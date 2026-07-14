"""
Graph exploration routes.

  POST /api/graph/seed        — build the initial graph for a list of seeds
  POST /api/graph/expansions  — list one-hop expansion options (with counts)
  POST /api/graph/expand      — execute a single one-hop expansion
"""

import logging

from flask import Blueprint, request, jsonify

from services.auth import require_auth
from services.settings import get_graph_expand_threshold
from services.graph import resolve_seeds, get_expansions, expand, compute_links

logger = logging.getLogger(__name__)

graph_bp = Blueprint("graph", __name__, url_prefix="/api/graph")


@graph_bp.route("/seed", methods=["POST"])
@require_auth
def seed():
    body = request.get_json(silent=True) or {}
    seeds = body.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        return jsonify({"error": "seeds must be a non-empty array"}), 400
    result = resolve_seeds(seeds)
    result["threshold"] = get_graph_expand_threshold()
    return jsonify(result), 200


@graph_bp.route("/expansions", methods=["POST"])
@require_auth
def expansions():
    body = request.get_json(silent=True) or {}
    ref = body.get("ref")
    known_ids = body.get("known_ids", [])
    if not isinstance(ref, dict):
        return jsonify({"error": "ref must be an object"}), 400
    if not isinstance(known_ids, list):
        known_ids = []
    threshold = get_graph_expand_threshold()
    options = get_expansions(ref, known_ids)
    for opt in options:
        opt["warn"] = opt.get("count", 0) >= threshold
    return jsonify({"expansions": options, "threshold": threshold}), 200


@graph_bp.route("/expand", methods=["POST"])
@require_auth
def do_expand():
    body = request.get_json(silent=True) or {}
    ref = body.get("ref")
    key = body.get("key")
    if not isinstance(ref, dict) or not key:
        return jsonify({"error": "ref (object) and key (string) are required"}), 400
    result = expand(ref, key)
    return jsonify(result), 200


@graph_bp.route("/links", methods=["POST"])
@require_auth
def links():
    body = request.get_json(silent=True) or {}
    ref = body.get("ref")
    known_ids = body.get("known_ids", [])
    if not isinstance(ref, dict):
        return jsonify({"error": "ref must be an object"}), 400
    if not isinstance(known_ids, list):
        known_ids = []
    return jsonify(compute_links(ref, known_ids)), 200
