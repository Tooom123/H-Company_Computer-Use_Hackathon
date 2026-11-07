# hcs-agent — H desktop agent for the customer-success assistant

Owner: Matteo. Python component that drives the user's software through H's `desktop` environment,
with explicit approval, a local stop gate, verified results and a structured report for support.

```
Electron app ──HTTP/WS──> hcs-agent serve ──H Agents API──> Holo model
                              │  (this process serves the desktop: screenshots out, mouse/keyboard in)
                              └── runs/<session_id>/report.json  ──> support backend / dashboard
```

## Setup

```bash
cd agent
uv sync
cp .env.example .env            # then put your HAI_API_KEY in it (or run: uv run holo login)
```

macOS permissions for the app that launches Python (Terminal, iTerm, Electron...):
System Settings → Privacy & Security → **Screen Recording**, **Accessibility**, **Input Monitoring**.
Restart the app after granting. `uv run holo doctor` shows what is missing.

## Run

```bash
uv run hcs-agent procedures                     # list scenarios
uv run hcs-agent serve                          # local API on 127.0.0.1:8765 for the Electron app
uv run hcs-agent serve --mock                   # same API, simulated H (events flagged simulated: true)

# Direct test on the Mac (Odoo open and logged in on the main display):
uv run hcs-agent run --procedure odoo_crm_followup_activity \
  --role "new sales rep" --goal "Help me schedule the follow-up on Acme Demo" \
  -p opportunity="Acme Demo" -p due_date=2026-11-14

uv run hcs-agent run --mock -y --procedure odoo_crm_change_stage_restricted --goal "Mark Acme Demo as won" -p opportunity="Acme Demo"
uv run hcs-agent run --mock -y ... --stop-after 2   # measures stop latency
uv run pytest
```

Guide mode (the agent explains and points, the user clicks):

```bash
uv run hcs-agent run --mode guide --procedure odoo_crm_followup_activity --role "new sales rep" \
  --goal "Show me how to schedule the follow-up on Acme Demo" -p opportunity="Acme Demo" -p due_date=2026-11-14
```

Environment variables: `HAI_API_KEY`, `LINKUP_API_KEY` (documentation lookups; optional), `HCS_MOCK=1`, `HCS_MODEL` (default `holo4-35b-a3b`),
`HCS_SCREENSHOT_MAX_WIDTH` (default 1280), `HCS_RUNS_DIR`, `HCS_MOCK_OUTCOME=done|blocked|fail_verify`,
`HCS_MOCK_PREFLIGHT_FAIL=1`.

## Shared contract (`src/hcs_agent/contract.py`)

| Direction | Object | Notes |
| --- | --- | --- |
| app → agent | `InterventionRequest` | `session_id`, `software`, `role`, `goal`, `symptom?`, `procedure_id`, `parameters` |
| app → agent | `ApproveCommand`, `StopCommand`, `NextCommand`, `FeedbackCommand` | nothing reaches H before `approved: true`; `NextCommand` answers a guide step |
| agent → app/backend | `AgentEvent` | `type` ∈ state_changed, plan_proposed, step, attempt_started, attempt_finished, verification, guidance, knowledge, needs_human, stopped, finished, error; `simulated` flag |
| agent → backend | `InterventionReport` | declared vs verified result, `category`, `status`, `escalation`, `evidence`, `timings.stop_latency_s` |

Categories: `usage, configuration, permissions, data, suspected_product_defect, environment, agent_failure, unknown`.
Statuses: `resolved, workaround, escalated, abandoned`.

## HTTP API (`hcs-agent serve`)

| Method | Path | Body |
| --- | --- | --- |
| POST | `/interventions` | `InterventionRequest` → 201, state `awaiting_approval` + `plan` |
| POST | `/interventions/{id}/approve` | `{"approved": true, "scope_note": "..."}` |
| POST | `/interventions/{id}/stop` | `{"reason": "..."}` |
| POST | `/interventions/{id}/next` | guide mode: `{"done": true, "note": "..."}` after a `guidance` event (state `awaiting_user`) |
| POST | `/interventions/{id}/feedback` | `{"useful": true, "comment": "...", "allow_screenshots_to_support": false}` |
| GET | `/interventions/{id}` | snapshot (state, plan, steps, declared, verification) |
| GET | `/interventions/{id}/report` | `InterventionReport` (425 until finished) |
| GET | `/interventions/{id}/events` | event history |
| WS | `/interventions/{id}/ws` | replays history, then live `AgentEvent`s until `finished` |
| GET | `/procedures`, `/health` | |

## Modes

- `act` (default): the agent performs the steps in the software, then a separate read-only session verifies.
- `guide`: the agent only explains and moves the pointer to the control; the user performs each step and
  answers with `/next`; the state alternates `running ↔ awaiting_user`. Same verification at the end.

## Web lookups (Linkup, optional)

Not central. With `LINKUP_API_KEY`, the H agent gets a custom tool `lookup_docs` it can call when it needs
information from the internet (a menu path, what an error means); at escalation the blocker text is looked
up so support gets context. Optional: `HCS_GROUND_PLAN=1` adds a sourced summary to the plan before approval,
`HCS_RESTRICT_DOMAINS=1` limits searches to the vendor's domains. Each lookup is recorded in
`report.knowledge` (`purpose` ∈ agent_lookup, blocker, explain). Without a key, nothing is looked up.

## State machine

`created → awaiting_approval → running (↔ awaiting_user in guide mode) → verifying → resolved | escalated`,
and `stopping → stopped` at any time.
Rules enforced in `runner.py` (not in the prompt):

- the agent's declared outcome never sets the case status; the observed postcondition does;
- a `blocked` declaration is not retried: the case is escalated with the exact blocker and the decision expected from support;
- attempts are capped by the procedure (`max_attempts`); verification failure feeds the next attempt;
- `stop()` sets a local gate first (no new H command leaves the process), then cancels the H session; latency is recorded;
- stop does not revert changes already made.

## Procedures (`src/hcs_agent/procedures/*.yaml`)

One YAML per scenario: parameters, preconditions, objective, planned changes, allowed / forbidden actions,
H instructions, postcondition checks (each becomes a boolean in the verification answer), attempt cap,
escalation rule. Two demo procedures ship:

- `odoo_crm_followup_activity` — success case (reversible, 2 attempts)
- `odoo_crm_change_stage_restricted` — blocked case (access rights, 1 attempt, escalates)

Verification runs as a **separate read-only H session** with a structured answer, so the result does not
rely on the acting agent's claim. Local before/after screenshots are kept as evidence
(`shareable_with_support` only after the user's feedback allows it).
