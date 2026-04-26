"""
Seed the database with default detection rules based on FPScanner's detections.

Run once after initializing the database:
    python seed_rules.py

These rules are auto-generated from FPScanner's FastBotDetectionDetails.
Each detection becomes a realtime rule that checks the corresponding
denormalized column on the Fingerprint model.

Running this script multiple times is safe — existing rules (matched by name)
are skipped.
"""

from flask import Flask
from config import Config
from services.database import init_db, db
from models import Rule
from _generated_schema import DETECTION_FIELDS

# Severity → score modifier mapping (matches analysis/risk.py)
SEVERITY_SCORES = {
    "high": 15,
    "medium": 8,
    "low": 3,
}

# Severity for each detection rule (from FPScanner's index.ts)
DETECTION_SEVERITIES = {
    "headlessChromeScreenResolution": "high",
    "hasWebdriver": "high",
    "hasWebdriverWritable": "high",
    "hasSeleniumProperty": "high",
    "hasCDP": "high",
    "hasPlaywright": "high",
    "hasImpossibleDeviceMemory": "high",
    "hasHighCPUCount": "high",
    "hasMissingChromeObject": "high",
    "hasWebdriverIframe": "high",
    "hasWebdriverWorker": "high",
    "hasMismatchWebGLInWorker": "high",
    "hasMismatchPlatformIframe": "high",
    "hasMismatchPlatformWorker": "high",
    "hasSwiftshaderRenderer": "low",
    "hasUTCTimezone": "medium",
    "hasMismatchLanguages": "low",
    "hasInconsistentEtsl": "high",
    "hasBotUserAgent": "high",
    "hasGPUMismatch": "high",
    "hasPlatformMismatch": "high",
}


def build_default_rules():
    """Build DEFAULT_RULES list from the generated schema + severity map."""
    rules = []
    for det in DETECTION_FIELDS:
        name = det["name"]
        col = det["column"]
        severity = DETECTION_SEVERITIES.get(name, "medium")
        score = SEVERITY_SCORES.get(severity, 5)
        rules.append({
            "name": name,
            "description": f"FPScanner detection: {det['label']} (severity: {severity})",
            "rule_type": "realtime",
            "logic": "AND",
            "conditions": [{"field": col, "op": "eq", "value": "true"}],
            "score_modifier": score,
        })
    return rules


DEFAULT_RULES = build_default_rules()


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
