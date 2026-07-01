# ai201-project4-provenance-guard

Provenance Guard is a Flask service that scores text submissions for AI-likeness, writes a structured audit trail, and supports creator appeals. The system is intentionally conservative: it uses two signals, a calibrated confidence score, and human-readable labels that surface uncertainty instead of pretending the result is absolute.

## Architecture

The submission flow starts at `POST /submit`. The app validates the text and creator id, runs the Groq-based signal, runs the stylometric signal, combines the two scores into a single AI-likeness value, maps that result to a label, and writes the entire decision to the audit log. The appeal flow starts at `POST /appeal`. A creator provides `content_id` and `creator_reasoning`, the system marks the item `under_review`, and the appeal is appended to the audit log with the original decision snapshot preserved.

This separation matters. The routes stay thin, the scoring logic stays testable, and the log remains the source of truth for what happened to a submission over time.

```text
Submission flow

POST /submit
	-> validate + normalize text
	-> Groq classifier (raw text -> groq_score)
	-> stylometric heuristics (raw text -> style_score)
	-> score combiner (groq_score + style_score -> combined_ai_score + confidence)
	-> label mapper (combined_ai_score + confidence -> label_text)
	-> audit log (request + scores + label + timestamp)
	-> response (content_id + label + label_text + scores)

Appeal flow

POST /appeal
	-> validate content_id + creator_reasoning
	-> status updater (submission -> under_review)
	-> audit log (appeal request + original decision snapshot)
	-> response (appeal_id + status + message)
```

## Detection Signals

### Signal 1: Groq LLM classifier

This signal measures semantic and stylistic coherence: whether the text feels like one consistent voice, or whether it has the smooth, over-regular tone that often appears in machine-written prose. It returns a `groq_score` from `0.0` to `1.0`, where `1.0` means more AI-like.

Why this signal: it captures semantic structure that simple heuristics miss. A model can spot polished transitions, generic phrasing, and overly even tone better than a hand-built rule set can.

What it misses: polished human writing can look AI-like, short samples are noisy, and the output depends on the model prompt and the provider’s current behavior. If this were production, I would replace the current fallback-heavy setup with a stable, versioned classifier and a calibration set.

### Signal 2: Stylometric heuristics

This signal measures sentence rhythm, lexical diversity, punctuation density, clause regularity, repetition, and paragraph compactness. It returns a `style_score` from `0.0` to `1.0`, where `1.0` means more AI-like.

Why this signal: human writing usually varies more in rhythm and punctuation, while machine-generated prose often becomes more uniform and compact. Stylometry gives a cheap second view that is independent from the LLM judgment.

What it misses: formal human writing, edited drafts, templates, and technical prose can look mechanically regular even when people wrote them. In real deployment, I would tune this against a larger, labeled dataset and likely add document-length normalization.

### Signal 3: Structured metadata signal

This signal measures how complete and internally consistent the structured metadata is: title length, description balance, tag richness, and field completeness. It returns a `metadata_score` from `0.0` to `1.0`, where `1.0` means more AI-like.

Why this signal: it gives the ensemble a third, distinct view that is based on structure rather than prose alone. That helps when the submission is not pure text, such as an image description or a structured metadata payload.

What it misses: a carefully prepared human submission can still look highly structured, and sparse metadata can be noisy. In production I would calibrate it against actual submission metadata rather than the synthetic fields used here.

## Ensemble Detection

The ensemble combines three signals:

- Groq LLM classifier: `45%`
- Stylometric heuristics: `35%`
- Structured metadata signal: `20%`

The signals are combined into one AI-likeness score. If any pair of signals disagrees by more than `0.35`, the combined score gets a `0.10` penalty before clamping. That keeps one signal from dominating when the others strongly disagree.

The submission response shows all three signal scores alongside the combined result, so the ensemble is visible rather than hidden.

## Confidence Scoring

The combined score follows the spec directly:

- `combined_ai_score = 0.60 * groq_score + 0.40 * style_score`
- If `abs(groq_score - style_score) > 0.35`, subtract `0.10` before clamping.
- `confidence = abs(combined_ai_score - 0.5) * 2`
- Likely AI only when `combined_ai_score >= 0.70` and `confidence >= 0.40`
- Likely human only when `combined_ai_score <= 0.30` and `confidence >= 0.40`
- Everything else is uncertain

That gives the system three behaviors instead of a binary flip at `0.5`. A score near `0.5` stays uncertain even if one signal is slightly above the other, which is what I wanted for a false-positive-prone problem.

Two examples from the calibration run:

- High-confidence case: the clearly human sample returned `combined_ai_score = 0.222` and `confidence = 0.556`, which mapped to `Likely human-written. This submission does not resemble common AI generation patterns.`
- Lower-confidence case: the borderline edited sample returned `combined_ai_score = 0.488` and `confidence = 0.024`, which stayed `Uncertain. The signals disagree or the text is too short to judge reliably.`

Those two examples show the score is not constant and that the confidence band changes the label instead of just echoing the raw score.

## Transparency Labels

The submission endpoint returns one of these exact label texts:

- High-confidence AI: `Likely AI-generated. This submission matches multiple machine-writing patterns.`
- High-confidence human: `Likely human-written. This submission does not resemble common AI generation patterns.`
- Uncertain: `Uncertain. The signals disagree or the text is too short to judge reliably.`

The label is deliberately phrased as guidance, not proof. That wording is part of the safety story: the system should help a reviewer or creator understand the signal, not accuse them of authorship with false certainty.

## Appeals Workflow

Appeals are filed by the original creator or submitter. The endpoint accepts `content_id` and `creator_reasoning`, plus optional creator identity metadata when available. On receipt, the system looks up the original decision, appends a new audit entry, and marks the item `under_review`.

The reviewer-facing record includes the content id, original attribution, confidence, both signal scores, the original decision snapshot, the appeal reasoning, and the new `under_review` state. I kept the workflow append-only so the original classification remains visible and the appeal is traceable instead of destructive.

## Provenance Certificate

The app issues a lightweight provenance certificate code with each submission. A creator verifies the certificate by POSTing the `content_id` and matching `certificate_code` back to the API. That verification step records a separate audit entry with the label `Verified provenance certificate` so it is visibly different from the standard transparency label.

This is intentionally simple: the project is demonstrating the workflow and the visible verified state, not building a production-grade identity system.

## Rate Limiting

`Flask-Limiter` is enabled with in-memory storage for local development.

- `POST /submit`: `10 per minute;100 per day`
- `POST /appeal`: `5 per hour`

Those limits are conservative enough to block simple flooding while still allowing a real writer to test a few drafts and file a reasonable appeal.

Rate-limit evidence from the live test run:

```text
200
200
200
200
200
200
200
429
429
429
429
429
```

## Audit Log

The audit log is structured JSON stored in SQLite. Each submission entry records:

- timestamp
- content id
- creator id
- attribution
- confidence
- both signal scores
- combined score
- status
- appeal metadata when present

I verified the log contains at least three structured entries and at least one appeal entry. Because the log is append-only, it works as a timeline rather than a single mutable status field.

## Analytics Dashboard

The project includes a lightweight analytics view at `GET /analytics`. It summarizes the current audit log with:

- the number of contents currently labeled likely AI, likely human, and uncertain
- appeal rate across the current contents
- average confidence

This is a JSON dashboard rather than a chart UI, but it still exposes the operational picture the rubric asks for: how often the system is leaning AI, how often creators appeal, and how confident the system is overall.

## Multi-Modal Support

The submission endpoint accepts `content_type: "metadata"` plus a structured `metadata` object for non-text content. The pipeline converts that payload into a canonical summary string for the text-based signals and also runs the structured metadata signal directly on the JSON fields. That keeps the same attribution pipeline usable for image descriptions or other structured content.

In other words, the multimodal path still ends in the same ensemble result, but it feeds the signals differently: text goes through the prose-based signals, while structured metadata also contributes its own score.

## Known Limitations

This system will likely struggle with formal human writing such as academic prose, policy memos, and edited essays. Those texts can look compact, coherent, and low-variance, which pushes both the LLM signal and the stylometric signal toward AI-like outputs.

It will also underperform on very short texts. Short captions, headlines, and brief replies do not give the stylometric heuristics enough material to measure rhythm or lexical variety, so the system has to stay cautious.

## Spec Reflection

The spec helped most by forcing the score thresholds and label texts to be concrete before I wrote code. That kept the system from drifting into a vague binary classifier and made the later UI and audit-log work much easier to reason about.

The main implementation divergence was the Groq integration. The installed Groq client and the current model deprecation state meant I had to keep a local fallback path so the app remained runnable and testable. I kept the spec’s scoring shape intact, but the provider call path is more defensive than the ideal production version would be.

## AI Usage

I used AI tools in at least two specific ways.

First, I asked for a Milestone 3 Flask skeleton plus the first Groq signal. The draft got the route structure and response shape right, but I revised it to fit this repo’s SQLite log and to avoid hard failure when the Groq model was unavailable.

Second, I asked for a Milestone 4 stylometric signal and confidence combiner. The draft gave me the right separation of concerns and the right score formula, but I tuned the feature weights and the score shaping by hand so the four test inputs separated into likely AI, likely human, and uncertain.

I also used an AI tool to draft the appeal workflow. That was useful for the endpoint contract, but I overrode the storage behavior so the audit log stayed append-only and captured the original classification decision alongside the appeal.

## Run It Locally

```bash
pip install -r requirements.txt
python run.py
```

Then submit text with `POST /submit`, inspect `GET /log`, and file an appeal with `POST /appeal`.

See [planning.md](planning.md) for the full architecture narrative, signal tradeoffs, API contract, and flow diagram.
