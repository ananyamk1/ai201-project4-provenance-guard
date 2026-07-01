from __future__ import annotations

from typing import Any


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def combine_signal_scores(groq_score: float, style_score: float) -> dict[str, Any]:
    combined_ai_score = 0.60 * groq_score + 0.40 * style_score
    disagreement_delta = 0.0
    disagreement_penalty_applied = False

    if abs(groq_score - style_score) > 0.35:
        combined_ai_score -= 0.10
        disagreement_delta = 0.10
        disagreement_penalty_applied = True

    combined_ai_score = _clamp(combined_ai_score)
    confidence = abs(combined_ai_score - 0.5) * 2

    if combined_ai_score >= 0.70 and confidence >= 0.40:
        label = "likely_ai"
        label_text = "Likely AI-generated. This submission matches multiple machine-writing patterns."
    elif combined_ai_score <= 0.30 and confidence >= 0.40:
        label = "likely_human"
        label_text = "Likely human-written. This submission does not resemble common AI generation patterns."
    else:
        label = "uncertain"
        label_text = "Uncertain. The signals disagree or the text is too short to judge reliably."

    return {
        "groq_score": groq_score,
        "style_score": style_score,
        "combined_ai_score": combined_ai_score,
        "confidence": confidence,
        "label": label,
        "label_text": label_text,
        "disagreement_penalty_applied": disagreement_penalty_applied,
        "disagreement_delta": disagreement_delta,
    }