"""
Redis event queue for asynchronous rule processing.

Events are pushed by the HTTP routes (collect, heartbeat) and consumed
by the worker process.  If Redis is unavailable the enqueue is silently
skipped so that the HTTP request is never blocked.
"""

import json
import os
import redis as _redis_lib

_client = None


def get_redis():
    global _client
    if _client is None:
        _client = _redis_lib.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0")
        )
    return _client


def enqueue_event(session_db_id, event_type):
    """Push an event onto the processing queue (best-effort)."""
    try:
        get_redis().lpush(
            "ofm:events",
            json.dumps({"session_id": session_db_id, "type": event_type}),
        )
    except Exception:
        pass
