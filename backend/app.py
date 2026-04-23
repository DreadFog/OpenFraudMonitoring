"""
Anti-Fraud Fingerprint Backend - Python Flask
Main application entry point
"""

from flask import Flask, send_from_directory
from flask_cors import CORS
from collections import defaultdict
import os

from routes import init_collect_routes
from routes.heartbeat import init_heartbeat_routes
from routes.sessions import init_sessions_routes
from routes.stats import init_stats_routes

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────────────────────────────────────
# In-memory storage
# ─────────────────────────────────────────────────────────────────────────────

sessions = {}
url_sessions = defaultdict(list)


# ─────────────────────────────────────────────────────────────────────────────
# Initialize routes with shared storage
# ─────────────────────────────────────────────────────────────────────────────

init_collect_routes(app, sessions, url_sessions)
init_heartbeat_routes(app, sessions, url_sessions)
init_sessions_routes(app, sessions)
init_stats_routes(app, sessions)


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
        "message": "Anti-Fraud Fingerprint Backend v2.0",
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
    return {"status": "ok", "sessions_count": len(sessions)}, 200


if __name__ == "__main__":
    print("Server starting...")
    print("  API:                http://localhost:5000/api/collect")
    print("  Heartbeat:          http://localhost:5000/api/heartbeat")
    print("  Sessions:           http://localhost:5000/api/sessions")
    print("  Stats:              http://localhost:5000/api/stats")
    print("  Fingerprint script: http://localhost:5000/fingerprint.js")
    app.run(debug=True, host="0.0.0.0", port=5000)
