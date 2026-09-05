"""
Rules CRUD endpoints
"""

from flask import Blueprint, request, jsonify
from services.database import db
from models import Rule, RuleMatch
from services.auth import require_auth, require_role
from services.schema import OPERATORS, get_field_meta

rules_bp = Blueprint("rules", __name__, url_prefix="/api")

_RULE_TYPES = {"realtime", "periodic"}
_LOGIC_VALUES = {"AND", "OR"}
_SEQUENCE_FIELDS = {
    "copy": {
        "url": "string", "length": "number", "text": "string",
        "source_tag": "string", "source_id": "string", "source_name": "string",
        "source_type": "string", "form_action": "string",
    },
    "paste": {
        "url": "string", "length": "number", "text": "string",
        "target_tag": "string", "target_id": "string", "target_name": "string",
        "target_type": "string", "form_action": "string",
    },
    "form_submit": {
        "url": "string", "action": "string", "method": "string",
        "field_names": "string",
    },
    "button_click": {
        "url": "string", "x": "number", "y": "number", "tag": "string",
        "text": "string",
    },
}


def _operator_names(field_type: str) -> set[str]:
    return {operator["name"] for operator in OPERATORS[field_type]}


def _validate_filter(condition: dict, field_types: dict[str, str] | None = None) -> str | None:
    field_name = condition.get("field")
    if not isinstance(field_name, str) or not field_name:
        return "Each filter must have a field."

    if field_types is None:
        metadata = get_field_meta(field_name)
        if metadata is None:
            return f"Unknown filter field: {field_name}."
        field_type = metadata["type"]
    else:
        field_type = field_types.get(field_name)
        if field_type is None:
            return f"Unknown sequence filter field: {field_name}."

    operator = condition.get("op")
    if operator not in _operator_names(field_type):
        return f"Operator '{operator}' is not valid for field '{field_name}'."
    if "value" not in condition:
        return f"Filter '{field_name}' must have a value."
    return None


def _validate_rule_data(data: dict) -> str | None:
    """Return an error string if the rule data is invalid, else None."""
    if not isinstance(data, dict):
        return "Rule body must be a JSON object."

    rule_type = data.get("rule_type", "realtime")
    logic = data.get("logic", "AND")
    conditions = data.get("conditions", [])

    if rule_type not in _RULE_TYPES:
        return "rule_type must be realtime or periodic."
    if logic not in _LOGIC_VALUES:
        return "logic must be AND or OR."
    if not isinstance(conditions, list):
        return "conditions must be an array."

    score_modifier = data.get("score_modifier", 0)
    period_seconds = data.get("period_seconds", 0)
    if isinstance(score_modifier, bool) or not isinstance(score_modifier, int) or not -100 <= score_modifier <= 100:
        return "score_modifier must be an integer between -100 and 100."
    if isinstance(period_seconds, bool) or not isinstance(period_seconds, int) or period_seconds < 0:
        return "period_seconds must be a non-negative integer."

    has_sequence = any(c.get("type") == "sequence" for c in conditions if isinstance(c, dict))

    if has_sequence and rule_type != "periodic":
        return "Sequence conditions are only allowed in periodic rules."
    if has_sequence and logic != "AND":
        return "Rules with sequence conditions must use AND logic."

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
                event_type = step["event_type"]
                field_types = _SEQUENCE_FIELDS.get(event_type)
                if field_types is None:
                    return f"Unknown sequence event_type: {event_type}."
                filters = step.get("filters", [])
                if not isinstance(filters, list):
                    return "Sequence step filters must be an array."
                for step_filter in filters:
                    if not isinstance(step_filter, dict):
                        return "Each sequence step filter must be a JSON object."
                    error = _validate_filter(step_filter, field_types)
                    if error:
                        return error
        else:
            error = _validate_filter(cond)
            if error:
                return error

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
