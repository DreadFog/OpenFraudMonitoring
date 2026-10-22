"""
Stats endpoint - overall statistics
"""

from flask import Blueprint, jsonify
from datetime import datetime
from models import Session
from services.bot_detection import has_bot_flag
from services.auth import require_auth

stats_bp = Blueprint("stats", __name__, url_prefix="/api")


@stats_bp.route("/stats", methods=["GET"])
@require_auth
def get_stats():
    """
    Get overall statistics
    """
    total = Session.query.count()
    high_risk = Session.query.filter(Session.risk_score >= 60).count()
    low_risk = total - high_risk

    bot_sessions = Session.query.filter(Session.flags != None).all()  # noqa: E711
    bots = sum(1 for sess in bot_sessions if has_bot_flag(sess.flags))

    return jsonify({
        "total_sessions": total,
        "high_risk_count": high_risk,
        "low_risk_count": low_risk,
        "bots_detected": bots,
        "timestamp": datetime.now().isoformat(),
    }), 200
