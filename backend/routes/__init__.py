"""
Routes package — registers all API blueprints.
"""

from routes.collect import collect_bp
from routes.heartbeat import heartbeat_bp
from routes.sessions import sessions_bp
from routes.stats import stats_bp
from routes.rules import rules_bp
from routes.filters import filters_bp


def register_routes(app):
    """Register all API blueprints with the Flask app."""
    app.register_blueprint(collect_bp)
    app.register_blueprint(heartbeat_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(filters_bp)
