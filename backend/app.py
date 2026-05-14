"""
OpenFraudMonitoring Backend - Python Flask
Main application entry point
"""

import logging
import os

from flask import Flask, send_from_directory, request
from flask_cors import CORS

from init.config import Config
from services.cors_origins import dynamic_origin

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger('pika').setLevel(logging.INFO)
logger = logging.getLogger(__name__)
from services.database import init_db
from services.log_shipper import install as install_log_shipper
from services.auth import bcrypt
from routes import register_routes
from rules import seed_default_rules
from init.seed_users import seed_default_admin

install_log_shipper("backend")

app = Flask(__name__)
app.config.from_object(Config)

# CORS handled manually in after_request (see below)
CORS(app, resources={
    r"/api/*": {
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
    }
}, origins=[])  # Empty list since we handle dynamically

bcrypt.init_app(app)


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic CORS validation
# ─────────────────────────────────────────────────────────────────────────────

@app.after_request
def apply_cors_headers(response):
    """Apply CORS headers based on allowed origins from database."""
    origin = request.headers.get("Origin")
    if origin and dynamic_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

# ─────────────────────────────────────────────────────────────────────────────
# Database + Routes + Default Rules
# ─────────────────────────────────────────────────────────────────────────────

init_db(app)
register_routes(app)

with app.app_context():
    seed_default_rules()
    seed_default_admin()


# ─────────────────────────────────────────────────────────────────────────────
# Static file serving
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/ofm.js")
def serve_fingerprint():
    """
    Serve the ofm.js script
    """
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return send_from_directory(script_dir, "ofm.js")


# ─────────────────────────────────────────────────────────────────────────────
# Root and health
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return {
        "message": "OpenFraudMonitoring Backend v2.0",
        "endpoints": {
            "collect": "POST /api/initial",
            "heartbeat": "POST /api/heartbeat",
            "sessions": "GET /api/sessions",
            "stats": "GET /api/stats",
            "fingerprint_script": "GET /ofm.js",
        }
    }, 200


@app.route("/health", methods=["GET"])
def health():
    from models import Session
    return {"status": "ok", "sessions_count": Session.query.count()}, 200


if __name__ == "__main__":
    logger.info("Server starting...")
    logger.info("  API:                http://localhost:5000/api/initial")
    logger.info("  Heartbeat:          http://localhost:5000/api/heartbeat")
    logger.info("  Sessions:           http://localhost:5000/api/sessions")
    logger.info("  Stats:              http://localhost:5000/api/stats")
    logger.info("  Fingerprint script: http://localhost:5000/ofm.js")
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT)
