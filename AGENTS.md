# Team conventions

Read this before pushing. It applies to humans and coding agents alike.

## Notes from teammates (read first)

- [docs/notes-for-agents-from-tom.md](docs/notes-for-agents-from-tom.md): contract regeneration, missing report
  fields (autonomy, takeover), support uplink, gaze halo, Odoo reset, Devin auto-fix.

## Branches

- `main` is always runnable. Nobody pushes directly after the initial skeleton: open a PR, one teammate reviews.
- One personal branch per owner for day-to-day work: `matteo`, `edouard`, `tom`. Rebase on `main` often.
- Feature branches when useful: `<owner>/<topic>` (e.g. `tom/dashboard-grouping`).
- Shared files (`contracts/`, `README.md`, `AGENTS.md`, root `pyproject.toml`) have one owner each; change them
  in a PR and tell the team on the chat.

## Tooling

- Python 3.12, managed by [uv](https://docs.astral.sh/uv/). Root `pyproject.toml` is a uv workspace with members
  `agent` and `backend`; run `uv sync --all-packages` once at the root, then `uv run --package <name> ...`.
- Add a dependency with `uv add <pkg>` from inside the member directory, never by editing lock files by hand.
- Electron app in `app/` uses npm (`package.json` is Edouard's).
- Tests: `pytest` for Python members (`agent/tests`, `backend/tests`). Keep them runnable without an H key
  (use the simulated backend).

## Shared contract

- Source of truth: `agent/src/hcs_agent/contract.py` (pydantic). `contracts/*.schema.json` are generated
  from it with `scripts/export_contracts.py`; do not hand-edit them.
- Every event and report carries `simulated: true|false`. Simulated runs are for building UI and backend;
  they are never a validation of the real H integration.
- The report keeps three things apart: what the user declared (role, goal, feedback), what the agent declared
  (`declared`), what was observed (`verification`). Never collapse them.

## Demo discipline (from the PRD)

- Nothing runs before the user's explicit approval. Stop blocks new commands locally, then cancels H.
- Success = postcondition observed, not "the agent said so". Blocked = escalate with the decision expected.
- Preparation / reset scripts live in `scripts/` and are never part of the run shown on stage.
- The Mac that drives H is shared: book it on the chat, one run at a time.
- Log every real run in `docs/test-log.md`: date, scenario, duration, outcome, human corrections.

## Commits

- Short imperative subject, body explains why. Reference the PRD section when relevant.
- No secrets, no `runs/` output, no screenshots of real customer data in the repo.
