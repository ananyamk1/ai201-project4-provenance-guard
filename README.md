# ai201-project4-provenance-guard

Provenance Guard is a Flask-based service that labels text submissions with a transparency score, records an audit trail, and supports appeals.

Core design:
- Two independent detection signals: a Groq-based LLM classifier and stylometric heuristics.
- Submission flow: `POST /submit` -> detection -> composite score -> label -> audit log -> response.
- Appeal flow: `POST /appeal` -> status update -> audit log -> response.

See [planning.md](planning.md) for the full architecture narrative, signal tradeoffs, API contract, and flow diagram.
