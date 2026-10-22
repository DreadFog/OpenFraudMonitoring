"""Graph node, edge, and identifier serialization helpers."""

from services.stix_filters import TYPE_TO_MODEL
from services.graph_schema import DEVICE_PROPERTY_FIELDS, PROPERTY_FIELDS
from models import Device, Session, StixRelationship


def session_node_id(session_id: int) -> str:
    return f"session:{session_id}"


def device_node_id(device_id: int) -> str:
    return f"device:{device_id}"


def stix_node_id(stix_id: str) -> str:
    return f"stix:{stix_id}"


def property_node_id(field: str, value: str) -> str:
    return f"property:{field}:{value}"


def flag_node_id(flag: str) -> str:
    return f"flag:{flag}"


def _stix_id_type(stix_id: str) -> str:
    return (stix_id or "").split("--", 1)[0]


def _resolve_stix(stix_id: str):
    Model = TYPE_TO_MODEL.get(_stix_id_type(stix_id))
    if Model is None:
        return None
    return Model.query.filter_by(stix_id=stix_id).first()


def build_session_node(sess: Session) -> dict:
    return {
        "id": session_node_id(sess.id),
        "kind": "session",
        "label": f"Session #{sess.id}",
        "ref": {"kind": "session", "id": sess.id},
        "data": {
            "id": sess.id,
            "fsid": sess.fsid,
            "risk_score": sess.risk_score or 0,
            "flags": sess.flags or [],
            "client_ip": sess.client_ip or "",
            "first_seen": sess.first_seen,
            "last_seen": sess.last_seen,
        },
    }


def build_device_node(device: Device) -> dict:
    label = f"Device #{device.id}"
    if device.platform:
        label += f" · {device.platform}"
    return {
        "id": device_node_id(device.id),
        "kind": "device",
        "label": label,
        "ref": {"kind": "device", "id": device.id},
        "data": {
            "id": device.id,
            "platform": device.platform,
            "device_type": device.device_type,
            "is_mobile": device.is_mobile,
            "confidence": device.confidence,
            "has_cookie": bool(device.cookie_id),
            "sessions_count": device.sessions.count(),
            "first_seen": device.first_seen,
            "last_seen": device.last_seen,
        },
    }


def build_stix_node(obj, stix_type: str) -> dict:
    if stix_type == "indicator":
        from services.indicator_revocation import apply_indicator_revocation
        apply_indicator_revocation([obj])
    name = (obj.raw or {}).get("name") if isinstance(obj.raw, dict) else None
    return {
        "id": stix_node_id(obj.stix_id),
        "kind": "stix",
        "stix_type": stix_type,
        "label": _stix_label(obj, stix_type),
        "ref": {"kind": "stix", "stix_id": obj.stix_id},
        "data": {
            "stix_id": obj.stix_id,
            "stix_type": stix_type,
            "name": name,
            "value": obj.value,
            **({"revoked": obj.revoked} if stix_type == "indicator" else {}),
        },
    }


def _stix_label(obj, stix_type: str) -> str:
    raw = obj.raw if isinstance(obj.raw, dict) else {}
    name = raw.get("name")
    if stix_type == "autonomous-system":
        num = raw.get("number") or obj.value
        base = f"AS{num}"
        return (f"{base} · {name}" if name else base)[:48]
    if name:
        return str(name)[:48]
    return (obj.value or obj.stix_id)[:48]


def build_flag_node(flag: str) -> dict:
    return {
        "id": flag_node_id(flag),
        "kind": "flag",
        "label": flag,
        "ref": {"kind": "flag", "value": flag},
        "data": {"flag": flag},
    }


def build_property_node(field: str, value: str) -> dict:
    meta = PROPERTY_FIELDS.get(field) or DEVICE_PROPERTY_FIELDS.get(field) or {}
    return {
        "id": property_node_id(field, value),
        "kind": "property",
        "field": field,
        "label": f"{meta.get('label', field)}: {value}",
        "ref": {"kind": "property", "field": field, "value": value},
        "data": {"field": field, "label": meta.get("label", field), "value": value},
    }


def _meta_edge(source_id: str, target_id: str, label: str) -> dict:
    return {
        "id": f"edge:{source_id}|{target_id}|{label}",
        "source": source_id,
        "target": target_id,
        "kind": "metadata",
        "label": label,
    }


def _stix_edge(rel: StixRelationship) -> dict:
    return {
        "id": f"edge:rel:{rel.stix_id}",
        "source": stix_node_id(rel.source_ref),
        "target": stix_node_id(rel.target_ref),
        "kind": "stix_relationship",
        "label": rel.relationship_type,
    }
