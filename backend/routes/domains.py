import json

from flask import Blueprint, jsonify, request, Response

from models import DomainConfig
from services.auth import require_auth, require_role
from services.database import db
from services.domains import normalize_domain


domains_bp = Blueprint("domains", __name__, url_prefix="/api/admin/domains")


def _config_values(body):
    domain = normalize_domain(body.get("domain", ""))
    if not domain or "." not in domain:
        raise ValueError("domain must be a hostname")

    field_names = body.get("form_field_names", [])
    if not isinstance(field_names, list) or any(not isinstance(name, str) for name in field_names):
        raise ValueError("form_field_names must be an array of strings")

    method = str(body.get("form_method") or "post").strip().lower()
    if method not in {"get", "post", "put", "patch", "delete"}:
        raise ValueError("form_method is invalid")

    return {
        "domain": domain,
        "auth_cookie_name": (str(body.get("auth_cookie_name") or "").strip() or None),
        "form_action": (str(body.get("form_action") or "").strip() or None),
        "form_method": method,
        "form_field_names": [name.strip() for name in field_names if name.strip()],
        "active": bool(body.get("active", True)),
    }


def _apply_config(config, values):
    for key, value in values.items():
        setattr(config, key, value)


@domains_bp.route("", methods=["GET"])
@require_auth
@require_role("admin")
def list_domains():
    configs = DomainConfig.query.order_by(DomainConfig.domain).all()
    return jsonify([config.to_dict() for config in configs]), 200


@domains_bp.route("", methods=["POST"])
@require_auth
@require_role("admin")
def create_domain():
    try:
        values = _config_values(request.get_json() or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if DomainConfig.query.filter_by(domain=values["domain"]).first():
        return jsonify({"error": "domain already exists"}), 409
    config = DomainConfig(**values)
    db.session.add(config)
    db.session.commit()
    return jsonify(config.to_dict()), 201


@domains_bp.route("/<int:domain_id>", methods=["PUT"])
@require_auth
@require_role("admin")
def update_domain(domain_id):
    config = db.session.get(DomainConfig, domain_id)
    if not config:
        return jsonify({"error": "domain not found"}), 404
    try:
        values = _config_values(request.get_json() or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    duplicate = DomainConfig.query.filter(
        DomainConfig.domain == values["domain"], DomainConfig.id != domain_id
    ).first()
    if duplicate:
        return jsonify({"error": "domain already exists"}), 409
    _apply_config(config, values)
    db.session.commit()
    return jsonify(config.to_dict()), 200


@domains_bp.route("/<int:domain_id>", methods=["DELETE"])
@require_auth
@require_role("admin")
def delete_domain(domain_id):
    config = db.session.get(DomainConfig, domain_id)
    if not config:
        return jsonify({"error": "domain not found"}), 404
    db.session.delete(config)
    db.session.commit()
    return jsonify({"deleted": domain_id}), 200


@domains_bp.route("/export", methods=["GET"])
@require_auth
@require_role("admin")
def export_domains():
    payload = {"version": 1, "domains": [
        {
            "domain": config.domain,
            "auth_cookie_name": config.auth_cookie_name or "",
            "form_action": config.form_action or "",
            "form_method": config.form_method or "post",
            "form_field_names": config.form_field_names or [],
            "active": bool(config.active),
        }
        for config in DomainConfig.query.order_by(DomainConfig.domain).all()
    ]}
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=ofm-domains.json"},
    )


@domains_bp.route("/import", methods=["POST"])
@require_auth
@require_role("admin")
def import_domains():
    body = request.get_json(silent=True)
    entries = body.get("domains") if isinstance(body, dict) else body
    if not isinstance(entries, list):
        return jsonify({"error": "expected a JSON array or an object with a domains array"}), 400

    imported = []
    try:
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each domain entry must be an object")
            values = _config_values(entry)
            config = DomainConfig.query.filter_by(domain=values["domain"]).first()
            if not config:
                config = DomainConfig(**values)
                db.session.add(config)
            else:
                _apply_config(config, values)
            imported.append(values["domain"])
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"imported": imported, "count": len(imported)}), 200
