"""
Reusable connector main-loop.

Each connector subclass / instantiator provides:
  * a ``handler(request_msg) -> stix_bundle_dict``  callable
  * the connector ``name`` (used for queue routing)

The runner takes care of:
  * declaring its own request queue ``intel.requests.<name>``
  * consuming requests, calling the handler, publishing responses
  * publishing a heartbeat every 10s to ``ofm:connector:<name>:heartbeat``
    on Redis (used by the /logging page)
"""

import json
import logging
import threading
import time
from typing import Callable, Optional

import pika
import redis as _redis_lib
from pika.exceptions import AMQPConnectionError

from .config import ConnectorConfig

logger = logging.getLogger(__name__)


EXCHANGE = "ofm.intel"
RESPONSE_ROUTING_KEY = "response"


class ConnectorRunner:
    def __init__(
        self,
        config: ConnectorConfig,
        handler: Callable[[dict], dict],
        redis_url: Optional[str] = None,
    ):
        self.config = config
        self.handler = handler
        self.redis_url = redis_url or "redis://redis:6379/0"
        self._stop = False

    # ── Heartbeat ──
    def _heartbeat_loop(self):
        try:
            r = _redis_lib.Redis.from_url(self.redis_url)
        except Exception as e:
            logger.warning("Redis unavailable, heartbeat disabled: %s", e)
            return
        key = f"ofm:connector:{self.config.name}:heartbeat"
        while not self._stop:
            try:
                r.set(key, str(int(time.time())), ex=30)
            except Exception as e:
                logger.debug("heartbeat write failed: %s", e)
            time.sleep(10)

    # ── Main consumer loop ──
    def _connect(self) -> pika.BlockingConnection:
        params = pika.URLParameters(self.config.rabbitmq_url)
        params.heartbeat = 30
        params.blocked_connection_timeout = 10
        return pika.BlockingConnection(params)

    def _publish_response(self, channel, request_msg: dict, bundle: dict, ok: bool, error: Optional[str]):
        body = {
            "request_id": request_msg.get("request_id"),
            "connector": self.config.name,
            "value": request_msg.get("value"),
            "ok": ok,
            "error": error,
            "stix_bundle": bundle or {"type": "bundle", "objects": []},
        }
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=RESPONSE_ROUTING_KEY,
            body=json.dumps(body).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )

    def run(self):
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        # Publish our mode to Redis so the backend knows when to auto-trigger.
        try:
            r = _redis_lib.Redis.from_url(self.redis_url)
            r.set(f"ofm:connector:{self.config.name}:mode", self.config.mode or "manual")
        except Exception as e:
            logger.debug("could not publish connector mode: %s", e)

        request_queue = f"intel.requests.{self.config.name}"
        request_rk = f"request.{self.config.name}"

        while not self._stop:
            try:
                conn = self._connect()
                ch = conn.channel()
                ch.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)
                ch.queue_declare(queue=request_queue, durable=True)
                ch.queue_bind(exchange=EXCHANGE, queue=request_queue, routing_key=request_rk)
                # Response queue is declared by the backend; ensure it exists too.
                ch.queue_declare(queue="intel.responses", durable=True)
                ch.queue_bind(exchange=EXCHANGE, queue="intel.responses", routing_key=RESPONSE_ROUTING_KEY)
                ch.basic_qos(prefetch_count=4)

                def _on_message(_chan, method, _props, body):
                    try:
                        msg = json.loads(body.decode("utf-8"))
                    except Exception as e:
                        logger.error("bad request body: %s", e)
                        _chan.basic_ack(delivery_tag=method.delivery_tag)
                        return

                    bundle: dict = {}
                    ok = True
                    error: Optional[str] = None
                    try:
                        bundle = self.handler(msg) or {}
                    except Exception as e:
                        logger.exception("handler failed: %s", e)
                        ok = False
                        error = str(e)

                    try:
                        self._publish_response(_chan, msg, bundle, ok, error)
                    except Exception as e:
                        logger.exception("publish_response failed: %s", e)

                    _chan.basic_ack(delivery_tag=method.delivery_tag)

                ch.basic_consume(queue=request_queue, on_message_callback=_on_message)
                logger.info("Connector %s consuming requests on %s", self.config.name, request_queue)
                ch.start_consuming()
            except AMQPConnectionError as e:
                logger.warning("RabbitMQ down: %s — retrying in 5s", e)
                time.sleep(5)
            except Exception as e:
                logger.exception("Runner error: %s", e)
                time.sleep(5)
