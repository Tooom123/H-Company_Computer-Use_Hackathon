# TODO — Tom (support backend, data, demo infrastructure)

State: 2026-11-07 evening. Engine on `main` (merged from `matteo`): voice → procedure → guide with overlay
or act with narration → verification → report. Read `agent/MEMORY.md` and
`contracts/InterventionReport.schema.json` for the exact fields. In priority order:

## 1. Demo data reset + non-admin Odoo user  (unblocks everything else) — DONE in code, to run on the demo Mac
- `scripts/odoo_reset.py` (or shell): put the Odoo 20 demo instance back to the known state — delete every
  `Zz Test*` opportunity, recreate "Acme Demo" in the New column (no contact, no revenue, no activity, no note),
  make sure contact "Acme Corp" exists once. Idempotent, runnable before each demo take.
- Create a Sales user WITHOUT manager rights (Sales: "User: Own Documents Only") and document the login in the
  private channel. Needed for the blocked scenario `odoo_crm_change_stage_restricted` (Won refused → escalation).
  The current account is admin, so Won always succeeds and the blocked case cannot be shown.
- PRD rule: the success case must pass 3 times in a row from this reset state; log each run in `docs/test-log.md`.

## 2. Dashboard: ingest the new report fields — DONE
- `InterventionReport` now carries: `mode` (act/guide), `autonomy` (0-2, in the request), `guidance[]`
  (index, instruction, why, pointer, box, kind, annotations), `knowledge[]` (Linkup lookups with sources and
  purpose), `verification.checks` (one boolean per postcondition check), `declared` vs `verification`,
  `evidence[]`, `timings` (incl. stop latency), `cost_usd`, `h_session_ids`.
- Show a case as a timeline: steps explained → where the user got stuck → takeover (if any) → each agent action
  → what the verifier observed. Keep "declared by the agent" and "observed" visually separate (PRD).
- `simulated: true` reports must be visibly flagged and excluded from metrics.

## 3. Grouping (PRD requirement) — DONE (needs ≥ 3 real runs to show)
- Two similar difficulties → one group; a different one stays apart. Each group lists its cases, the procedures
  tried, the verified results and the decision expected from support (`escalation.decision_expected`).
- Start simple: same `procedure_id` + same `category` + similar `escalation.blocked_on` (normalized text).
- Needs ≥ 3 real runs: they accumulate in `runs/<session>/report.json` on the demo Mac.

## 4. Reliability metrics page (jury: reliability 25 %) — DONE (`/dashboard/metrics`)
- Per scenario: success rate (verified), median seconds per guided step (from `steps` with kind=action and
  summary "step N shown after X s"), takeover rate, stop latency, cost per session, attempts.
- Honest numbers only; show N.

## 5. Escalation case file export — DONE (`/dashboard/cases/{id}/dossier`, `.md`)
- One markdown/printable "dossier" per escalated case: goal, role, state observed, steps tried, exact blocker,
  Linkup context (`knowledge` with purpose=blocker), evidence refs, decision expected. What a support agent
  would receive from the vendor.

## 6. If time remains: procedure authoring helper — DONE (draft only, see docs/procedure-drafts.md)
- From a documented Odoo task (Linkup fetch of the doc page) to a draft YAML (`guide_steps` with element
  descriptions and `done_when`) that Matteo/Claude Code validate against the live screen. Shows the vendor can
  scale to dozens of tasks.

## Status (Tom, 2026-11-07 night, branch `feature/tom-todo`)

1. `scripts/odoo_reset.py` (+ `docs/odoo-reset.md`), tested against a disposable Odoo 19. Finding: an
   "Own Documents Only" user does not even see `Acme Demo`; the script adds a read-only pipeline rule so the
   card is visible and Won is refused (checked by logging in as that user). **Left for the demo Mac**: run it on
   the Odoo 20 instance, share the sales login privately, then 3 successful runs in a row logged in
   `docs/test-log.md`.
2. Case timeline (explained → stuck → takeover → agent → verifier), mode / takeover / attempts / duration / stop
   latency / cost, Linkup lookups; simulated reports flagged and excluded from all numbers. The report has no
   `autonomy` / `takeover` field: takeover is read from the guide traces ("taking over"). Adding both to
   `InterventionReport` would make this exact (Matteo).
3. Grouping on procedure + category + normalised `blocked_on`; groups list cases, procedures, verified results
   and decisions expected.
4. `/dashboard/metrics` and `/metrics`: per scenario, real sessions only, N and numerator/denominator shown.
5. Escalation file with the Linkup context on the blocker and the course of the session; printable page.
6. `scripts/draft_procedure.py`: documentation page → draft YAML validated against the engine's model.

## Rules
- Branch `tom` (or `tom/<topic>`), PR to `main`, do not edit `agent/` without telling Matteo.
- One operator drives the demo Mac at a time; the engine refuses a second desktop driver.
