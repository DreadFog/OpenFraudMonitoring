"""
Worker process — consumes events from Redis and evaluates detection rules.

Run as a separate Docker service:
    python worker.py

Two loops run concurrently:
  1. Real-time loop  – pulls events from the Redis queue and evaluates
     "realtime" rules against the session that triggered the event.
  2. Periodic loop   – runs every 60 s, evaluates "periodic" rules against
     all sessions in the database.
"""

import os
import json
import logging
import time
import threading
from flask import Flask
from config import Config
from services.database import init_db, db
from services.event_queue import get_redis
from rules import seed_default_rules

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger('pika').setLevel(logging.INFO) #  reduce verbosity of pika
logger = logging.getLogger(__name__)

from services.log_shipper import install as install_log_shipper
install_log_shipper("worker")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db(app)

    # Retry — the DB container may still be initializing on first boot
    with app.app_context():
        for attempt in range(1, 11):
            try:
                db.create_all()
                seed_default_rules()
                break
            except Exception as e:
                logger.warning("DB not ready (attempt %d/10): %s", attempt, e)
                db.session.rollback()
                time.sleep(2)
        else:
            logger.error("Could not seed rules after 10 attempts, continuing anyway")

    return app


app = create_app()


def _apply_rule_matches(rules, session_id=None):
    """Evaluate a list of rules; create RuleMatch rows for new matches."""
    from models import Rule, RuleMatch, Session
    from rules.engine import evaluate_rule

    for rule in rules:
        matching = evaluate_rule(rule, session_id=session_id)
        for session in matching:
            existing = RuleMatch.query.filter_by(
                rule_id=rule.id, session_id=session.id
            ).first()
            if not existing:
                session.risk_score = min(
                    (session.risk_score or 0) + rule.score_modifier, 100
                )
                # Append rule name to session flags
                flags = list(session.flags or [])
                if rule.name not in flags:
                    flags.append(rule.name)
                    session.flags = flags
                db.session.add(RuleMatch(
                    rule_id=rule.id,
                    session_id=session.id,
                    score_change=rule.score_modifier,
                ))
    db.session.commit()


# ── Real-time event consumer ────────────────────────────────────────────────

def process_realtime_events():
    r = get_redis()
    logger.info("Listening for events on ofm:events …")

    while True:
        try:
            result = r.brpop("ofm:events", timeout=5)
            if result is None:
                continue

            _, raw = result
            event = json.loads(raw)
            session_id = event["session_id"]

            with app.app_context():
                from models import Rule
                rules = Rule.query.filter_by(
                    enabled=True, rule_type="realtime"
                ).all()
                _apply_rule_matches(rules, session_id=session_id)

        except Exception as e:
            logger.error("Error processing event: %s", e)
            time.sleep(1)


# ── Periodic rule evaluator ─────────────────────────────────────────────────

def process_periodic_rules():
    while True:
        time.sleep(Config.PERIODIC_INTERVAL_SECONDS)
        try:
            with app.app_context():
                from models import Rule
                rules = Rule.query.filter_by(
                    enabled=True, rule_type="periodic"
                ).all()
                if rules:
                    _apply_rule_matches(rules)
        except Exception as e:
            logger.error("Periodic error: %s", e)


# ── Entry point ─────────────────────────────────────────────────────────────

def _intel_response_handler(msg: dict):
    """Persist a STIX bundle from a connector response."""
    bundle = msg.get("stix_bundle") or {}
    if not bundle:
        logger.warning("intel response %s carried no stix_bundle", msg.get("request_id"))
        return
    from services.intel_ingest import ingest_bundle
    with app.app_context():
        logger.debug("Received the following bundle: '%s'", str(bundle))
        count = ingest_bundle(bundle)
        logger.info(
            "intel response request_id=%s connector=%s value=%s ingested=%d",
            msg.get("request_id"), msg.get("connector"), msg.get("value"), count,
        )


def process_intel_responses():
    """Drain the RabbitMQ ``intel.responses`` queue forever."""
    from services.mq import consume_responses
    consume_responses(_intel_response_handler)


if __name__ == "__main__":
    threading.Thread(target=process_periodic_rules, daemon=True).start()
    threading.Thread(target=process_intel_responses, daemon=True).start()
    process_realtime_events()
