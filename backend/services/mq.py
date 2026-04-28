"""
RabbitMQ message queue helpers for backend ⇄ connector communication.

Exchanges & queues
------------------

* Exchange ``ofm.intel`` (direct):
    - routing key ``request.<connector>``  → queue ``intel.requests.<connector>``
      Connectors consume their own request queue.
    - routing key ``response``             → queue ``intel.responses``
      The backend worker consumes responses (regardless of which connector
      produced them).

Message format
--------------

Both directions carry JSON.  Requests:

    {
      "request_id":   "<uuid>",          # echoed back in the response
      "type":         "ip_lookup",       # only one type for now
      "value":        "1.2.3.4",
      "requested_at": <epoch_ms>
    }

Responses:

    {
      "request_id":  "<uuid>",
      "connector":   "opencti",
      "value":       "1.2.3.4",
      "ok":          true,
      "error":       null,
      "stix_bundle": { ... }              # STIX 2.1 bundle of objects+SROs
    }
"""

import json
import logging
import threading
import time
import uuid
from typing import Optional, Callable

import pika
from pika.exceptions import AMQPConnectionError

from config import Config

logger = logging.getLogger(__name__)


EXCHANGE = "ofm.intel"
RESPONSE_QUEUE = "intel.responses"
RESPONSE_ROUTING_KEY = "response"


def request_routing_key(connector: str) -> str:
    return f"request.{connector}"


def request_queue(connector: str) -> str:
    return f"intel.requests.{connector}"


# ── Connection (lazy, thread-local) ─────────────────────────────────────────

_local = threading.local()


def _connect() -> pika.BlockingConnection:
    params = pika.URLParameters(Config.RABBITMQ_URL)
    params.heartbeat = 30
    params.blocked_connection_timeout = 10
    return pika.BlockingConnection(params)


def _get_channel():
    conn = getattr(_local, "conn", None)
    if conn is None or conn.is_closed:
        _local.conn = _connect()
        _local.channel = _local.conn.channel()
        _declare_topology(_local.channel)
    return _local.channel


def _declare_topology(channel):
    """Idempotently declare the exchange + the response queue."""
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)
    channel.queue_declare(queue=RESPONSE_QUEUE, durable=True)
    channel.queue_bind(
        exchange=EXCHANGE,
        queue=RESPONSE_QUEUE,
        routing_key=RESPONSE_ROUTING_KEY,
    )


# ── Publish ─────────────────────────────────────────────────────────────────

def publish_intel_request(connector: str, value: str, request_type: str = "ip_lookup") -> Optional[str]:
    """
    Publish an intel-lookup request to a connector.  Returns the request_id
    so callers can correlate the response, or None if publishing failed.
    """
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "type": request_type,
        "value": value,
        "requested_at": int(time.time() * 1000),
    }
    rk = request_routing_key(connector)
    queue = request_queue(connector)

    try:
        ch = _get_channel()
        # Ensure the per-connector request queue exists & is bound.
        ch.queue_declare(queue=queue, durable=True)
        ch.queue_bind(exchange=EXCHANGE, queue=queue, routing_key=rk)
        ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=rk,
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,  # persistent
            ),
        )
        logger.info("Published intel request %s to %s (value=%s)", request_id, connector, value)
        return request_id
    except (AMQPConnectionError, Exception) as e:
        logger.error("Failed to publish intel request: %s", e)
        # Reset the cached connection so the next call reconnects.
        try:
            if getattr(_local, "conn", None):
                _local.conn.close()
        except Exception:
            pass
        _local.conn = None
        return None


# ── Consume responses (blocking, for the worker) ────────────────────────────

def consume_responses(handler: Callable[[dict], None]):
    """
    Block forever, calling ``handler(message_dict)`` for each response.
    Reconnects automatically on connection loss.
    """
    while True:
        try:
            conn = _connect()
            ch = conn.channel()
            _declare_topology(ch)
            ch.basic_qos(prefetch_count=8)

            def _on_message(_chan, method, _props, body):
                try:
                    msg = json.loads(body.decode("utf-8"))
                except Exception as e:
                    logger.error("Bad message body: %s", e)
                    _chan.basic_ack(delivery_tag=method.delivery_tag)
                    return
                try:
                    handler(msg)
                    _chan.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logger.exception("Handler failed: %s", e)
                    # Requeue once; rely on dead-letter / manual retry beyond that.
                    _chan.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            ch.basic_consume(queue=RESPONSE_QUEUE, on_message_callback=_on_message)
            logger.info("Consuming intel responses from %s", RESPONSE_QUEUE)
            ch.start_consuming()
        except AMQPConnectionError as e:
            logger.warning("RabbitMQ connection lost: %s — reconnecting in 5s", e)
            time.sleep(5)
        except Exception as e:
            logger.exception("Unexpected error in consume_responses: %s", e)
            time.sleep(5)


# ── Health (queue depth) ────────────────────────────────────────────────────

def queue_depth(queue_name: str) -> Optional[int]:
    """Return the current message count of a queue, or None on error."""
    try:
        ch = _get_channel()
        result = ch.queue_declare(queue=queue_name, durable=True, passive=True)
        return result.method.message_count
    except Exception as e:
        logger.debug("queue_depth(%s) failed: %s", queue_name, e)
        return None
