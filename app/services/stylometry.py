from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class StylometryResult:
    style_score: float
    metrics: dict[str, Any]
    explanation: str
    provider: str
    latency_ms: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _split_sentences(text: str) -> list[str]:
    sentences = [sentence.strip() for sentence in re.split(r"[.!?]+", text) if sentence.strip()]
    return sentences or ([text.strip()] if text.strip() else [])


def _extract_words(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def score_with_stylometry(text: str) -> dict[str, Any]:
    started_at = time.perf_counter()
    stripped = text.strip()
    words = _extract_words(stripped)
    sentences = _split_sentences(stripped)
    word_count = len(words)
    sentence_count = len(sentences)

    if word_count < 30 or sentence_count < 2:
        return StylometryResult(
            style_score=0.5,
            metrics={
                "word_count": word_count,
                "sentence_count": sentence_count,
                "avg_sentence_length": float(word_count) if sentence_count else 0.0,
                "sentence_length_stdev": 0.0,
                "sentence_length_cv": 0.0,
                "lexical_diversity": len(set(words)) / word_count if word_count else 0.0,
                "punctuation_density": sum(1 for char in stripped if char in ",:;-()[]\"—") / max(1, len(stripped)),
                "avg_clause_complexity": 0.0,
                "repetition_rate": 0.0,
                "low_reliability": True,
            },
            explanation="Text is too short for reliable stylometric scoring.",
            provider="local",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        ).as_dict()

    sentence_lengths = [len(_extract_words(sentence)) for sentence in sentences if sentence]
    avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths)
    variance = sum((length - avg_sentence_length) ** 2 for length in sentence_lengths) / len(sentence_lengths)
    sentence_length_stdev = variance ** 0.5
    sentence_length_cv = sentence_length_stdev / avg_sentence_length if avg_sentence_length else 0.0

    unique_ratio = len(set(words)) / word_count if word_count else 0.0
    punctuation_density = sum(1 for char in stripped if char in ",:;-()[]\"—") / max(1, len(stripped))
    clause_markers = re.findall(r"\b(and|but|or|while|because|however|though|although|since|if|yet|so)\b", stripped, re.I)
    avg_clause_complexity = len(clause_markers) / sentence_count if sentence_count else 0.0

    repeated_bigrams = 0
    bigrams: list[tuple[str, str]] = []
    for index in range(len(words) - 1):
        bigrams.append((words[index], words[index + 1]))
    if bigrams:
        repeated_bigrams = len(bigrams) - len(set(bigrams))
    repetition_rate = repeated_bigrams / max(1, len(bigrams))

    rhythm_ai = _clamp(1.0 - min(sentence_length_cv / 1.0, 1.0))
    length_ai = _clamp((avg_sentence_length - 8.0) / 16.0)
    diversity_ai = _clamp(1.0 - min(abs(unique_ratio - 0.72) / 0.28, 1.0))
    punctuation_ai = _clamp(1.0 - min(abs(punctuation_density - 0.02) / 0.02, 1.0))
    clause_ai = _clamp(min(avg_clause_complexity / 1.2, 1.0))
    repetition_ai = _clamp(min(repetition_rate / 0.15, 1.0))
    compact_paragraph_ai = 1.0 if sentence_count <= 3 and word_count >= 35 else 0.0

    style_score = _clamp(
        0.30 * rhythm_ai
        + 0.20 * length_ai
        + 0.15 * diversity_ai
        + 0.15 * punctuation_ai
        + 0.10 * clause_ai
        + 0.10 * repetition_ai
        + 0.15 * compact_paragraph_ai
    )

    return StylometryResult(
        style_score=style_score,
        metrics={
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": avg_sentence_length,
            "sentence_length_stdev": sentence_length_stdev,
            "sentence_length_cv": sentence_length_cv,
            "lexical_diversity": unique_ratio,
            "punctuation_density": punctuation_density,
            "avg_clause_complexity": avg_clause_complexity,
            "repetition_rate": repetition_rate,
            "rhythm_ai": rhythm_ai,
            "length_ai": length_ai,
            "diversity_ai": diversity_ai,
            "punctuation_ai": punctuation_ai,
            "clause_ai": clause_ai,
            "repetition_ai": repetition_ai,
            "compact_paragraph_ai": compact_paragraph_ai,
            "low_reliability": False,
        },
        explanation="Stylometric heuristic score computed from sentence rhythm, diversity, punctuation, and repetition.",
        provider="local",
        latency_ms=int((time.perf_counter() - started_at) * 1000),
    ).as_dict()