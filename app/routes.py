from __future__ import annotations

from uuid import uuid4

from flask import Blueprint, jsonify, request

from .extensions import limiter
from .services.groq_signal import score_with_groq
from .services.metadata_signal import score_with_metadata
from .services.scoring import combine_signal_scores
from .services.stylometry import score_with_stylometry
from .storage import append_appeal_entry, get_latest_entry, get_recent_entries, insert_audit_entry, list_all_audit_entries, make_timestamp

api = Blueprint("api", __name__)

@api.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    payload = request.get_json(silent=True) or {}
    content_type = str(payload.get("content_type", "text")).strip().lower()
    text = payload.get("text")
    creator_id = payload.get("creator_id")
    title = payload.get("title")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    if content_type == "text":
        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "text is required"}), 400
    else:
        if not metadata:
            return jsonify({"error": "metadata is required for non-text submissions"}), 400

    if not isinstance(text, str) or not text.strip():
        text = ""
    if not isinstance(creator_id, str) or not creator_id.strip():
        return jsonify({"error": "creator_id is required"}), 400

    content_id = str(uuid4())
    canonical_text = text.strip() if text else " ".join(
        str(metadata.get(key, "")).strip() for key in ["title", "caption", "description", "alt_text"]
    ) or str(metadata.get("content_type", ""))
    metadata_payload = {
        "title": title or metadata.get("title"),
        "description": metadata.get("description") or metadata.get("caption") or metadata.get("alt_text"),
        "tags": metadata.get("tags", []),
        "source": metadata.get("source") or creator_id,
        "content_type": content_type,
    }

    groq_result = score_with_groq(canonical_text)
    style_result = score_with_stylometry(canonical_text)
    metadata_result = score_with_metadata(metadata_payload)
    combined_result = combine_signal_scores(
        float(groq_result["groq_score"]),
        float(style_result["style_score"]),
        float(metadata_result["metadata_score"]),
    )
    certificate_code = content_id[:8].upper()

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "title": title,
        "content_type": content_type,
        "timestamp": make_timestamp(),
        "attribution": combined_result["label"],
        "confidence": round(combined_result["confidence"], 3),
        "llm_score": round(float(groq_result["groq_score"]), 3),
        "style_score": round(float(style_result["style_score"]), 3),
        "metadata_score": round(float(metadata_result["metadata_score"]), 3),
        "combined_ai_score": round(float(combined_result["combined_ai_score"]), 3),
        "status": "classified",
        "signal_scores": {
            "groq_score": round(float(groq_result["groq_score"]), 3),
            "style_score": round(float(style_result["style_score"]), 3),
            "metadata_score": round(float(metadata_result["metadata_score"]), 3),
        },
        "model": groq_result["model"],
        "provider": groq_result["provider"],
        "prompt_version": groq_result["prompt_version"],
        "raw_label": groq_result["raw_label"],
        "groq_explanation": groq_result["explanation"],
        "style_metrics": style_result["metrics"],
        "style_explanation": style_result["explanation"],
        "metadata_metrics": metadata_result["metrics"],
        "metadata_explanation": metadata_result["explanation"],
        "combined_result": combined_result,
        "certificate_code": certificate_code,
        "certificate_verified": False,
    }
    insert_audit_entry(entry)

    response = {
        "content_id": content_id,
        "submission_id": content_id,
        "certificate_code": certificate_code,
        "certificate_available": True,
        "content_type": content_type,
        "attribution": combined_result["label"],
        "confidence": round(combined_result["confidence"], 3),
        "label": combined_result["label_text"],
        "label_text": combined_result["label_text"],
        "combined_ai_score": round(float(combined_result["combined_ai_score"]), 3),
        "signal_scores": {
            "groq_score": round(float(groq_result["groq_score"]), 3),
            "style_score": round(float(style_result["style_score"]), 3),
            "metadata_score": round(float(metadata_result["metadata_score"]), 3),
        },
        "llm_score": round(float(groq_result["groq_score"]), 3),
        "style_score": round(float(style_result["style_score"]), 3),
        "metadata_score": round(float(metadata_result["metadata_score"]), 3),
        "status": "classified",
        "explanation": groq_result["explanation"],
        "appeal_available": True,
    }
    return jsonify(response), 200


@api.route("/appeal", methods=["POST"])
@limiter.limit("5 per hour")
def appeal():
    payload = request.get_json(silent=True) or {}
    content_id = payload.get("content_id")
    creator_reasoning = payload.get("creator_reasoning")
    creator_id = payload.get("creator_id") or payload.get("requester_name") or ""

    if not isinstance(content_id, str) or not content_id.strip():
        return jsonify({"error": "content_id is required"}), 400
    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return jsonify({"error": "creator_reasoning is required"}), 400

    original_entry = get_latest_entry(content_id.strip())
    if original_entry is None:
        return jsonify({"error": "content_id not found"}), 404

    appeal_id = str(uuid4())
    appeal_entry = {
        "appeal_id": appeal_id,
        "content_id": content_id.strip(),
        "creator_id": creator_id,
        "creator_reasoning": creator_reasoning.strip(),
        "timestamp": make_timestamp(),
        "attribution": original_entry.get("attribution", "under_review"),
        "confidence": original_entry.get("confidence", 0.0),
        "llm_score": original_entry.get("llm_score", 0.0),
        "style_score": original_entry.get("style_score", 0.0),
        "combined_ai_score": original_entry.get("combined_ai_score", 0.0),
        "status": "under_review",
        "appeal_reasoning": creator_reasoning.strip(),
        "appeal_filed": True,
        "original_decision": original_entry,
    }
    append_appeal_entry(appeal_entry)

    return jsonify({
        "appeal_id": appeal_id,
        "content_id": content_id.strip(),
        "status": "under_review",
        "message": "Appeal received and marked under review.",
    }), 200


@api.route("/certificate", methods=["POST"])
@limiter.limit("5 per hour")
def certificate():
    payload = request.get_json(silent=True) or {}
    content_id = payload.get("content_id")
    certificate_code = payload.get("certificate_code")

    if not isinstance(content_id, str) or not content_id.strip():
        return jsonify({"error": "content_id is required"}), 400
    if not isinstance(certificate_code, str) or not certificate_code.strip():
        return jsonify({"error": "certificate_code is required"}), 400

    original_entry = get_latest_entry(content_id.strip())
    if original_entry is None:
        return jsonify({"error": "content_id not found"}), 404

    expected_code = str(original_entry.get("certificate_code", ""))
    if certificate_code.strip().upper() != expected_code:
        return jsonify({"error": "certificate_code does not match"}), 400

    verified_entry = {
        "content_id": content_id.strip(),
        "creator_id": original_entry.get("creator_id", ""),
        "timestamp": make_timestamp(),
        "attribution": original_entry.get("attribution", "uncertain"),
        "confidence": original_entry.get("confidence", 0.0),
        "llm_score": original_entry.get("llm_score", 0.0),
        "style_score": original_entry.get("style_score", 0.0),
        "metadata_score": original_entry.get("metadata_score", 0.0),
        "combined_ai_score": original_entry.get("combined_ai_score", 0.0),
        "status": "verified",
        "certificate_verified": True,
        "certificate_label": "Verified provenance certificate",
        "original_decision": original_entry,
    }
    insert_audit_entry(verified_entry)

    return jsonify({
        "content_id": content_id.strip(),
        "status": "verified",
        "certificate_label": "Verified provenance certificate",
        "message": "Certificate verified and added to the audit trail.",
    }), 200


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


@api.route("/analytics", methods=["GET"])
def analytics():
    entries = list_all_audit_entries()
    latest_by_content = {}
    for entry in entries:
        content_id = entry.get("content_id")
        if content_id and content_id not in latest_by_content:
            latest_by_content[content_id] = entry

    current_entries = list(latest_by_content.values())
    total = len(current_entries)
    ai_likely = sum(1 for entry in current_entries if entry.get("attribution") == "likely_ai")
    human_likely = sum(1 for entry in current_entries if entry.get("attribution") == "likely_human")
    uncertain = sum(1 for entry in current_entries if entry.get("attribution") == "uncertain")
    appeal_count = sum(1 for entry in current_entries if entry.get("status") == "under_review")
    average_confidence = sum(float(entry.get("confidence", 0.0)) for entry in current_entries) / total if total else 0.0

    return jsonify({
        "total_contents": total,
        "ai_likely": ai_likely,
        "human_likely": human_likely,
        "uncertain": uncertain,
        "appeal_rate": round(appeal_count / total, 3) if total else 0.0,
        "average_confidence": round(average_confidence, 3),
    }), 200
