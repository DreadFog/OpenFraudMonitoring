"""
Stats endpoint - overall statistics
"""

from flask import Blueprint, jsonify
from datetime import datetime
from models import Session
from sqlalchemy import func
from services.bot_detection import bot_flag_expression
from services.auth import require_auth
from services.database import db

stats_bp = Blueprint("stats", __name__, url_prefix="/api")


@stats_bp.route("/stats", methods=["GET"])
@require_auth
def get_stats():
    """
    Get overall statistics
    """
    total, high_risk, bots = db.session.query(
        func.count(Session.id),
        func.count(Session.id).filter(Session.risk_score >= 60),
        func.count(Session.id).filter(bot_flag_expression(Session.flags)),
    ).one()
    low_risk = total - high_risk

    return jsonify({
        "total_sessions": total,
        "high_risk_count": high_risk,
        "low_risk_count": low_risk,
        "bots_detected": bots,
        "timestamp": datetime.now().isoformat(),
    }), 200
