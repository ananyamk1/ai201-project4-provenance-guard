# Provenance Guard Planning

## Detection Signals

### Signal 1: Groq LLM classifier

- Measures: semantic coherence, tonal consistency, and whether the writing reads like a single human voice or model-generated prose.
- Output: `groq_score` from `0.0` to `1.0`, where `1.0` means more AI-like.
- Why it differs: AI text often has smooth transitions, evenly distributed tone, and fewer localized quirks than human writing.
- Blind spot: polished human writing, heavily edited drafts, and very short samples can look AI-like; prompt-sensitive outputs can also swing the score.

### Signal 2: Stylometric heuristics

- Measures: sentence-length variance, lexical diversity, punctuation density, average clause complexity, and repetition patterns.
- Output: `style_score` from `0.0` to `1.0`, where `1.0` means more AI-like.
- Why it differs: human writing usually has more irregular rhythm, more varied punctuation, and more uneven sentence structure than typical AI text.
- Blind spot: template-based business writing, technical documentation, legal boilerplate, and carefully edited human prose can look machine-like.

### Combination rule

- Normalize both signals to the same `0.0` to `1.0` AI-likeness scale.
- Compute `combined_ai_score = 0.60 * groq_score + 0.40 * style_score`.
- Compute `confidence = abs(combined_ai_score - 0.5) * 2` so `0.0` means maximally uncertain and `1.0` means strongly one-sided.
- Apply a disagreement penalty when the signals diverge sharply: if `abs(groq_score - style_score) > 0.35`, subtract `0.10` from `combined_ai_score` before clamping to `[0.0, 1.0]`.

## Uncertainty Representation

- A confidence score of `0.6` means the system has a moderate but not decisive preference for one side; it is not a binary yes/no result.
- The score is calibrated from the combined AI-likeness estimate, not from raw classifier output alone.
- Thresholds:
    - `combined_ai_score >= 0.70` and `confidence >= 0.40` -> likely AI.
    - `combined_ai_score <= 0.30` and `confidence >= 0.40` -> likely human.
    - Anything in between, or any case with low confidence, -> uncertain.
- Borderline cases stay uncertain even if one signal is slightly above or below `0.5`; the system should not flip labels on tiny differences.

## Transparency Labels

- High-confidence AI: `Likely AI-generated. This submission matches multiple machine-writing patterns.`
- High-confidence human: `Likely human-written. This submission does not resemble common AI generation patterns.`
- Uncertain: `Uncertain. The signals disagree or the text is too short to judge reliably.`

The API returns the raw `combined_ai_score`, the derived `confidence`, and the human-readable label string together so the label can be explained, not just displayed.

## Appeals Workflow

- Who can appeal: the original submitter or creator of the submission, using the `submission_id` returned by `POST /submit`.
- What they provide: `submission_id`, `reason`, and a requester identifier such as `creator_id` or `requester_name`.
- What happens on receipt:
    - create an appeal record with a timestamp,
    - set the submission status to `appeal_pending`,
    - preserve the original detection outputs,
    - append an audit-log entry with the appeal reason and requester metadata.
- What a human reviewer sees:
    - submission id and title, if present,
    - submitted text or excerpt,
    - Groq score, stylometric score, combined AI score, and confidence,
    - the original label text,
    - appeal reason and requester metadata,
    - appeal timestamp and current status.

The appeal does not overwrite the original verdict. It creates a traceable review state so a reviewer can see both the decision and the challenge.

## Anticipated Edge Cases

- Short headlines, social captions, and very short bios: the sample is too small for stylometry to stabilize, so the system may over-rely on a few surface cues.
- Template-heavy professional writing, such as status updates, cover letters, or policy memos: the writing can look uniform even when a human wrote it.
- Heavily edited human prose: revision can remove the quirks that the signals depend on, making the text look more AI-like.
- Quoted dialogue, transcripts, or list-heavy content: punctuation and sentence-length metrics can become misleading because the structure is driven by formatting rather than authorship.

## API Surface

### `POST /submit`

Accepts:
- `text`: required raw submission text.
- `creator_id` or `source_id`: optional traceability field.
- `title`: optional display title.

Returns:
- `submission_id`
- `label`
- `label_text`
- `combined_ai_score`
- `confidence`
- `signal_scores`
- `appeal_available`
- `explanation`

### `POST /appeal`

Accepts:
- `submission_id`
- `reason`
- `creator_id` or `requester_name`

Returns:
- `appeal_id`
- `submission_id`
- `status`
- `message`

### `GET /submission/<id>`

Returns the stored submission, both signal outputs, combined score, label text, and current appeal status.

### `GET /audit/<id>`

Returns the audit trail for a submission or appeal.

### `GET /health`

Returns a simple service health response.

## Architecture

```text
Submission flow

POST /submit
    -> validate + normalize text
    -> Groq classifier (raw text -> groq_score)
    -> stylometric heuristics (raw text -> style_score)
    -> score combiner (groq_score + style_score -> combined_ai_score + confidence)
    -> label mapper (combined_ai_score + confidence -> label_text)
    -> audit log (request + scores + label + timestamp)
    -> response (submission_id + label + label_text + scores)

Appeal flow

POST /appeal
    -> validate submission_id + reason
    -> status updater (submission -> appeal_pending)
    -> audit log (appeal request + requester + timestamp)
    -> response (appeal_id + status + message)
```

The submission path keeps detection separate from presentation: raw text is analyzed by two independent signals, combined into a calibrated AI-likeness score, mapped to a user-facing label, and written to the audit log. The appeal path does not change the original detection result; it records a review request, updates status, and preserves the full provenance trail for a human reviewer.

## AI Tool Plan

### M3: submission endpoint + first signal

- Provide to the AI tool: the `Detection Signals` section and the `Architecture` section.
- Ask it to generate: the Flask app skeleton, `POST /submit`, request validation, and the Groq classifier wrapper as the first signal function.
- Verify by: calling the signal function directly on a few clearly human and clearly AI-like texts before wiring the result into the endpoint.

### M4: second signal + confidence scoring

- Provide to the AI tool: the `Detection Signals`, `Uncertainty Representation`, and `Architecture` sections.
- Ask it to generate: the stylometric signal function, the weighted combination logic, the confidence calculation, and the score-to-label mapping helpers.
- Verify by: comparing outputs on clearly human, clearly AI, and mixed texts to confirm the scores vary meaningfully and that borderline samples land in the uncertain band.

### M5: production layer

- Provide to the AI tool: the `Transparency Labels`, `Appeals Workflow`, and `Architecture` sections.
- Ask it to generate: label-generation logic, the `POST /appeal` endpoint, audit-log updates, and status transitions for appealed submissions.
- Verify by: exercising all three label variants and confirming that an appeal changes status to `appeal_pending` without overwriting the original label or scores.

## Implementation Notes

- Keep the two signals independent so one can drift without breaking the other.
- Preserve raw inputs and intermediate outputs in the audit trail for explainability.
- Use conservative label wording so the system communicates uncertainty instead of certainty.
- Prefer a thin HTTP layer over logic in route handlers so detection and appeal handling stay testable.
