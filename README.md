# H Companion

**A voice-first computer-use companion that lives inside the software you already use.** Hold a key, say what
you need, and H Companion shows you how on your own screen (red-pencil notes and circles drawn over the real
interface, read aloud), or does it for you while you watch. Every result is checked in the software itself, and
anything it cannot solve goes to the vendor's support as a complete, structured case.

Built on [H Company](https://hcompany.ai/)'s Holo models and H Agents API (computer use) during the H Company
computer-use hackathon.

![H Companion: clicking the H key turns "H Company" into "H Companion", corrected in red pen](h-companion.gif)

---

## What it does

- **Ask by voice.** Push-to-talk (hold the shortcut, speak, release). Speech is transcribed (Gladia), then routed
  to a known procedure or to a general task by a Holo model.
- **Three levels of autonomy**, changeable at any time, even mid-task:
  - *Show me*: the assistant points at each control and explains; you click, it never takes the controls.
  - *Help if I'm stuck*: it guides you, and finishes the task itself (narrating each action) if you are stuck.
  - *Do it, I watch*: it does the task in front of you through H computer use, annotating every action.
- **On-screen guidance** in a hand-drawn style: a transparent overlay (macOS) frames the exact control found by
  Holo on a fresh screenshot, with a short handwritten note. The overlay is excluded from screen capture, so the
  model never sees its own marks.
- **Spoken notes** (ElevenLabs): each note is read aloud as it is drawn; the voice stops as soon as you act or
  speak.
- **Verified results.** Success means the expected end state is observed on screen by a separate read-only check,
  not that the agent said it was done. The report keeps three things apart: what the user declared, what the
  agent declared, and what was observed.
- **Safe by design.** Nothing runs before approval (a spoken request counts as approval in voice mode), Stop is
  local-first (no new command leaves the machine) and then cancels the remote session; simulated runs are always
  flagged as such.
- **Support side.** Reports go to a support backend: an authenticated dashboard with a timeline per case,
  grouping of similar difficulties, reliability metrics on real sessions only, a printable escalation file with
  the exact blocker and the decision expected from support, and optional automatic bug-fix pull requests through
  Devin (Cognition) for suspected product defects on allowlisted repositories.
- **Desktop app.** A small window (Electron) next to your work: live status and Stop, the autonomy slider, your
  task history with a ✓ / ✗ verdict per task (sent back with the report), voice and push-to-talk settings, and
  gaze calibration.
- **Vision: gaze-assisted grounding (opt-in).** With one switch in the desktop app, a webcam gaze tracker running
  entirely on the computer (no face image ever leaves it) tells the agent where the user is looking. Instead of the
  whole screen, the agent sends H's Holo model a **smaller screenshot**, cropped around the gaze, the clickable
  controls and what the user asked, and falls back to the full screen when the control is not there. Benchmarked
  on 7,000+ real Holo calls: **same accuracy with 43 % fewer pixels and ~64 % fewer image tokens**, and **75 % →
  85 % success** on vague, user-style requests. A red "honeycomb" shows the user what is tracked, over every app.
  Details in [Vision: gaze-assisted grounding](#vision-gaze-assisted-grounding).

Demo software: Odoo CRM (create an opportunity, schedule a follow-up, log a note, qualify an opportunity, and a
deliberately blocked action caused by user rights) and the H Company platform (find documentation, create an API
key, redeem credits, create an agent, review a session, run a cloud session). Unscripted requests are handled by
the general agent working from the live page.

## How it works

```
 voice ──► transcription ──► routing (Holo) ──► guide  (Holo locates each control, overlay + voice, user acts)
 (push-to-talk)                              └► act    (H Agents API drives mouse/keyboard, narrated on screen)
                                                   │
                         read-only verification ◄──┘   (separate H session: is the end state really there?)
                                                   │
             runs/<session>/report.json ──► support backend ──► dashboard · grouping · escalation file · Devin fix
                                                   ▲
                        desktop app ◄── control point 127.0.0.1:8768 (status, autonomy, stop, voice, rating)
```

## Vision: gaze-assisted grounding

Every guided step asks Holo to find one control on a screenshot. The user is usually already looking at it, so
H Companion can send **only the part of the screen that matters**: a smaller image to the H Models API, and a
model that is not distracted by look-alike controls elsewhere on the screen.

**How it works.**

1. **Opt-in.** Vision is off by default. The user turns it on in the desktop app's Vision tab and calibrates once
   (9 dots, 3 clicks each, then 4 dots only looked at, ~30 s); the accuracy is measured and shown.
2. **On-device gaze tracking.** A background tracker reads the webcam locally (MediaPipe face and iris landmarks,
   ridge regression calibrated on the user) and streams only screen coordinates to the agent's local control
   point. No image of the face is stored or sent. The user sees their gaze as a red honeycomb over every app
   (it can be hidden; the overlay is excluded from screen capture, so Holo never sees it).
3. **Gaze × controls × intent.** At each step the agent scores every clickable control on screen (accessibility
   tree on macOS) by how close it is to the gaze and how well its label matches the request (local, free, FR/EN),
   and crops the screenshot around the most probable controls, at least 768×480
   ([`gaze_crop.py`](agent/src/hcs_agent/gaze_crop.py)).
4. **Safe fallback.** Holo can answer "not here"; the agent then asks again on the full screen. Strict screen
   checks (verification) always use the full screen.

**Benchmarks** (real H Models API calls, `holo4-35b-a3b`, the agent's own grounding request; method, data, raw
calls and statistics in [`bench/`](bench/README.md)). We iterated in three rounds: an exploration run (5,206
calls, 3 Holo models, 12 real websites and 3 Odoo-like screens), a **confirmation run on a fresh dataset**
(2,018 calls, 112 tasks) so that the chosen setting is not judged on the data it was tuned on, and an ablation of
each signal (gaze, controls, intent) on user-style requests (1,236 images).

| Finding | Full screen (before) | Gaze crop (now) |
| --- | --- | --- |
| Pixels sent per screenshot | 655,360 | **368,640 (−43 %)** |
| Image tokens per call | 581 | **207 (−64 %)** |
| Success when the task names the control | 95 % | **94–97 %** (no significant difference) |
| Success on vague, user-style requests (good / fair webcam) | 75 % | **86 % / 85 %** with the gaze crop, 84 % / 82 % with all three signals (p < 0.01–0.02) |
| Gaze × controls × intent, realistic mix (10 % of steps looking elsewhere) | 75 % | **82 %**, for +6 % cost |
| User looking elsewhere | — | Holo says "not here" 94 % of the time; fallback recovers |

What we learned along the way:

- **Smaller screenshots, same answers.** A crop of at least 768×480 around the gaze is as accurate as the full
  screen while sending 43 % fewer pixels; per call, the bill drops ~7 % and latency 5–10 %, because the fixed
  prompt and tool schema (~540 tokens) dominate. A lighter tool schema would multiply the saving.
- **When users speak like users, the gaze makes Holo right more often.** "I want to revoke my key" is vague; the full
  screen keeps every look-alike, the crop around the gaze does not: +10 points.
- **Too tight hurts.** Crops of 512×320 lost accuracy among dense links (84–87 %); the 768×480 floor fixed it.
- **The gaze is what makes a crop work.** The same crop at the screen centre falls back 79 % of the time and costs
  more.
- **Combining the three signals is the robust choice.** Gaze alone is fragile when the user looks away; adding the
  request and the on-screen controls keeps the crop on the right control and is the most stable setting.

Honest limits: the gaze in the benchmark is simulated from measured webcam error (60 / 120 / 200 px), and the
screens are public websites and Odoo-like mock-ups; the next step is the same protocol with recorded gaze on real
customer software.

## Repository layout

| Path | What it is | Stack |
| --- | --- | --- |
| [`agent/`](agent/) | The assistant: procedures, routing, guide and act modes, verification, report, push-to-talk, overlay, voice, local control point (`hcs-agent`) | Python 3.12, `hai-agents`, AppKit (macOS) |
| [`backend/`](backend/) | Support backend: case ingestion, dashboard, grouping, metrics, escalation file, Devin auto-fix, Stripe test checkout (`hcs-backend`) | Python 3.12, FastAPI, SQLite |
| [`desktop/`](desktop/) | Desktop app (status, autonomy, activity and verdicts, voice, vision opt-in), background gaze tracker, macOS menu-bar companion and Finder launcher | Electron, plain JS, Python (MediaPipe) |
| [`app/`](app/) | Vision Lab (local gaze tracking, calibration, region of interest, clean screen capture, Holo analysis) and the voice pilot UI | Electron, React, Vite, TypeScript |
| [`pilot/`](pilot/) | Voice pilot server and isolated headless-browser pilot | Python |
| [`heatmap/`](heatmap/) | Gaze "honeycomb" heatmap, calibration, webcam vision page and the full-screen gaze overlay | JS (no dependency) |
| [`bench/`](bench/) | Gaze-assisted grounding benchmark: datasets, scripts, raw Holo calls and reports | Python, Electron |
| [`landing/`](landing/) | The public website (landing page) | Static HTML/CSS/JS, three.js |
| [`contracts/`](contracts/) | JSON Schemas shared by every component, generated from `agent/src/hcs_agent/contract.py` | JSON Schema |
| [`scripts/`](scripts/) | Contract export, demo data reset (Odoo), procedure drafting, launchers, benchmarks | Python |
| [`docs/`](docs/) | Product spec ([PRD.md](PRD.md)), gaze research protocol, scenarios, test logs | Markdown |

## Requirements

- **macOS 14+** for the full assistant (overlay, screen capture, global push-to-talk). The support backend, the
  desktop app with a simulated agent, the website and every test also run on Linux.
- **Python ≥ 3.12** and [uv](https://docs.astral.sh/uv/).
- **Node.js ≥ 20** and npm (the Vision Lab is developed with Node 26).
- **Xcode Command Line Tools** for the Vision Lab's native screen-capture helper (`xcode-select --install`).
- **Google Chrome** for the isolated browser pilot only.
- API keys, all optional except H:

| Variable | Used for | Where |
| --- | --- | --- |
| `HAI_API_KEY` | **Required.** H Agents API and Models API (Holo). Or run `uv run holo login` | `.env` at the repo root (agent), `app/.env` (Vision Lab, pilot) |
| `GLADIA_API_KEY` | Speech-to-text for push-to-talk | `.env` |
| `ELEVENLABS_API_KEY` | Spoken notes (also read from `ELEVEN` in `backend/.env`) | `.env` |
| `LINKUP_API_KEY` | Documentation lookups (web search restricted to the vendor's docs when asked) | `.env` |
| `HCS_INGEST_TOKEN`, `HCS_DASHBOARD_PASSWORD` | Agent → backend uploads, dashboard login (generated and printed if empty) | `backend/.env` |
| `STRIPE_SECRET_KEY` | Checkout on the website, **test keys only** (`sk_test_…`) | `backend/.env` |
| `DEVIN_API_KEY`, `DEVIN_ORG_ID`, `HCS_FIX_REPOS` | Automatic fix pull requests (allowlisted repositories only) | `backend/.env` |

All `.env` files are git-ignored; every one has a commented `.env.example` next to it.

## Install

```bash
git clone https://github.com/Tooom123/H-Company_Computer-Use_Hackathon.git h-companion
cd h-companion

uv sync --all-packages                 # one .venv at the root with the agent and the backend
cp .env.example .env                   # put HAI_API_KEY (and the optional keys) in it
cp backend/.env.example backend/.env   # support backend settings

npm ci --prefix desktop                # desktop app
npm ci --prefix app                    # Vision Lab (optional)
```

**macOS permissions.** The app that launches Python (Terminal, iTerm, Ghostty…) needs **Screen Recording**,
**Accessibility**, **Input Monitoring** and **Microphone** in System Settings → Privacy & Security. Grants apply
to a freshly started app. `uv run holo doctor` checks the H side.

## Run

### 1. The assistant (macOS)

```bash
export HCS_PTT_KEY=ctrl+shift+h        # push-to-talk shortcut (or cmd+j, alt_r, f9)
uv run hcs-agent talk                  # the voice loop: hold the shortcut, speak, release
```

Other commands:

```bash
uv run hcs-agent procedures            # list the scripted procedures
uv run hcs-agent run --mode guide --procedure odoo_crm_create_opportunity \
    --goal "Create the Acme Demo opportunity" -p opportunity="Acme Demo"
uv run hcs-agent run -y --mode act --procedure odoo_crm_log_note --goal "Log a call" -p opportunity="Acme Demo"
uv run hcs-agent run --mock -y --procedure odoo_crm_change_stage_restricted --goal "Mark Acme Demo as won"
uv run hcs-agent serve [--mock]        # local HTTP/WebSocket API on 127.0.0.1:8765
uv run hcs-agent cleanup               # close orphaned H sessions that hold concurrency slots
```

`--mock` (or `HCS_MOCK=1`) runs everything against a simulated H backend: no key, no desktop control, and every
event and report is flagged `simulated: true`. Reports are written to `runs/<session>/report.json`; to send them to
the support backend, set `HCS_BACKEND_URL=http://127.0.0.1:8766` and `HCS_INGEST_TOKEN` (same as the backend's).

### 2. The desktop app

```bash
npm start --prefix desktop             # connects to the assistant on 127.0.0.1:8768 by itself
```

On macOS, `Launch H Companion.command` (double-click in Finder) starts the menu-bar companion, and
`python3 scripts/install-macos-launcher.py` installs a local `H Companion.app` shortcut in `~/Applications`.
Details: [desktop/README.md](desktop/README.md).

### 3. The support backend and dashboard

```bash
.venv/bin/hcs-backend seed-demo --reset   # optional: 4 demo cases, flagged demo_data + simulated
.venv/bin/hcs-backend serve               # http://127.0.0.1:8766/dashboard (user "support")
.venv/bin/hcs-backend fix <case_id>       # ask Devin to fix the defect behind a case (allowlisted repos)
```

API, grouping rules and the escalation file: [backend/README.md](backend/README.md).

### 4. Vision: gaze tracking, Vision Lab and heatmap

In the desktop app: **Vision** tab → turn on "Use my gaze" → **Recalibrate**. The background tracker needs a
one-time setup (see [desktop/tracker/README.md](desktop/tracker/README.md)):

```bash
python3 -m venv desktop/tracker/.venv && desktop/tracker/.venv/bin/pip install -r desktop/tracker/requirements.txt
```

The Vision Lab (macOS) and the heatmap test page:

```bash
cp app/.env.example app/.env && npm run dev --prefix app      # Vision Lab: calibration, gaze region, Holo analysis
python3 -m http.server 5174 --bind 127.0.0.1 --directory heatmap   # heatmap test page (mouse as the eyes)
```

[app/README.md](app/README.md) · [heatmap/README.md](heatmap/README.md) ·
[research protocol](docs/gaze-research-protocol.md).

### 5. Voice pilot and isolated browser pilot

See [pilot/README.md](pilot/README.md) and [docs/isolated-browser-pilot.md](docs/isolated-browser-pilot.md).

### 6. Website

```bash
python3 -m http.server 5173 --bind 127.0.0.1 --directory landing   # http://127.0.0.1:5173
```

Click the H key (or press `h`).

## Tests

```bash
uv run pytest                          # agent + backend (simulated backend, no key needed)
npm test --prefix desktop              # desktop app UI logic
npm test --prefix app                  # Vision Lab (vitest)
npm test --prefix heatmap              # heatmap maths
uv run pytest bench                    # benchmark helpers (no call; real runs: bench/README.md)
```

Tests never need an H key: they run against the simulated backend.

## Shared contract

A request carries `session_id, software, role, goal, procedure_id, parameters, mode, autonomy`. Commands are
`approve`, `stop`, `next`, `autonomy`, `feedback`. Events expose the state, each step, guidance, documentation
lookups, `needs_human` and `finished`. The report separates the agent's **declared** result from the **verified**
postcondition and carries `category`, `status`, `escalation`, `evidence`, `timings`, `cost_usd` and the user's
`feedback`. Source of truth: [`agent/src/hcs_agent/contract.py`](agent/src/hcs_agent/contract.py); JSON Schemas in
[`contracts/`](contracts/), regenerated with `uv run python scripts/export_contracts.py`.

## Privacy

- Vision is opt-in and off by default. Gaze tracking runs locally (background tracker or browser engine); no image
  of the user's face is stored or sent anywhere. Only screen coordinates reach the agent, and only screen regions
  go to the model.
- The overlay and the desktop app are excluded from screen capture.
- Screenshots reach support only when the evidence is marked shareable and the user allowed it.
- Keys stay in git-ignored `.env` files and are never sent to the desktop app's interface.
