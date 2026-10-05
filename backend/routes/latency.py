"""Public, non-persistent endpoint for measuring a lightweight HTTP round trip."""

from flask import Blueprint, make_response

latency_bp = Blueprint("latency_probe", __name__, url_prefix="/api")


@latency_bp.route("/latency", methods=["GET"])
def probe():
    response = make_response("", 204)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Expose-Headers"] = "X-OFM-Latency-Probe"
    response.headers["X-OFM-Latency-Probe"] = "1"
    return response