"""
OpenFraudMonitoring Backend - Python Flask
Main application entry point
"""

import logging
import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from config import Config

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger('pika').setLevel(logging.INFO)
logger = logging.getLogger(__name__)
from services.database import init_db
from services.log_shipper import install as install_log_shipper
from routes import register_routes
from rules import seed_default_rules

install_log_shipper("backend")

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# ─────────────────────────────────────────────────────────────────────────────
# Database + Routes + Default Rules
# ─────────────────────────────────────────────────────────────────────────────

init_db(app)
register_routes(app)

with app.app_context():
    seed_default_rules()


# ─────────────────────────────────────────────────────────────────────────────
# Static file serving
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/fingerprint.js")
def serve_fingerprint():
    """
    Serve the fingerprint.js script
    """
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return send_from_directory(script_dir, "fingerprint.js")


# ─────────────────────────────────────────────────────────────────────────────
# Root and health
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return {
        "message": "OpenFraudMonitoring Backend v2.0",
        "endpoints": {
            "collect": "POST /api/collect",
            "heartbeat": "POST /api/heartbeat",
            "sessions": "GET /api/sessions",
            "stats": "GET /api/stats",
            "fingerprint_script": "GET /fingerprint.js",
        }
    }, 200


@app.route("/health", methods=["GET"])
def health():
    from models import Session
    return {"status": "ok", "sessions_count": Session.query.count()}, 200


if __name__ == "__main__":
    logger.info("Server starting...")
    logger.info("  API:                http://localhost:5000/api/collect")
    logger.info("  Heartbeat:          http://localhost:5000/api/heartbeat")
    logger.info("  Sessions:           http://localhost:5000/api/sessions")
    logger.info("  Stats:              http://localhost:5000/api/stats")
    logger.info("  Fingerprint script: http://localhost:5000/fingerprint.js")
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT)
