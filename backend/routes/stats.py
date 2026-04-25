"""
Stats endpoint - overall statistics
"""

from flask import Blueprint, jsonify
from datetime import datetime
from models import Session

stats_bp = Blueprint("stats", __name__, url_prefix="/api")


@stats_bp.route("/stats", methods=["GET"])
def get_stats():
    """
    Get overall statistics
    """
    total = Session.query.count()
    high_risk = Session.query.filter(Session.risk_score >= 60).count()
    low_risk = total - high_risk

    # Count sessions with bot-related flags using JSONB contains
    bot_keywords = ["DETECTED", "WEBDRIVER", "DRIVER"]
    bots = 0
    bot_sessions = Session.query.filter(Session.flags != None).all()  # noqa: E711
    for sess in bot_sessions:
        for flag in (sess.flags or []):
            if any(kw in flag for kw in bot_keywords):
                bots += 1
                break

    return jsonify({
        "total_sessions": total,
        "high_risk_count": high_risk,
        "low_risk_count": low_risk,
        "bots_detected": bots,
        "timestamp": datetime.now().isoformat(),
    }), 200
