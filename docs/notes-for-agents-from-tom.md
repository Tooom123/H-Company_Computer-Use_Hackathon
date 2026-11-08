# Notes for the other agents (from Tom's side) — read before touching the contract, the overlay or the demo

State: 2026-11-07, late evening. Each item says who it concerns and what to do. Facts were checked; nothing here
is a guess unless marked so.

## For Matteo (engine, `agent/`)

1. **Regenerate `contracts/` after every `contract.py` change.** It was forgotten twice (`GuidanceStep.box` and the
   annotation fields were missing from the schemas). The support backend validates every report against
   `contracts/*.schema.json`: a stale schema means rejected reports. Command:
   `uv run --package hcs-agent python scripts/export_contracts.py`, commit the JSON with the Python change.
2. **`InterventionReport` has no `autonomy` and no `takeover` field.** The dashboard has to infer takeover from
   the guide traces (`"autonomy raised to max: taking over"`) and cannot show the Magnet level at all. Please add
   `autonomy: int` (copied from the request) and `takeover: bool` (+ ideally `takeover_at_step: int | None`) to the
   report. The dashboard will read them as soon as they exist (backend `timeline.had_takeover`).
3. **`Step.attempt` in guide mode is the guide step number, not the attempt.** The backend therefore takes the
   attempt count from `escalation.attempts`. If a report should show attempts outside escalations, add an explicit
   `attempts` field to the report instead of relying on `Step.attempt`.
4. **Verifier steps are recognised by `attempt == 0`.** Keep that convention (the case timeline colours them
   apart from the agent's claims), or add `actor: "verifier"` to `Step`.
5. **Reports reach the support dashboard only if the uplink is on**: set `HCS_BACKEND_URL` and
   `HCS_INGEST_TOKEN` (same value as the backend's) in the engine's `.env` on the demo Mac
   (`agent/src/hcs_agent/support.py`; off by default, never blocks a run). Optional `HCS_SUPPORT_USER`.
6. **Procedure drafts**: `scripts/draft_procedure.py` turns a doc page into a YAML that validates against
   `Procedure`. It writes a `done_when` hint per guide step that the engine ignores today; if you add a
   `done_when` field to `GuideStepSpec`, the drafts already carry it. Drafts must be checked on the live screen.

## Spoken notes (ElevenLabs TTS) — for Matteo

`agent/src/hcs_agent/speech.py` + hooks in `cli.py` and two lines in `overlay.py` (Tom, 2026-11-08):
- every overlay note is read aloud: guide steps (instruction, plus `why` when it is shown), takeover
  narration, closing note, routing flashes. Call `_say(...)` right BEFORE `ov.show_scene(...)`;
- sync: `Overlay.hold_reveal = Speaker.holding`; the scene is not drawn until its sentence is audible
  (max 1.5 s), so pencil and voice start together;
- a new step interrupts the previous sentence; narration never cuts, only the latest waits; the user acting
  (`advance`), Stop, Ctrl+C, `q` and push-to-talk (`recording`) silence it at once;
- guide sentences are prefetched at plan time and cached on disk (`$TMPDIR/hcs-tts/`): a step is heard ~5 ms
  after it is requested (measured), an unknown sentence ~0.3-1 s;
- `HCS_TTS=0` mutes; no key / no `afplay` = silent, never an error. Tests: `agent/tests/test_speech.py`.
- Not done: the Electron app path (`serve`) has no voice; Édouard's overlay would need the same hook.

Also: `pyobjc-framework-avfoundation` has no `sys_platform == 'darwin'` marker, so `uv sync` fails on Linux
(build of pyobjc-framework-coreaudio). `test_geometry_and_inputs` has 2 tests that fail off macOS.
Contracts are out of sync again on `main` (`cbad15f`): `GuidanceStep.shown_at` / `done_s` are in `contract.py`
but not in `contracts/*.schema.json`; run `scripts/export_contracts.py` and commit the result.

## Desktop app + control point — for Matteo (branch `feature/tom-desktop-app`)

- `desktop/`: Electron app (Home / Activity / Usage & plan / Voice / Vision). See `desktop/README.md`.
- `agent/src/hcs_agent/control.py`: stdlib HTTP on 127.0.0.1:8768, started by `talk` and `run`
  (`_start_control` in `cli.py`). Needs header `X-HCS-App: 1` + local Host. `HCS_CONTROL=0` turns it off.
- Autonomy has one entry point now, `_set_autonomy(level)` in `cli.py` (Magnet clicks and the app both use it).
- The Magnet hides while the app polls (`MagnetWidget.hide/show`, `contains()` is False when hidden) and comes
  back 6 s after the app closes.
- Clicks inside the app window never count as the user doing a step (`_InputWatcher` asks
  `ctl.app_contains(x, y)`; the app sends its bounds in `X-HCS-App-Bounds`). The app window is excluded from
  screen capture (`setContentProtection`), so H and `_ScreenWatcher` never see it.
- `POST /ptt {key}` changes the push-to-talk key live (`PushToTalk.set_key`, `voice.py`); badges use
  `_key_label()` instead of a hard-coded ⌘H.
- `Speaker.muted` and live voice switching (`_control_voice` replaces the speaker; `hold_reveal` reads
  `_SPEECH["speaker"]`, not a bound method).

## For Édouard (Vision Lab, pilot, Odoo)

1. **Gaze halo is wired into the Vision Lab overlay** (`app/src/Overlay.tsx`, `GazeHalo`): main relays accepted
   gaze points to the overlay only (`companion:gaze-updated`, coordinates, no image); the overlay window is
   already excluded from captures, so Holo never sees it. Targets are empty for now (gaze-only cloud): feed
   desktop targets with `heat.setTargets([{id, rect}])` when they exist (accessibility / Holo localisation).
   Module source and tests: `heatmap/`; `app/src/lib/gaze-heatmap.js` is a copy, keep both in sync.
2. **The voice pilot imports the backend `Store` directly** (pinned `bd3b2ca`). The current backend adds a
   `fixes` table and new pages but `Store` stays compatible. If the pilot moves to the HTTP API, use
   `POST /cases` with the ingest token (same as the engine uplink).
3. **Odoo reset + restricted user**: `scripts/odoo_reset.py` (`docs/odoo-reset.md`). Run `--check` then the reset
   before each take, `--sales-user` once. Important finding on a real Odoo 19: an "Own Documents Only" user does
   not see `Acme Demo` at all, so the script adds a read-only pipeline rule for that user and proves that the
   card is visible and Won is refused. Not yet run on the Odoo 20 instance (labels may differ).

## For everyone

1. **Branch names**: `tom/<topic>` is impossible while a branch named `tom` exists (git refs), hence
   `feature/tom-*`. Same for `matteo/<x>` / `edouard/<x>` if personal branches exist.
2. **`main` was force-forwarded by Tom twice tonight** (consolidated merge, then the Devin branch) on request,
   without PR review: AGENTS.md says PR + review. Pull before working.
3. **Simulated vs real**: every number in the dashboard and `/dashboard/metrics` counts real sessions only;
   simulated reports are listed with a flag. Demo cases are `demo_data` and can be removed with
   `hcs-backend reset-demo` before the pitch.
4. **Devin auto-fix**: suspected product defects on allowlisted repos (`HCS_FIX_REPOS`) open a PR on
   `feature/hcs-fix-<case>`; verified end to end on the sandbox repo (Tooom123/hcs-sandbox-fake-crm#1). Keys live
   in `backend/.env` only. Devin may stay `waiting_for_user` after opening its PR: the backend treats "PR present"
   as done.
5. **Ports**: agent 8765, support backend 8766, voice pilot 8767, landing 5173, heatmap test page 5174,
   disposable Odoo for tests 18069 (local Docker, never the shared instance).
