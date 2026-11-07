# hcs-backend (Tom)

Receives `InterventionReport`s from the agent, stores cases, builds the escalation file for support, groups
similar difficulties and serves an authenticated dashboard. Reports are validated against
`contracts/*.schema.json` (no duplicated models) and stored verbatim in SQLite (`runs/`, git-ignored).

```bash
uv sync --all-packages                         # at repo root
cp backend/.env.example backend/.env           # set HCS_INGEST_TOKEN and HCS_DASHBOARD_PASSWORD
.venv/bin/hcs-backend seed-demo --reset        # 4 demo cases, flagged demo_data + simulated
.venv/bin/hcs-backend serve                    # http://127.0.0.1:8766/dashboard
.venv/bin/hcs-backend reset-demo               # remove demo cases only
uv run pytest backend
```

## API

| Auth | Method | Path | Purpose |
| --- | --- | --- | --- |
| — | GET | `/health` | liveness |
| Bearer `HCS_INGEST_TOKEN` | POST | `/cases` | `InterventionReport` → `{case_id, created, group_id, needs_escalation}`. Same `case_id` again replaces the case (e.g. after feedback). Optional header `X-HCS-User`: pseudonymous user ref for "distinct users". |
| Bearer | POST | `/events` | `AgentEvent`, stored per session for live follow-up |
| Basic (support) | GET | `/cases`, `/cases/{id}` | stored cases with their group |
| Basic | GET | `/cases/{id}/escalation` · `.md` | escalation file, JSON or Markdown |
| Basic | GET | `/groups`, `/groups/{id}` | difficulty groups with source cases |
| Basic | GET | `/sessions/{id}/events` | events of a session |
| Basic | GET | `/dashboard`, `/dashboard/groups/{id}`, `/dashboard/cases/{id}` | HTML dashboard |

Invalid payloads get a 422 listing the schema errors.

## Rules implemented (from the PRD)

- **Grouping**: same software and same category, then Jaccard ≥ 0.3 on keywords of the blocker, suspected
  cause and symptom (goal if none) plus the procedure id. Two similar cases share a group, a different one
  stays distinct, every group lists its source cases.
- **Escalation file**: decision expected, blocked on, attempts, suspected cause (labelled hypothesis),
  steps attempted. User-declared, agent-declared and observed facts stay in separate sections.
- **Consent**: a screenshot is shown to support only if the evidence is `shareable_with_support` and the
  user's feedback has `allow_screenshots_to_support`; withheld screenshots are counted, not shown.
- **Flags**: `simulated` and `demo_data` are displayed on every case and group.
- **Access**: no unauthenticated read of cases; the agent and support use separate secrets.
