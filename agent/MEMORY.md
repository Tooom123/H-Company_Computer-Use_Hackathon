# Memory — branch `matteo` (H desktop agent, "H-Companion")

Written for the next agent (Claude Code or a human) who will test this tool end to end on the Mac and be
critical about it. State as of 2026-11-07 ~23:30, Paris. Read `AGENTS.md` at the repo root first.

## 1. What this is, in one paragraph

A customer-support assistant for a software vendor (demo software: Odoo CRM in Chrome). The user speaks
a request (push-to-talk ⌘H, Gladia STT), Holo (H Models API) routes it to a scripted procedure, then
either the agent **guides** the user step by step with a hand-drawn overlay on screen (circle/box on the
exact control, short handwritten note, arrow) or the agent **does** the task itself through H's desktop
computer-use while narrating each action. A separate read-only H session **verifies** the result; a
structured report (declared vs observed, category, escalation) is written to `runs/<session>/report.json`.
Nothing runs before approval (voice request counts as approval in `talk`); Stop is local-first.

## 2. How to run

```bash
cd /Users/matt/dev/H-Company_Computer-Use_Hackathon        # repo root, uv workspace
uv sync --all-packages
uv run pytest                                             # 18 tests, mock backend, no keys needed
uv run hcs-agent procedures                               # list scenarios
uv run hcs-agent talk                                     # the demo entry point (see below)
uv run hcs-agent run --mode guide --procedure odoo_crm_create_opportunity --goal "x" -p opportunity="Acme Demo"
uv run hcs-agent run -y --mode act --procedure odoo_crm_create_opportunity --goal "x" -p opportunity="Zz Test"
uv run hcs-agent cleanup                                  # close orphaned H desktop channels (frees quota)
uv run hcs-agent serve [--mock]                           # local HTTP/WS API for the Electron app
```

Keys in `.env` at the repo root (git-ignored; `.env.example` documents everything): `HAI_API_KEY`
(H Agents + Models API, same key), `GLADIA_API_KEY`, `LINKUP_API_KEY` (optional). `hcs-agent` loads the
nearest `.env` automatically.

**macOS permissions** for the app that launches Python (Ghostty is the user's terminal; Devin.app when run
from Devin): Accessibility, Screen Recording, Input Monitoring, Microphone. Grants apply to a fresh process
only. `uv run holo doctor` checks the H side.

**Everything the CLI prints is mirrored to `runs/hcs-agent.log`** (plus SDK logs, thread exceptions,
faulthandler dumps, signals). Read it first when something looks wrong.

## 3. `talk` — the demo loop

`uv run hcs-agent talk` → badge appears bottom-center, **Magnet** widget bottom-left.
Hold **⌘H**, speak, release → `[voice] recording / transcribing` → `You said: …` → routed procedure →
plan printed → runs immediately (`--confirm` to require `y`). After the task: closing note on screen for
5 s, then back to listening ("⌘H : nouvelle demande" badge). Ctrl+C quits.

**Magnet** (clickable paper, 3 notches; also `HCS_AUTONOMY=0|1|2` default):
- 0 *Je montre*: guide only, never takes the controls (re-explains, recovery to base screen when lost).
- 1 *J'aide si tu bloques*: guide; takeover (agent acts + narrates) when a control is missing twice or
  the user types anything ("fais-le") + Enter at a step.
- 2 *Je fais, tu regardes*: agent acts from the start, each action annotated on screen.
The Magnet is the authority on mode; the spoken verb no longer decides. Raising it mid-guide hands over.

Guide loop per step: Holo locates the control on a fresh screenshot (bounding box, ~2 s) → overlay draws
→ waits for the user's real input (global click / Enter / Esc via `inputs.InputHub`) → verifies progress
on screen (next control visible, or current gone) before moving on → re-shows the same step otherwise.
If the control is missing: diagnosis (open menu/dialog → "Appuie sur Échap"), Linkup lookup in the note,
then recovery / takeover depending on the Magnet.

## 4. Architecture (agent/src/hcs_agent)

| File | Role |
| --- | --- |
| `contract.py` | Shared pydantic contract: `InterventionRequest` (mode, autonomy), commands, `AgentEvent`, `GuidanceStep` (pointer, box, kind click/type/key/info/wait, annotations), `InterventionReport`. JSON schemas exported to `contracts/` via `scripts/export_contracts.py`. |
| `procedures.py` + `procedures/*.yaml` | The vendor knowledge: per scenario objective, allowed/forbidden actions, H instructions (act), `guide_steps` (instruction, element description for grounding, why, optional, annotations), `expected_screen`, `recovery_steps`, postcondition checks, escalation rule. Params with defaults (`+7d` = relative date). |
| `backend.py` | `HBackend`: H Agents API sessions (`host: user_device` desktop env, **one persistent desktop channel** per process with health check), structured answers (lenient parsing; H strips `outcome` so our field is `result`), custom tool `lookup_docs` (Linkup), `verify()` read-only session, `locate()`/`screen_matches()`/`diagnose()` via `grounding.py`. `MockBackend` for tests/UI (flag `simulated`). |
| `grounding.py` | Holo Models API (`holo4-35b-a3b`, thinking off): `locate` returns the element's bounding box + `is_the_control` honesty flag (never offer a `not_found` escape alone: Holo bails too easily). Coordinates are normalised [0,1000]. |
| `runner.py` | `Intervention` state machine: approval gate, attempts, scripted guide (`_scripted_guide`), takeover, verification, report, stop with measured latency, `set_autonomy()` live. |
| `overlay.py` | AppKit overlay (click-through, excluded from screen capture so H never sees it): `Scene`/`Mark`, paper-cutout notes (collision-avoiding placement, clamped on screen), pencil strokes revealed progressively, frames fitted to element boxes (loop / rounded box / brackets / highlighter), doodles (asterisk, check, question), listening badge, `MagnetWidget`. |
| `inputs.py` | Single global pynput mouse+keyboard listener (`InputHub`); swallows the ⌘H combo. Two event taps in one process caused silent process deaths. |
| `voice.py` | `Recorder` (sounddevice 16 kHz), `Transcriber` (Gladia solaria-3, French, custom vocabulary), `IntentRouter` (Holo text, `enable_thinking: false`, never invents params → `missing`), `PushToTalk`. |
| `knowledge.py` | Linkup (optional): `lookup_docs` tool for the agent, blocker lookup at escalation, element lookup when a control is missing. `HCS_GROUND_PLAN=1` adds a sourced summary to the plan. |
| `cli.py` | `run`, `talk`, `serve`, `procedures`, `cleanup`; `_guide_loop` (main thread: overlay pump, input watcher, screen watcher, narration during takeover), logging/tee/faulthandler. |
| `server.py` | FastAPI + WebSocket for the Electron app (`/interventions`, `/approve`, `/stop`, `/next`, `/feedback`, `/ws`). |

Procedures today (all Odoo CRM, English UI labels, written for Odoo 19/Online — the team's demo instance
is **Odoo 20** on Netcup via Édouard's tunnel; labels may differ):
`odoo_crm_create_opportunity` (3 steps, starter), `odoo_crm_followup_activity`, `odoo_crm_log_note`
(Log note vs Send message trap), `odoo_crm_qualify_opportunity` (7 steps incl. an info "tour" step),
`odoo_crm_change_stage_restricted` (blocked case, permissions).

## 4b. Validated on the real Odoo 20 (Claude Code, 2026-11-07 evening)

- Procedures rewritten against **Odoo 20** (commit `0da7530`): Contact (not Customer), "Opportunity's Name" is
  the 2nd line of the quick-create card (cursor starts in Contact), Enter saves and reopens an empty card
  (so "type name" and "Add" are one step), chatter on the right, Activity dialog button is **Save** (type
  To-Do preselected, summary pre-filled "To-Do"), internal notes have no yellow background any more.
- **Grounding**: 26/28 element descriptions framed the right control first try, 0.7–2 s (median 0.9 s).
  Details in `docs/grounding-odoo20-2026-11-07.md`. Failures were descriptions containing a value that
  changes ("0.00 €") and a header covered by Odoo's tutorial bubble (close the tutorial on the demo base).
- **`done_when`** (per-step end state checked by Holo before advancing): 16/18 first try, 20/20 after
  rewording. Rules: name the exact field (Holo reads the whole screen and may match history text behind a
  dialog); write positive statements (Holo answers negatives badly: not "no cloud icon" but "the form is
  saved: only the ⋮ menu is shown").
- Full guided run with the overlay **still not observed end to end** (screen was busy). That is the test.
- "Won blocked" needs a non-admin Odoo user AND an opportunity owned by someone else (a salesperson may
  mark their own opportunity Won). Decide the setup before the demo.
- API for the Electron app: `autonomy` on the request, `POST /interventions/{id}/autonomy` (live Magnet),
  snapshot `autonomy`/`takeover`/`mode`; `guidance` events carry `box` and `annotations`. Stop (Ctrl+C or
  `/stop`) is clean mid-guide and mid-takeover; voice "reprends / continue" re-runs the last request.

## 5. Measured numbers (keep them honest)

- Holo text answer, thinking off: 0.6 s. Grounding with 1024-px screenshot: 1.2–1.8 s (+0.4 s capture).
- One H agent observation+answer turn (`holo4-35b-a3b`, low effort): ~10 s. Session startup ~5 s.
- Desktop channel: 0.6 s when reused; ~5 s + rate-limit retries when opened per session (fixed).
- Gladia pre-recorded (3 s audio): ~3.6 s. Routing: ~1.2 s. Stop latency (mock): 0.2 s.
- Act mode end to end (create opportunity + verification): ~1.5–2 min including verification.
- Quota: Free plan = 3 concurrent sessions org-wide. A killed process leaves its channel open and eats a
  slot → sessions silently `queued`. `hcs-agent cleanup` (also run at backend start) closes them.

## 6. Known problems and open questions — be critical here

1. **Guide reliability on real Odoo is unproven beyond the first steps.** Verified live: screen check,
   card located and framed, New button; grounding and done_when validated offline on real screenshots
   (see 4b). Not yet seen live: a full guided run to the closing note with the bounding-box frames. Test each procedure end to end and record per-step: was the right control framed?
   did progress detection fire after the user's click? how many seconds per step?
2. **Progress detection** uses real input (click/Enter/Esc) then a screen re-check. Typing steps advance on
   Enter/Tab or a click after typing. Expect false positives when the user clicks elsewhere (the screen
   re-check should catch it) and false negatives on fields filled without Enter.
3. **Grounding descriptions live in YAML**, now aligned with Odoo 20 and tested offline (26/28). Wrong frames
   are almost always a description problem; never put changing values in a description.
4. **Takeover narration circles** rely on the agent's action coordinates (normalised 0–1 of the screen);
   mapping untested on a second display or non-retina screen. Narration text quality depends on the agent
   obeying "one French sentence before each action".
5. **Gladia** mangles proper nouns in French ("Acme Demo" → "akakakakka", "Acme Studio"). Custom vocabulary
   is passed; pronunciation hints not yet. Prefer French-sounding demo names.
6. **Silent process exits** happened three times from `talk` right after approval; cause identified as a
   second keyboard event tap; fixed via `InputHub` — confirmed once (traceback instead of death). Watch for
   recurrence; check `echo $?` and `runs/hcs-agent.log`.
7. **Only one process may drive the desktop.** Running a test from another shell while the user runs `talk`
   displaces the bridge and kills the user's run. Book the Mac.
8. **Verification** is an H agent session (~10 s) and is the only thing that decides `resolved`. It once
   clicked outside the browser and reloaded the page (instructions now forbid both). Check it stays inside.
9. **Overlay text**: terse by default (instruction only; `why` on info steps; `HCS_GUIDE_VERBOSE=1` for all).
   Users found earlier versions too wordy and overlapping; placement is collision-avoiding now.
10. **Not done**: pronunciation hints for Gladia, TTS output, Electron integration of guide mode (Édouard's
    pilot pins an old engine revision in act mode), Odoo 20 label alignment, local Holo runtime on the DGX,
    crops from the Vision Lab, stop/resume of an interrupted guide, tests for `inputs.py`/`overlay.py`
    (AppKit, untested), rate limits of the Models API under rapid grounding calls.

## 7. Suggested test protocol for the next agent

1. `uv run pytest`, then `uv run holo doctor`, then `uv run hcs-agent cleanup`.
2. Odoo CRM pipeline visible in Chrome on the main display, card "Acme Demo" present.
3. Magnet 0, voice or `run --mode guide`: `odoo_crm_create_opportunity` → `odoo_crm_log_note` →
   `odoo_crm_qualify_opportunity`. For each step note: control framed correctly (y/n), seconds to show,
   advanced after the right action (y/n), any wrong/extra step. Try a deliberate wrong click and an open
   dropdown to exercise re-show and diagnosis. Type "fais-le" once to exercise takeover (Magnet 1).
4. Magnet 2: `odoo_crm_qualify_opportunity` by voice; judge the narration (French? before each action?
   circle on the right element?). Then the verification outcome vs reality in Odoo.
5. Stop test: Ctrl+C mid-run; check the report says `abandoned`, nothing else changed, latency recorded.
6. Log every real run in `docs/test-log.md` (date, scenario, duration, outcome, human corrections).
7. Be blunt in a findings section: what a real support customer would find confusing, slow or wrong.

## 8. Git

Branch `matteo` tracks `origin/matteo`, merged with `main` at `8b8b8ac` (Édouard's recap in
`docs/recap-equipe-2026-11-07.md`: pilot results, Odoo 20 instance, DGX inference). Commit small, push often,
never commit `.env`, `runs/`, screenshots of real data.
