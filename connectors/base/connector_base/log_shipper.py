"""Cross-container log shipping via a capped Redis list (matches backend/services/log_shipper.py)."""

import json
import logging
import os
import time

import redis as _redis_lib

LIST_KEY = "ofm:logs"
MAX_ENTRIES = 500


class RedisLogHandler(logging.Handler):
    def __init__(self, redis_url: str, source: str, level=logging.WARNING):
        super().__init__(level=level)
        self.source = source
        try:
            self._client = _redis_lib.Redis.from_url(redis_url)
        except Exception:
            self._client = None

    def emit(self, record: logging.LogRecord) -> None:
        if self._client is None:
            return
        try:
            payload = json.dumps({
                "ts": int(time.time() * 1000),
                "level": record.levelname,
                "source": self.source,
                "logger": record.name,
                "message": self.format(record),
            })
            pipe = self._client.pipeline()
            pipe.lpush(LIST_KEY, payload)
            pipe.ltrim(LIST_KEY, 0, MAX_ENTRIES - 1)
            pipe.execute()
        except Exception:
            pass


def install(source: str, redis_url: str = None, level=logging.WARNING) -> None:
    redis_url = redis_url or os.environ.get("REDIS_URL", "redis://redis:6379/0")
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, RedisLogHandler):
            return
    handler = RedisLogHandler(redis_url, source, level=level)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root.addHandler(handler)
