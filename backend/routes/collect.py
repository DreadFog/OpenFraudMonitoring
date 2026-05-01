"""
Collect endpoint — receives FPScanner fingerprints + OFM extension data.

Expected payload:
  {
    "fingerprint": "<encrypted_base64>",   // FPScanner encrypted fingerprint
    "extensions": { "ip": {...}, ... },     // OFM extension data (optional)
    "timestamp": 1234567890,
    "url": "https://..."
  }
"""

import logging

from flask import Blueprint, request, jsonify, current_app
from services.database import db
from models import Session, Fingerprint, SessionURL, BrowserSession
from services.event_queue import enqueue_event, get_redis
from services.stix_store import (
    get_or_create_ip, get_or_create_user_agent,
    get_or_create_country, get_or_create_autonomous_system,
    get_or_create_relationship,
)
from services.mq import publish_intel_request
from utils.crypto import decrypt_fingerprint

logger = logging.getLogger(__name__)

collect_bp = Blueprint("collect", __name__, url_prefix="/api")


@collect_bp.route("/collect", methods=["POST"])
def collect():
    """
    Receive and store an FPScanner fingerprint with extension data.
    """
    body = request.get_json() or {}

    # Decrypt the FPScanner payload
    encrypted_payload = body.get("fingerprint")
    if encrypted_payload and isinstance(encrypted_payload, str):
        key = current_app.config.get("FPSCANNER_KEY", "dev-key")
        try:
            fp = decrypt_fingerprint(encrypted_payload, key)
        except Exception as e:
            return jsonify({"error": f"Decryption failed: {e}"}), 400
    else:
        # Raw (unencrypted) fingerprint for development
        fp = body

    # Merge extension data into the stored object
    extensions = body.get("extensions", {})

    fsid = fp.get("fsid", "unknown")
    url = fp.get("url", "") or body.get("url", "")
    timestamp = fp.get("time", 0)
    nonce = fp.get("nonce", "")

    # Get client IP (prefer extension-collected IP, fallback to headers)
    ip_ext = extensions.get("ip", {}) or {}
    client_ip = ip_ext.get("ip") or request.headers.get("X-Forwarded-For", request.remote_addr)

    # Find or create session keyed by fsid
    session_obj = Session.query.filter_by(fsid=fsid).first()
    if not session_obj:
        session_obj = Session(fsid=fsid, first_seen=timestamp)
        db.session.add(session_obj)
        db.session.flush()

    session_obj.last_seen = timestamp
    session_obj.client_ip = client_ip

    # ── Create / link STIX observables (Phase 1) ──
    # IP observable
    ip_obs = get_or_create_ip(client_ip) if client_ip else None
    if ip_obs is not None:
        session_obj.ip_observable_type = ip_obs.raw.get("type") if isinstance(ip_obs.raw, dict) else None
        session_obj.ip_observable_id = ip_obs.id

    # Country observable (from IP extension data)
    country_iso = ip_ext.get("country_iso")
    country_name = ip_ext.get("country")
    country_obs = get_or_create_country(country_iso, country_name) if country_iso else None
    if ip_obs is not None and country_obs is not None:
        get_or_create_relationship(ip_obs.stix_id, "located-at", country_obs.stix_id)

    # Autonomous System observable (from IP extension data)
    asn = ip_ext.get("asn")
    asn_org = ip_ext.get("asn_org")
    as_obs = get_or_create_autonomous_system(asn, asn_org) if asn else None
    if ip_obs is not None and as_obs is not None:
        get_or_create_relationship(ip_obs.stix_id, "belongs-to", as_obs.stix_id)

    # User-Agent observable (from the decrypted fingerprint payload)
    ua_string = (fp.get("signals", {}).get("browser", {}) or {}).get("userAgent")
    ua_obs = get_or_create_user_agent(ua_string) if ua_string else None
    if ua_obs is not None:
        session_obj.user_agent_observable_id = ua_obs.id

    # Build the full stored object: FPScanner fingerprint + extensions
    stored_data = fp
    if extensions:
        stored_data["_extensions"] = extensions

    # ── Debug logging: dump key signal values to diagnose missing data ──
    _signals = fp.get("signals", {})
    _device = _signals.get("device", {})
    _browser = _signals.get("browser", {})
    _locale = _signals.get("locale", {})
    _hev = _browser.get("highEntropyValues", {})
    logger.debug("Incoming FP keys: %s", list(fp.keys()))
    logger.debug("signals keys: %s", list(_signals.keys()))
    logger.debug("device.memory=%s device.cpuCount=%s device.platform=%s", _device.get('memory'), _device.get('cpuCount'), _device.get('platform'))
    logger.debug("device.screenResolution=%s", _device.get('screenResolution'))
    logger.debug("browser.userAgent=%s", str(_browser.get('userAgent', ''))[:80])
    logger.debug("highEntropyValues=%s", _hev)
    logger.debug("locale.languages=%s locale.intl=%s", _locale.get('languages'), _locale.get('internationalization'))
    logger.debug("fastBotDetection=%s detections_count=%s", fp.get('fastBotDetection'), len(fp.get('fastBotDetectionDetails', {})))
    logger.debug("extensions keys: %s", list(extensions.keys()))

    # Store fingerprint with denormalized fields
    denorm = Fingerprint.extract_fields(fp)
    fingerprint = Fingerprint(
        session_id=session_obj.id,
        timestamp=timestamp,
        data=stored_data,
        **denorm,
    )
    db.session.add(fingerprint)

    # Track URL (ignore duplicate)
    if url:
        existing_url = SessionURL.query.filter_by(
            session_id=session_obj.id, url=url
        ).first()
        if not existing_url:
            db.session.add(SessionURL(session_id=session_obj.id, url=url))

    # Track nonce as browser session ID (for anti-replay / session tracking)
    if nonce:
        existing_bs = BrowserSession.query.filter_by(
            browser_session_id=nonce
        ).first()
        if not existing_bs:
            db.session.add(BrowserSession(
                session_id=session_obj.id,
                browser_session_id=nonce,
            ))

    db.session.commit()

    # Enqueue for rule evaluation (best-effort)
    enqueue_event(session_obj.id, "fingerprint")

    # ── Auto-trigger intel lookups for connectors in 'auto' or 'both' mode ──
    if ip_obs is not None and client_ip:
        try:
            redis_client = get_redis()
            for key in redis_client.scan_iter(match="ofm:connector:*:mode"):
                mode = (redis_client.get(key) or b"").decode("utf-8")
                if mode in ("auto", "both"):
                    # key format: ofm:connector:<name>:mode
                    name = key.decode("utf-8").split(":")[2]
                    publish_intel_request(name, client_ip, request_type="ip_lookup")
        except Exception as e:
            logger.debug("auto intel trigger failed: %s", e)

    logger.info("fsid=%s bot=%s ip=%s url=%s", fsid[:32], fp.get('fastBotDetection'), client_ip, url)

    return jsonify({
        "ok": True,
        "fsid": fsid,
        "session_id": session_obj.id,
    }), 200
