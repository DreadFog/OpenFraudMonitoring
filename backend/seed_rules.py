"""
Seed the database with default detection rules.

Run once after initializing the database:
    python seed_rules.py

These rules replicate the scoring logic that was previously hardcoded in
analysis/risk.py. They are inserted as realtime rules so the worker evaluates
them on every incoming fingerprint / heartbeat event.

Running this script multiple times is safe — existing rules (matched by name)
are skipped.
"""

from flask import Flask
from config import Config
from services.database import init_db, db
from models import Rule

DEFAULT_RULES = [
    # ── Bot / automation signals ─────────────────────────────────────────────
    {
        "name": "CHROMEDRIVER_PROPS",
        "description": "ChromeDriver properties detected on the page",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_chromedriver", "op": "eq", "value": "true"}],
        "score_modifier": 45,
    },
    {
        "name": "WEBDRIVER_DETECTED",
        "description": "navigator.webdriver is true",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_webdriver", "op": "eq", "value": "true"}],
        "score_modifier": 40,
    },
    {
        "name": "PHANTOMJS_DETECTED",
        "description": "PhantomJS runtime detected",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_phantom", "op": "eq", "value": "true"}],
        "score_modifier": 40,
    },
    {
        "name": "SELENIUM_DETECTED",
        "description": "Selenium automation framework detected",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_selenium", "op": "eq", "value": "true"}],
        "score_modifier": 35,
    },
    {
        "name": "PUPPETEER_DETECTED",
        "description": "Puppeteer automation framework detected",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_puppeteer", "op": "eq", "value": "true"}],
        "score_modifier": 35,
    },
    {
        "name": "NIGHTMARE_DETECTED",
        "description": "Nightmare automation framework detected",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_nightmare", "op": "eq", "value": "true"}],
        "score_modifier": 35,
    },
    {
        "name": "NATIVE_SPOOFED",
        "description": "Browser native function toString check failed — likely spoofed environment",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_native_spoofed", "op": "eq", "value": "true"}],
        "score_modifier": 30,
    },
    {
        "name": "EMPTY_LANGUAGES",
        "description": "navigator.languages is empty — unusual for real browsers",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_empty_languages", "op": "eq", "value": "true"}],
        "score_modifier": 20,
    },
    {
        "name": "NO_PLUGINS",
        "description": "No browser plugins reported",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_no_plugins", "op": "eq", "value": "true"}],
        "score_modifier": 15,
    },

    # ── Hardware anomalies ───────────────────────────────────────────────────
    {
        "name": "ZERO_SCREEN",
        "description": "Screen width or height is zero — likely headless environment",
        "rule_type": "realtime",
        "logic": "OR",
        "conditions": [
            {"field": "screen_width", "op": "eq", "value": "0"},
            {"field": "screen_height", "op": "eq", "value": "0"},
        ],
        "score_modifier": 25,
    },
    {
        "name": "ZERO_CPU_CORES",
        "description": "hardwareConcurrency is zero",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "hardware_concurrency", "op": "eq", "value": "0"}],
        "score_modifier": 20,
    },
    {
        "name": "ZERO_DEVICE_MEMORY",
        "description": "deviceMemory is zero",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "device_memory", "op": "eq", "value": "0"}],
        "score_modifier": 15,
    },
    {
        "name": "ZERO_COLOR_DEPTH",
        "description": "Screen color depth is zero",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "color_depth", "op": "eq", "value": "0"}],
        "score_modifier": 15,
    },

    # ── Missing capabilities ─────────────────────────────────────────────────
    {
        "name": "NO_CANVAS",
        "description": "Canvas fingerprinting returned no data",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_canvas", "op": "eq", "value": "false"}],
        "score_modifier": 10,
    },
    {
        "name": "NO_WEBGL",
        "description": "No WebGL vendor or renderer reported",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [
            {"field": "webgl_vendor", "op": "eq", "value": ""},
            {"field": "webgl_renderer", "op": "eq", "value": ""},
        ],
        "score_modifier": 10,
    },
    {
        "name": "NO_AUDIO",
        "description": "No audio context data available",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "has_audio", "op": "eq", "value": "false"}],
        "score_modifier": 5,
    },
    {
        "name": "NO_TIMEZONE",
        "description": "Timezone is empty — unusual for real browsers",
        "rule_type": "realtime",
        "logic": "AND",
        "conditions": [{"field": "timezone", "op": "eq", "value": ""}],
        "score_modifier": 5,
    },
]


def seed():
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db(app)

    with app.app_context():
        db.create_all()

        created = 0
        skipped = 0

        for rule_data in DEFAULT_RULES:
            existing = Rule.query.filter_by(name=rule_data["name"]).first()
            if existing:
                skipped += 1
                continue

            rule = Rule(
                name=rule_data["name"],
                description=rule_data["description"],
                enabled=True,
                rule_type=rule_data["rule_type"],
                logic=rule_data["logic"],
                conditions=rule_data["conditions"],
                score_modifier=rule_data["score_modifier"],
            )
            db.session.add(rule)
            created += 1

        db.session.commit()
        print(f"[SEED] {created} rules created, {skipped} skipped (already exist)")


if __name__ == "__main__":
    seed()
