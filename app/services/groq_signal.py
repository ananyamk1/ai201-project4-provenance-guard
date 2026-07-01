from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from groq import Groq


@dataclass
class GroqSignalResult:
    groq_score: float
    model: str
    prompt_version: str
    explanation: str
    raw_label: str
    raw_response: dict[str, Any]
    latency_ms: int
    provider: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


PROMPT_VERSION = "v1"
DEFAULT_MODEL = "llama3-70b-8192"
SUPPORTED_MODELS = {"gemma-7b-it", "llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768"}


def _local_fallback_score(text: str) -> tuple[float, str]:
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.5, "uncertain"

    sentence_count = max(1, len(re.findall(r"[.!?]+", text)) or 1)
    avg_sentence_length = len(words) / sentence_count
    unique_ratio = len(set(words)) / len(words)
    punctuation_chars = set(",:;-()[]\"")
    punctuation_density = sum(1 for char in text if char in punctuation_chars) / max(1, len(text))

    ai_likeness = 0.45
    if avg_sentence_length > 22:
        ai_likeness += 0.15
    if unique_ratio < 0.55:
        ai_likeness += 0.15
    if punctuation_density < 0.02:
        ai_likeness += 0.10
    if len(words) < 40:
        ai_likeness -= 0.10

    ai_likeness = max(0.0, min(1.0, ai_likeness))
    label = "likely_ai" if ai_likeness >= 0.65 else "likely_human" if ai_likeness <= 0.35 else "uncertain"
    return ai_likeness, label



def _parse_json_response(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        score_match = re.search(r"(?:score|ai_score)\s*[:=]\s*(0(?:\.\d+)?|1(?:\.0+)?)", content, re.I)
        label_match = re.search(r"(likely_ai|likely_human|uncertain)", content, re.I)
        score = float(score_match.group(1)) if score_match else 0.5
        label = label_match.group(1).lower() if label_match else "uncertain"
        return {"groq_score": score, "raw_label": label, "explanation": content.strip()}



def score_with_groq(text: str, *, model: str | None = None, temperature: float = 0.0) -> dict[str, Any]:
    started_at = time.perf_counter()
    requested_model = model or os.getenv("GROQ_MODEL") or DEFAULT_MODEL
    selected_model = requested_model if requested_model in SUPPORTED_MODELS else DEFAULT_MODEL
    client = Groq(api_key=os.getenv("GROQ_API_KEY")) if Groq and os.getenv("GROQ_API_KEY") else None

    if client is None:
        score, label = _local_fallback_score(text)
        return GroqSignalResult(
            groq_score=score,
            model=selected_model,
            prompt_version=PROMPT_VERSION,
            explanation="Groq API key not configured; using local fallback assessment.",
            raw_label=label,
            raw_response={"fallback": True},
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            provider="fallback",
        ).as_dict()

    prompt = (
        "Assess whether the following text is more likely human-written or AI-generated. "
        "Return JSON with keys groq_score (0 to 1 where 1 is more AI-like), raw_label, and explanation.\n\n"
        f"TEXT:\n{text}"
    )
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": "You are a provenance classification assistant that returns strict JSON."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        payload = _parse_json_response(content)
        score = float(payload.get("groq_score", 0.5))
        label = str(payload.get("raw_label", "uncertain"))
        explanation = str(payload.get("explanation", ""))
        raw_response = {"content": content, "parsed": payload}
        provider = "groq"
    except Exception as error:  # pragma: no cover - provider fallback path
        score, label = _local_fallback_score(text)
        explanation = f"Groq request failed; using local fallback assessment: {error}"
        raw_response = {"fallback": True, "error": str(error)}
        provider = "fallback"

    return GroqSignalResult(
        groq_score=max(0.0, min(1.0, score)),
        model=selected_model,
        prompt_version=PROMPT_VERSION,
        explanation=explanation,
        raw_label=label,
        raw_response=raw_response,
        latency_ms=int((time.perf_counter() - started_at) * 1000),
        provider=provider,
    ).as_dict()
