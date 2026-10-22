"""OpenFraudMonitoring Flask application factory and development entry point."""

import logging
import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from init.config import Config


def create_app(config_object=Config):
    """Create and initialize the backend application."""
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("pika").setLevel(logging.WARNING)

    if hasattr(config_object, "validate"):
        config_object.validate()

    app = Flask(__name__)
    app.config.from_object(config_object)

    # Import routes before database initialization so every model is registered.
    from routes import register_routes
    from services.auth import bcrypt
    from services.cors_origins import apply_cors_headers
    from services.database import init_db
    from services.log_shipper import install as install_log_shipper
    from rules import seed_default_rules
    from init.seed_users import seed_default_admin

    install_log_shipper("backend")

    CORS(app, resources={
        r"/api/*": {
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
        }
    }, origins=[])
    bcrypt.init_app(app)
    app.after_request(apply_cors_headers)

    init_db(app)
    register_routes(app)

    with app.app_context():
        seed_default_rules()
        seed_default_admin()

    @app.route("/ofm.js")
    def serve_fingerprint():
        script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        return send_from_directory(script_dir, "ofm.js")

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

    return app


if __name__ == "__main__":
    application = create_app()
    logger = logging.getLogger(__name__)
    logger.info("Server starting...")
    logger.info("  API:                http://localhost:5000/api/initial")
    logger.info("  Heartbeat:          http://localhost:5000/api/heartbeat")
    logger.info("  Sessions:           http://localhost:5000/api/sessions")
    logger.info("  Stats:              http://localhost:5000/api/stats")
    logger.info("  Fingerprint script: http://localhost:5000/ofm.js")
    application.run(debug=application.config["DEBUG"],
                    host=application.config["HOST"],
                    port=application.config["PORT"])
