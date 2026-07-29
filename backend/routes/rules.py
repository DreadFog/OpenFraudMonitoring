"""
Rules CRUD endpoints
"""

from flask import Blueprint, request, jsonify
from services.database import db
from models import Rule, RuleMatch
from services.auth import require_auth, require_role

rules_bp = Blueprint("rules", __name__, url_prefix="/api")


def _validate_rule_data(data: dict) -> str | None:
    """Return an error string if the rule data is invalid, else None."""
    rule_type = data.get("rule_type", "realtime")
    conditions = data.get("conditions") or []

    has_sequence = any(c.get("type") == "sequence" for c in conditions if isinstance(c, dict))

    if has_sequence and rule_type != "periodic":
        return "Sequence conditions are only allowed in periodic rules."

    for cond in conditions:
        if not isinstance(cond, dict):
            return "Each condition must be a JSON object."
        if cond.get("type") == "sequence":
            steps = cond.get("steps")
            if not isinstance(steps, list) or len(steps) < 2:
                return "A sequence condition must have at least 2 steps."
            for step in steps:
                if not isinstance(step, dict) or "event_type" not in step:
                    return "Each sequence step must have an event_type."

    return None


@rules_bp.route("/rules", methods=["GET"])
@require_auth
@require_role("admin")
def list_rules():
    rules = Rule.query.order_by(Rule.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rules]), 200


@rules_bp.route("/rules", methods=["POST"])
@require_auth
@require_role("admin")
def create_rule():
    data = request.get_json() or {}
    err = _validate_rule_data(data)
    if err:
        return jsonify({"ok": False, "error": err}), 400

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
@require_auth
@require_role("admin")
def update_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    data = request.get_json() or {}

    # Merge proposed changes for validation
    merged = rule.to_dict()
    merged.update({k: data[k] for k in data if k in merged})
    err = _validate_rule_data(merged)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    for key in ("name", "description", "enabled", "rule_type", "logic",
                "conditions", "score_modifier", "period_seconds"):
        if key in data:
            setattr(rule, key, data[key])

    db.session.commit()
    return jsonify(rule.to_dict()), 200


@rules_bp.route("/rules/<int:rule_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def delete_rule(rule_id):
    rule = Rule.query.get_or_404(rule_id)
    RuleMatch.query.filter_by(rule_id=rule.id).delete()
    db.session.delete(rule)
    db.session.commit()
    return jsonify({"ok": True}), 200
