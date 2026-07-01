from __future__ import annotations

from uuid import uuid4

from flask import Blueprint, jsonify, request

from .services.groq_signal import score_with_groq
from .services.scoring import combine_signal_scores
from .services.stylometry import score_with_stylometry
from .storage import get_recent_entries, insert_audit_entry, make_timestamp

api = Blueprint("api", __name__)

@api.route("/submit", methods=["POST"])
def submit():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    creator_id = payload.get("creator_id")
    title = payload.get("title")

    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text is required"}), 400
    if not isinstance(creator_id, str) or not creator_id.strip():
        return jsonify({"error": "creator_id is required"}), 400

    content_id = str(uuid4())
    groq_result = score_with_groq(text.strip())
    style_result = score_with_stylometry(text.strip())
    combined_result = combine_signal_scores(float(groq_result["groq_score"]), float(style_result["style_score"]))

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "title": title,
        "timestamp": make_timestamp(),
        "attribution": combined_result["label"],
        "confidence": round(combined_result["confidence"], 3),
        "llm_score": round(float(groq_result["groq_score"]), 3),
        "style_score": round(float(style_result["style_score"]), 3),
        "combined_ai_score": round(float(combined_result["combined_ai_score"]), 3),
        "status": "classified",
        "signal_scores": {
            "groq_score": round(float(groq_result["groq_score"]), 3),
            "style_score": round(float(style_result["style_score"]), 3),
        },
        "model": groq_result["model"],
        "provider": groq_result["provider"],
        "prompt_version": groq_result["prompt_version"],
        "raw_label": groq_result["raw_label"],
        "groq_explanation": groq_result["explanation"],
        "style_metrics": style_result["metrics"],
        "style_explanation": style_result["explanation"],
        "combined_result": combined_result,
    }
    insert_audit_entry(entry)

    response = {
        "content_id": content_id,
        "submission_id": content_id,
        "attribution": combined_result["label"],
        "confidence": round(combined_result["confidence"], 3),
        "label": combined_result["label_text"],
        "label_text": combined_result["label_text"],
        "combined_ai_score": round(float(combined_result["combined_ai_score"]), 3),
        "signal_scores": {
            "groq_score": round(float(groq_result["groq_score"]), 3),
            "style_score": round(float(style_result["style_score"]), 3),
        },
        "llm_score": round(float(groq_result["groq_score"]), 3),
        "style_score": round(float(style_result["style_score"]), 3),
        "status": "classified",
        "explanation": groq_result["explanation"],
        "appeal_available": True,
    }
    return jsonify(response), 200


@api.route("/log", methods=["GET"])
def log_entries():
    limit_param = request.args.get("limit", "20")
    try:
        limit = max(1, min(100, int(limit_param)))
    except ValueError:
        limit = 20
    return jsonify({"entries": get_recent_entries(limit)}), 200


@api.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200
