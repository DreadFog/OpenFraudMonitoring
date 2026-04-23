"""
Stats endpoint - overall statistics
"""

from flask import Blueprint, jsonify
from datetime import datetime

stats_bp = Blueprint("stats", __name__, url_prefix="/api")

# Shared session storage
sessions_store = {}


def init_stats_routes(app, sessions):
    """Initialize stats routes with shared storage"""
    global sessions_store
    sessions_store = sessions
    app.register_blueprint(stats_bp)


@stats_bp.route("/stats", methods=["GET"])
def get_stats():
    """
    Get overall statistics
    """
    total = len(sessions_store)
    high_risk = sum(1 for s in sessions_store.values() if s.risk_score >= 60)
    low_risk = total - high_risk

    bots = 0
    for sess in sessions_store.values():
        for flag in sess.flags:
            if "DETECTED" in flag or "WEBDRIVER" in flag or "DRIVER" in flag:
                bots += 1
                break

    return jsonify({
        "total_sessions": total,
        "high_risk_count": high_risk,
        "low_risk_count": low_risk,
        "bots_detected": bots,
        "timestamp": datetime.now().isoformat(),
    }), 200
