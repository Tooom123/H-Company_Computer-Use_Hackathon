# hcs-backend (Tom)

Receives `InterventionReport`s (see `contracts/InterventionReport.schema.json`), stores cases, builds the
escalation file for support, groups similar difficulties and serves an authenticated dashboard.

Expected inputs from the agent: `POST /cases` with an `InterventionReport`; optional `POST /events` with
`AgentEvent`s for live follow-up. Every record keeps `simulated` and `demo_data` flags.

```bash
uv sync --all-packages                   # at repo root
uv run --package hcs-backend hcs-backend
uv run pytest backend
```
