from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MetadataSignalResult:
    metadata_score: float
    metrics: dict[str, Any]
    explanation: str
    provider: str
    latency_ms: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def score_with_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    started_at = time.perf_counter()
    title = str(metadata.get("title", "")).strip()
    description = str(metadata.get("description") or metadata.get("caption") or metadata.get("alt_text") or "").strip()
    tags = metadata.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(tag).strip().lower() for tag in tags if str(tag).strip()]

    field_count = sum(1 for value in [title, description, metadata.get("source"), metadata.get("content_type")] if value)
    tag_count = len(tags)
    description_words = len(description.split())
    title_words = len(title.split())
    completeness = _clamp(field_count / 4.0)
    tag_richness = _clamp(tag_count / 6.0)
    description_balance = _clamp(1.0 - abs(description_words - 18) / 18.0) if description_words else 0.0
    title_balance = _clamp(1.0 - abs(title_words - 6) / 6.0) if title_words else 0.0
    repetition = 0.0 if len(set(tags)) == tag_count else 0.25

    metadata_score = _clamp(
        0.30 * completeness
        + 0.25 * tag_richness
        + 0.25 * description_balance
        + 0.15 * title_balance
        + 0.05 * repetition
    )

    return MetadataSignalResult(
        metadata_score=metadata_score,
        metrics={
            "field_count": field_count,
            "tag_count": tag_count,
            "description_words": description_words,
            "title_words": title_words,
            "completeness": completeness,
            "tag_richness": tag_richness,
            "description_balance": description_balance,
            "title_balance": title_balance,
            "repetition": repetition,
        },
        explanation="Structured metadata score computed from field completeness, tag richness, and description balance.",
        provider="local",
        latency_ms=int((time.perf_counter() - started_at) * 1000),
    ).as_dict()