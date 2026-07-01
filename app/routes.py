from __future__ import annotations

from uuid import uuid4

from flask import Blueprint, jsonify, request

from .services.groq_signal import score_with_groq
from .storage import get_recent_entries, insert_audit_entry, make_timestamp

api = Blueprint("api", __name__)



def _build_label(groq_score: float) -> tuple[str, str, float]:
    confidence = abs(groq_score - 0.5) * 2
    if groq_score >= 0.70:
        return (
            "likely_ai",
            "Likely AI-generated. This submission matches multiple machine-writing patterns.",
            confidence,
        )
    if groq_score <= 0.30:
        return (
            "likely_human",
            "Likely human-written. This submission does not resemble common AI generation patterns.",
            confidence,
        )
    return (
        "uncertain",
        "Uncertain. The signals disagree or the text is too short to judge reliably.",
        confidence,
    )


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
    signal_result = score_with_groq(text.strip())
    groq_score = float(signal_result["groq_score"])
    attribution, label, confidence = _build_label(groq_score)

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "title": title,
        "timestamp": make_timestamp(),
        "attribution": attribution,
        "confidence": round(confidence, 3),
        "llm_score": round(groq_score, 3),
        "status": "classified",
        "signal_scores": {"groq_score": round(groq_score, 3)},
        "model": signal_result["model"],
        "provider": signal_result["provider"],
        "prompt_version": signal_result["prompt_version"],
        "raw_label": signal_result["raw_label"],
        "explanation": signal_result["explanation"],
    }
    insert_audit_entry(entry)

    response = {
        "content_id": content_id,
        "submission_id": content_id,
        "attribution": attribution,
        "confidence": round(confidence, 3),
        "label": label,
        "signal_scores": {"groq_score": round(groq_score, 3)},
        "llm_score": round(groq_score, 3),
        "status": "classified",
        "explanation": signal_result["explanation"],
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
