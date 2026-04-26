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

from flask import Blueprint, request, jsonify, current_app
from services.database import db
from models import Session, Fingerprint, SessionURL, BrowserSession
from services.event_queue import enqueue_event
from utils.crypto import decrypt_fingerprint

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

    # Build the full stored object: FPScanner fingerprint + extensions
    stored_data = fp
    if extensions:
        stored_data["_extensions"] = extensions

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

    print(f"[COLLECT] fsid={fsid[:32]} bot={fp.get('fastBotDetection')} ip={client_ip} url={url}")

    return jsonify({
        "ok": True,
        "fsid": fsid,
        "session_id": session_obj.id,
    }), 200
