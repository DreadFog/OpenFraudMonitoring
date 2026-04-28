"""
Centralized configuration — reads from environment variables with sensible defaults.
All services (app, worker) import from here.
"""

import os


class Config:
    # ── Database ──
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://ofm:ofm@db:5432/ofm")
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
    }

    # ── Redis ──
    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

    # ── RabbitMQ ──
    RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://ofm:ofm@rabbitmq:5672/")

    # ── Intel / Connectors ──
    CONNECTOR_TOKEN = os.environ.get("CONNECTOR_TOKEN", "dev-connector-token")
    INTEL_DECAY_DAYS = int(os.environ.get("INTEL_DECAY_DAYS", "7"))

    # ── Server ──
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # ── Worker ──
    PERIODIC_INTERVAL_SECONDS = int(os.environ.get("PERIODIC_INTERVAL_SECONDS", "60"))

    # ── FPScanner encryption ──
    # Must match the key used at fpscanner build time (npx fpscanner build --key=...)
    FPSCANNER_KEY = os.environ.get("FPSCANNER_KEY", "dev-key")

    # ── Client (injected at build time via Vite) ──
    # OFM_SERVER_URL is the URL the fingerprint.js client sends data to.
    # Set to "" for same-origin (default), or "https://ofm.example.com" for remote.
    OFM_SERVER_URL = os.environ.get("OFM_SERVER_URL", "")
