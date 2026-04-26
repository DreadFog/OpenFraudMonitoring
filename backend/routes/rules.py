"""
Rules CRUD endpoints
"""

from flask import Blueprint, request, jsonify
from services.database import db
from models import Rule, RuleMatch

rules_bp = Blueprint("rules", __name__, url_prefix="/api")


@rules_bp.route("/rules", methods=["GET"])
def list_rules():
    rules = Rule.query.order_by(Rule.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rules]), 200


@rules_bp.route("/rules", methods=["POST"])
def create_rule():
    data = request.get_json() or {}
    rule = Rule(
        name=data.get("name", "Untitled Rule"),
        description=data.get("description", ""),
        enabled=data.get("enabled", True),
        rule_type=data.get("rule_type", "realtime"),
        logic=data.get("logic", "AND"),
        conditions=data.get("conditions", []),
        score_modifier=data.get("score_modifier", 0),
        period_seconds=data.get("period_seconds", 0),
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict()), 201


@rules_bp.route("/rules/<int:rule_id>", methods=["PUT"])
def update_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    data = request.get_json() or {}

    for key in ("name", "description", "enabled", "rule_type", "logic",
                "conditions", "score_modifier", "period_seconds"):
        if key in data:
            setattr(rule, key, data[key])

    db.session.commit()
    return jsonify(rule.to_dict()), 200


@rules_bp.route("/rules/<int:rule_id>", methods=["DELETE"])
def delete_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    RuleMatch.query.filter_by(rule_id=rule.id).delete()
    db.session.delete(rule)
    db.session.commit()
    return jsonify({"ok": True}), 200
