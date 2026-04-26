"""
Rules package — engine + rule loader (defaults + custom).
"""

import json
import os

DEFAULTS_DIR = os.path.join(os.path.dirname(__file__), "defaults")
CUSTOM_DIR = os.path.join(os.path.dirname(__file__), "custom")


def _load_json_rules(directory):
    """Read all .json files from a directory and return a list of rule dicts."""
    rules = []
    if not os.path.isdir(directory):
        return rules
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(directory, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            rules.append(json.load(f))
    return rules


def load_default_rules():
    """Load rules from both defaults/ and custom/ directories."""
    return _load_json_rules(DEFAULTS_DIR) + _load_json_rules(CUSTOM_DIR)


def seed_default_rules():
    """
    Insert default rules into the database. Skips rules whose name already exists.
    Must be called inside a Flask app context.
    """
    from services.database import db
    from models import Rule

    defaults = load_default_rules()
    created = 0

    for rule_data in defaults:
        existing = Rule.query.filter_by(name=rule_data["name"]).first()
        if existing:
            continue
        db.session.add(Rule(
            name=rule_data["name"],
            description=rule_data.get("description", ""),
            enabled=True,
            rule_type=rule_data.get("rule_type", "realtime"),
            logic=rule_data.get("logic", "AND"),
            conditions=rule_data.get("conditions", []),
            score_modifier=rule_data.get("score_modifier", 0),
        ))
        created += 1

    if created:
        db.session.commit()
        print(f"[RULES] {created} default rules loaded from {DEFAULTS_DIR}")
