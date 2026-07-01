# ai201-project4-provenance-guard

Provenance Guard is a Flask-based service that labels text submissions with a transparency score, records an audit trail, and supports appeals.

Core design:
- Two independent detection signals: a Groq-based LLM classifier and stylometric heuristics.
- Submission flow: `POST /submit` -> detection -> composite score -> label -> audit log -> response.
- Appeal flow: `POST /appeal` -> status update -> audit log -> response.

Production notes:
- `POST /submit` is rate-limited to `10 per minute;100 per day` per IP.
- `POST /appeal` is rate-limited to `5 per hour` per IP.
- Appeals accept `content_id` and `creator_reasoning`, update the stored status to `under_review`, and append an immutable audit entry with the original decision snapshot.
- The audit log is structured JSON stored in SQLite and includes timestamp, content ID, attribution, confidence, both signal scores, and appeal metadata.

Rate-limit test evidence:
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

See [planning.md](planning.md) for the full architecture narrative, signal tradeoffs, API contract, and flow diagram.
