"""
Graph exploration service.

Builds nodes/edges for the interactive graph view and computes one-hop
expansions.  Three node families exist:

  - session   : a tracked session (keyed by fsid)
  - stix      : a STIX observable/SDO (keyed by stix_id)
  - property  : a virtual metadata value node (keyed by field + value)

Edges are never persisted; session↔stix and session↔property links are
"metadata" edges derived at query time, while stix↔stix edges come from the
persisted STIX relationships.

All expansions are strictly one hop.  Every expansion option is annotated with
the exact number of *new* nodes it would add (after subtracting node ids the
client already has), so the UI can warn before large expansions.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import func, or_

from services.database import db
from services.stix_filters import TYPE_TO_MODEL
from models import Session, Fingerprint, StixRelationship


# ─────────────────────────────────────────────────────────────────────────────
# Curated property whitelist (v1)
# ─────────────────────────────────────────────────────────────────────────────
# Each entry maps a human label to the denormalized Fingerprint column(s) used
# both to read a session's own value and to count sessions sharing that value.

PROPERTY_FIELDS = {
    "platform": {
        "label": "Platform",
        "columns": ["device_platform"],
    },
    "timezone": {
        "label": "Timezone",
        "columns": ["locale_internationalization_timezone"],
    },
    "language": {
        "label": "Language",
        "columns": ["locale_languages_language"],
    },
    "screen_resolution": {
        "label": "Screen Resolution",
        "columns": [
            "device_screen_resolution_width",
            "device_screen_resolution_height",
        ],
        "join": "x",
    },
    "cpu_count": {
        "label": "CPU Count",
        "columns": ["device_cpu_count"],
        "type": "number",
    },
    "webgl_vendor": {
        "label": "WebGL Vendor",
        "columns": ["graphics_web_gl_vendor"],
    },
    "webgl_renderer": {
        "label": "WebGL Renderer",
        "columns": ["graphics_web_gl_renderer"],
    },
    "locale_language": {
        "label": "Locale Language",
        "columns": ["locale_internationalization_locale_language"],
    },
    "hev_platform": {
        "label": "UA-CH Platform",
        "columns": ["browser_high_entropy_values_platform"],
    },
    "hev_architecture": {
        "label": "UA-CH Architecture",
        "columns": ["browser_high_entropy_values_architecture"],
    },
    "color_scheme": {
        "label": "Color Scheme",
        "columns": ["device_media_queries_prefers_color_scheme"],
    },
    "canvas_fingerprint": {
        "label": "Canvas Fingerprint",
        "columns": ["graphics_canvas_canvas_fingerprint"],
    },
    "pointer_type": {
        "label": "Pointer Type",
        "columns": ["device_media_queries_pointer"],
    },
}


# Human labels for STIX entity types (used for per-type relationship expansions).
STIX_TYPE_LABELS = {
    "ipv4-addr": "IPv4 Address",
    "ipv6-addr": "IPv6 Address",
    "user-agent": "User Agent",
    "autonomous-system": "Autonomous System",
    "location": "Country",
    "indicator": "Indicator",
    "malware": "Malware",
    "campaign": "Campaign",
    "intrusion-set": "Intrusion Set",
}


# ─────────────────────────────────────────────────────────────────────────────
# Node / edge id helpers
# ─────────────────────────────────────────────────────────────────────────────

def session_node_id(fsid: str) -> str:
    return f"session:{fsid}"


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


# ─────────────────────────────────────────────────────────────────────────────
# Node builders
# ─────────────────────────────────────────────────────────────────────────────

def build_session_node(sess: Session) -> dict:
    return {
        "id": session_node_id(sess.fsid),
        "kind": "session",
        "label": sess.fsid[:16] + ("…" if len(sess.fsid) > 16 else ""),
        "ref": {"kind": "session", "fsid": sess.fsid},
        "data": {
            "fsid": sess.fsid,
            "risk_score": sess.risk_score or 0,
            "flags": sess.flags or [],
            "client_ip": sess.client_ip or "",
            "first_seen": sess.first_seen,
            "last_seen": sess.last_seen,
        },
    }


def build_stix_node(obj, stix_type: str) -> dict:
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
            "decayed": obj.decayed,
        },
    }


def _stix_label(obj, stix_type: str) -> str:
    """Human-friendly label for a STIX node — prefers the name from raw JSONB."""
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
    meta = PROPERTY_FIELDS.get(field, {})
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


# ─────────────────────────────────────────────────────────────────────────────
# Property helpers
# ─────────────────────────────────────────────────────────────────────────────

def _session_property_value(sess: Session, field: str):
    """Return the string value of a whitelisted property for a session."""
    meta = PROPERTY_FIELDS.get(field)
    if meta is None:
        return None
    fp = sess.fingerprints.order_by(Fingerprint.timestamp.desc()).first()
    if fp is None:
        return None
    parts = []
    for col in meta["columns"]:
        val = getattr(fp, col, None)
        if val is None or val == "" or val == 0:
            return None
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        parts.append(str(val))
    return meta.get("join", "").join(parts) if len(parts) > 1 else parts[0]


def _property_filter(field: str, value: str):
    """Build a SQLAlchemy filter matching Fingerprints with this property value."""
    meta = PROPERTY_FIELDS.get(field)
    if meta is None:
        return None
    cols = meta["columns"]
    is_number = meta.get("type") == "number"
    if len(cols) == 1:
        typed_value = float(value) if is_number else value
        return getattr(Fingerprint, cols[0]) == typed_value
    # Composite (e.g. resolution "WxH")
    sep = meta.get("join", "x")
    parts = str(value).split(sep)
    if len(parts) != len(cols):
        return None
    conds = []
    for col, part in zip(cols, parts):
        conds.append(getattr(Fingerprint, col) == part)
    from sqlalchemy import and_
    return and_(*conds)


def _count_sessions_with_property(field: str, value: str) -> int:
    flt = _property_filter(field, value)
    if flt is None:
        return 0
    return (
        db.session.query(func.count(func.distinct(Fingerprint.session_id)))
        .filter(flt)
        .scalar()
        or 0
    )


def _sessions_with_property(field: str, value: str):
    flt = _property_filter(field, value)
    if flt is None:
        return []
    session_ids = [
        r[0]
        for r in db.session.query(func.distinct(Fingerprint.session_id)).filter(flt).all()
    ]
    if not session_ids:
        return []
    return Session.query.filter(Session.id.in_(session_ids)).all()


# ─────────────────────────────────────────────────────────────────────────────
# Flag (triggered rule) helpers
# ─────────────────────────────────────────────────────────────────────────────

def _count_sessions_with_flag(flag: str) -> int:
    return Session.query.filter(Session.flags.contains([flag])).count()


def _sessions_with_flag(flag: str):
    return Session.query.filter(Session.flags.contains([flag])).all()


# ─────────────────────────────────────────────────────────────────────────────
# Session ↔ STIX linkage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _session_linked_stix(sess: Session):
    """Return [(obj, stix_type, edge_label)] for a session's IP + user-agent."""
    out = []
    if sess.ip_observable_id and sess.ip_observable_type:
        Model = TYPE_TO_MODEL.get(sess.ip_observable_type)
        if Model is not None:
            obj = Model.query.get(sess.ip_observable_id)
            if obj is not None:
                out.append((obj, sess.ip_observable_type, "ip"))
    if sess.user_agent_observable_id:
        Model = TYPE_TO_MODEL.get("user-agent")
        obj = Model.query.get(sess.user_agent_observable_id)
        if obj is not None:
            out.append((obj, "user-agent", "user-agent"))
    return out


def _sessions_linked_to_stix(obj, stix_type: str):
    if stix_type in ("ipv4-addr", "ipv6-addr"):
        return Session.query.filter_by(
            ip_observable_id=obj.id, ip_observable_type=stix_type
        ).all()
    if stix_type == "user-agent":
        return Session.query.filter_by(user_agent_observable_id=obj.id).all()
    return []


def _count_sessions_linked_to_stix(obj, stix_type: str) -> int:
    if stix_type in ("ipv4-addr", "ipv6-addr"):
        return Session.query.filter_by(
            ip_observable_id=obj.id, ip_observable_type=stix_type
        ).count()
    if stix_type == "user-agent":
        return Session.query.filter_by(user_agent_observable_id=obj.id).count()
    return 0


def _stix_relationships(obj):
    return StixRelationship.query.filter(
        or_(
            StixRelationship.source_ref == obj.stix_id,
            StixRelationship.target_ref == obj.stix_id,
        )    ).all()


# ─────────────────────────────────────────────────────────────────────────────
# Seed resolution
# ─────────────────────────────────────────────────────────────────────────────

def resolve_seeds(seeds: Iterable[dict]) -> dict:
    """Build the initial graph for a list of seed refs.

    Session seeds also include their directly-linked IP/user-agent observables
    (intrinsic attributes), so the graph is not empty on open.
    """
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(node):
        nodes[node["id"]] = node

    def add_edge(edge):
        edges[edge["id"]] = edge

    for seed in seeds or []:
        kind = (seed.get("kind") or "").strip()
        if kind == "session":
            fsid = seed.get("fsid")
            sess = Session.query.filter_by(fsid=fsid).first() if fsid else None
            if sess is None:
                continue
            sn = build_session_node(sess)
            add_node(sn)
            for obj, stix_type, label in _session_linked_stix(sess):
                stn = build_stix_node(obj, stix_type)
                add_node(stn)
                add_edge(_meta_edge(sn["id"], stn["id"], label))
        elif kind == "stix":
            obj = None
            stix_type = None
            if seed.get("stix_id"):
                obj = _resolve_stix(seed["stix_id"])
                stix_type = _stix_id_type(seed["stix_id"])
            elif seed.get("type") and seed.get("value"):
                Model = TYPE_TO_MODEL.get(seed["type"])
                if Model is not None:
                    obj = Model.query.filter_by(value=seed["value"]).first()
                    stix_type = seed["type"]
            if obj is not None:
                add_node(build_stix_node(obj, stix_type))

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


# ─────────────────────────────────────────────────────────────────────────────
# Expansion options (with counts)
# ─────────────────────────────────────────────────────────────────────────────

def _new_count(candidate_ids: Iterable[str], known_ids: set) -> int:
    return sum(1 for cid in candidate_ids if cid not in known_ids)


def get_expansions(ref: dict, known_ids: Iterable[str]) -> list[dict]:
    """Return the available one-hop expansion options for a node ref.

    Each option: {key, label, count} where count = new nodes it would add.
    """
    known = set(known_ids or [])
    kind = (ref.get("kind") or "").strip()

    if kind == "session":
        sess = Session.query.filter_by(fsid=ref.get("fsid")).first()
        if sess is None:
            return []
        options = []

        # Linked STIX observables (IP + user-agent), keyed by role so the same
        # expansion category works across many selected sessions in bulk.
        for obj, stix_type, role in _session_linked_stix(sess):
            nid = stix_node_id(obj.stix_id)
            rlabel = "IP address" if role == "ip" else "User Agent"
            options.append({
                "key": f"role:{role}",
                "label": f"{rlabel}: {obj.value}",
                "category": rlabel,
                "group": "linked",
                "count": _new_count([nid], known),
            })

        # Property values
        for field, meta in PROPERTY_FIELDS.items():
            value = _session_property_value(sess, field)
            if value is None:
                continue
            nid = property_node_id(field, value)
            options.append({
                "key": f"property:{field}",
                "label": f"{meta['label']}: {value}",
                "category": meta["label"],
                "group": "property",
                "count": _new_count([nid], known),
            })

        # Flags / triggered rules
        for flag in (sess.flags or []):
            nid = flag_node_id(flag)
            options.append({
                "key": f"flag:{flag}",
                "label": f"Flag: {flag}",
                "category": flag,
                "group": "flag",
                "count": _new_count([nid], known),
            })
        return options

    if kind == "stix":
        obj, stix_type = _resolve_ref_stix(ref)
        if obj is None:
            return []
        options = []

        # Linked sessions
        linked_sessions = _count_sessions_linked_to_stix(obj, stix_type)
        if linked_sessions:
            sess_rows = _sessions_linked_to_stix(obj, stix_type)
            ids = [session_node_id(s.fsid) for s in sess_rows]
            options.append({
                "key": "linked_sessions",
                "label": "Linked sessions",
                "category": "Linked sessions",
                "group": "sessions",
                "count": _new_count(ids, known),
            })

        # STIX relationships grouped by the related entity type so the user can
        # expand a specific type (AS, Country, IP, User Agent, …).
        rels = _stix_relationships(obj)
        by_type: dict[str, set] = {}
        for r in rels:
            other = r.target_ref if r.source_ref == obj.stix_id else r.source_ref
            t = _stix_id_type(other)
            by_type.setdefault(t, set()).add(stix_node_id(other))
        for t, ids in by_type.items():
            label = STIX_TYPE_LABELS.get(t, t)
            options.append({
                "key": f"reltype:{t}",
                "label": label,
                "category": label,
                "group": "relationships",
                "count": _new_count(ids, known),
            })
        return options

    if kind == "property":
        field = ref.get("field")
        value = ref.get("value")
        count = _count_sessions_with_property(field, value)
        if not count:
            return []
        sess_rows = _sessions_with_property(field, value)
        ids = [session_node_id(s.fsid) for s in sess_rows]
        return [{
            "key": "sessions",
            "label": "Sessions with this value",
            "category": "Sessions",
            "group": "sessions",
            "count": _new_count(ids, known),
        }]

    if kind == "flag":
        flag = ref.get("value")
        if not flag:
            return []
        sess_rows = _sessions_with_flag(flag)
        ids = [session_node_id(s.fsid) for s in sess_rows]
        if not ids:
            return []
        return [{
            "key": "sessions",
            "label": "Sessions with this flag",
            "category": "Sessions",
            "group": "sessions",
            "count": _new_count(ids, known),
        }]

    return []


def _resolve_ref_stix(ref: dict):
    if ref.get("stix_id"):
        return _resolve_stix(ref["stix_id"]), _stix_id_type(ref["stix_id"])
    if ref.get("type") and ref.get("value"):
        Model = TYPE_TO_MODEL.get(ref["type"])
        if Model is not None:
            return Model.query.filter_by(value=ref["value"]).first(), ref["type"]
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# One-hop expansion execution
# ─────────────────────────────────────────────────────────────────────────────

def expand(ref: dict, key: str) -> dict:
    """Execute a single one-hop expansion and return the added nodes/edges."""
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(node):
        nodes[node["id"]] = node

    def add_edge(edge):
        edges[edge["id"]] = edge

    kind = (ref.get("kind") or "").strip()

    if kind == "session":
        sess = Session.query.filter_by(fsid=ref.get("fsid")).first()
        if sess is None:
            return {"nodes": [], "edges": []}
        sn_id = session_node_id(sess.fsid)

        if key.startswith("role:"):
            role = key.split(":", 1)[1]
            for obj, stix_type, r in _session_linked_stix(sess):
                if r == role:
                    stn = build_stix_node(obj, stix_type)
                    add_node(stn)
                    add_edge(_meta_edge(sn_id, stn["id"], r))
        elif key.startswith("property:"):
            field = key.split(":", 1)[1]
            value = _session_property_value(sess, field)
            if value is not None:
                pn = build_property_node(field, value)
                add_node(pn)
                add_edge(_meta_edge(sn_id, pn["id"], PROPERTY_FIELDS[field]["label"]))
        elif key.startswith("flag:"):
            flag = key.split(":", 1)[1]
            if flag in (sess.flags or []):
                fn = build_flag_node(flag)
                add_node(fn)
                add_edge(_meta_edge(sn_id, fn["id"], "flag"))

    elif kind == "stix":
        obj, stix_type = _resolve_ref_stix(ref)
        if obj is None:
            return {"nodes": [], "edges": []}
        obj_node_id = stix_node_id(obj.stix_id)

        if key == "linked_sessions":
            for sess in _sessions_linked_to_stix(obj, stix_type):
                sn = build_session_node(sess)
                add_node(sn)
                label = "user-agent" if stix_type == "user-agent" else "ip"
                add_edge(_meta_edge(sn["id"], obj_node_id, label))
        elif key.startswith("reltype:"):
            target_type = key.split(":", 1)[1]
            for r in _stix_relationships(obj):
                other_id = r.target_ref if r.source_ref == obj.stix_id else r.source_ref
                if _stix_id_type(other_id) != target_type:
                    continue
                other = _resolve_stix(other_id)
                if other is None:
                    continue
                on = build_stix_node(other, _stix_id_type(other_id))
                add_node(on)
                add_edge(_stix_edge(r))

    elif kind == "property":
        field = ref.get("field")
        value = ref.get("value")
        pn_id = property_node_id(field, value)
        label = PROPERTY_FIELDS.get(field, {}).get("label", field)
        for sess in _sessions_with_property(field, value):
            sn = build_session_node(sess)
            add_node(sn)
            add_edge(_meta_edge(sn["id"], pn_id, label))

    elif kind == "flag":
        flag = ref.get("value")
        fn_id = flag_node_id(flag)
        for sess in _sessions_with_flag(flag):
            sn = build_session_node(sess)
            add_node(sn)
            add_edge(_meta_edge(sn["id"], fn_id, "flag"))

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


# ─────────────────────────────────────────────────────────────────────────────
# Auto-link: edges between a node and nodes already present in the graph
# ─────────────────────────────────────────────────────────────────────────────

def compute_links(ref: dict, known_ids: Iterable[str]) -> dict:
    """Return only the edges connecting `ref` to nodes already in the graph.

    No new nodes are added — used when adding an entity with "look up links to
    existing nodes" enabled.
    """
    known = set(known_ids or [])
    edges: dict[str, dict] = {}

    def add_edge(edge):
        edges[edge["id"]] = edge

    kind = (ref.get("kind") or "").strip()

    if kind == "session":
        sess = Session.query.filter_by(fsid=ref.get("fsid")).first()
        if sess is None:
            return {"edges": []}
        sn_id = session_node_id(sess.fsid)
        for obj, stix_type, label in _session_linked_stix(sess):
            other = stix_node_id(obj.stix_id)
            if other in known:
                add_edge(_meta_edge(sn_id, other, label))
        for field, meta in PROPERTY_FIELDS.items():
            value = _session_property_value(sess, field)
            if value is None:
                continue
            other = property_node_id(field, value)
            if other in known:
                add_edge(_meta_edge(sn_id, other, meta["label"]))
        for flag in (sess.flags or []):
            other = flag_node_id(flag)
            if other in known:
                add_edge(_meta_edge(sn_id, other, "flag"))

    elif kind == "stix":
        obj, stix_type = _resolve_ref_stix(ref)
        if obj is None:
            return {"edges": []}
        obj_node_id = stix_node_id(obj.stix_id)
        for sess in _sessions_linked_to_stix(obj, stix_type):
            other = session_node_id(sess.fsid)
            if other in known:
                label = "user-agent" if stix_type == "user-agent" else "ip"
                add_edge(_meta_edge(other, obj_node_id, label))
        for r in _stix_relationships(obj):
            other_id = r.target_ref if r.source_ref == obj.stix_id else r.source_ref
            if stix_node_id(other_id) in known:
                add_edge(_stix_edge(r))

    elif kind == "property":
        field = ref.get("field")
        value = ref.get("value")
        pn_id = property_node_id(field, value)
        label = PROPERTY_FIELDS.get(field, {}).get("label", field)
        for sess in _sessions_with_property(field, value):
            other = session_node_id(sess.fsid)
            if other in known:
                add_edge(_meta_edge(other, pn_id, label))

    elif kind == "flag":
        flag = ref.get("value")
        fn_id = flag_node_id(flag)
        for sess in _sessions_with_flag(flag):
            other = session_node_id(sess.fsid)
            if other in known:
                add_edge(_meta_edge(other, fn_id, "flag"))

    return {"edges": list(edges.values())}
