# Customer-success assistant — H Company Computer-Use Hackathon

A desktop app that helps a user get a result inside their software through H's computer-use, acts only
with the user's approval, verifies the outcome, and hands a structured case to the vendor's support when
it is blocked. Full product spec: [PRD.md](PRD.md).

## Repository layout

```
.
├── PRD.md               product requirements (source of truth for scope)
├── AGENTS.md            team conventions: branches, tooling, contract ownership
├── contracts/           JSON Schemas shared by the three components (generated, do not hand-edit)
├── agent/               Python — H desktop agent, local API for the app          (Matteo)
├── app/                 Electron — user app: request, approval, progress, stop   (Edouard)
├── backend/             Python — support backend: cases, escalation, dashboard   (Tom)
├── docs/                scenario notes, demo checklist, test logs
└── scripts/             demo data preparation / reset (never part of the shown run)
```

## Who owns what

| Area | Owner | Deliverable |
| --- | --- | --- |
| `agent/` | Matteo | Real execution through H, procedures, verification, local stop, structured report |
| `app/` | Edouard | Request, role, consent, progress, stop, result, feedback; drives the first full run |
| `backend/` | Tom | Storage, escalation case file, dashboard, simple grouping, demo data |
| `contracts/` | Matteo (generated from `agent/src/hcs_agent/contract.py`) | Changes are proposed in a PR and announced to the team |

## Quick start

```bash
# Python parts (agent, backend) use uv; one workspace at the root
uv sync --all-packages               # one .venv at the root with every Python member
uv run --package hcs-agent hcs-agent --help
uv run pytest                        # all Python tests

# Electron app
cd app && npm install && npm run dev
```

Secrets go in `.env` files that are git-ignored (`agent/.env`, `backend/.env`). Never commit an H API key.

## Demo scenario (proposal, Odoo)

Success case: a new sales rep asks to schedule the follow-up on the opportunity "Acme Demo"; the assistant
explains, gets approval, creates a To Do activity and verifies it on the reopened record.
Blocked case: the user asks for an action their rights do not allow; the agent recognises the access error,
does not retry, and escalates a case file with the decision expected from support.

## Shared contract in one line

A request carries `session_id, software, role, goal, procedure_id, parameters`. Commands are
`approve`, `stop`, `feedback`. Events expose `state`, `step`s, `needs_human`, `finished`. The report
separates the agent's **declared** result from the **verified** postcondition, and carries
`category`, `status`, `escalation`, `evidence`, `feedback`. Schemas: [`contracts/`](contracts/).
