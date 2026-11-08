# Notes for the other agents (from Matteo's side): running and testing the Devin Desktop coach

State: 2026-11-08. Checked on Matteo's Mac (Devin Desktop installed at `/Applications/Devin.app`). Anything not
measured is marked as such.

## Two launchers, two products: do not mix them up

| What you want to coach | Command | Push-to-talk key |
| --- | --- | --- |
| H Company platform in **Chrome** | `uv run hcs-agent talk` | `HCS_PTT_KEY` from `.env` (Matteo: ⌘H) |
| **Devin Desktop** (Cognition, native app) | `uv run --all-packages python scripts/run-h-company-human.py --software cognition --native-devin --input-language fr-en` | **Ctrl+Shift+H** by default (`--key` to change it) |

- `hcs-agent talk` alone routes to **hcompany in the browser**. It never reads the Devin window
  (log line `-> ... | hcompany` and `browser accessibility tree: ...`). Using it in front of Devin "does not work"
  by design.
- `Launch H Companion.command` (repo root) starts the same Devin runtime as the second line.
- The Devin launcher ignores `HCS_PTT_KEY` in `.env`: it passes its own `--key` (default `ctrl+shift+h`). The badge
  on screen shows the active key. Avoid `--key cmd+h` in Devin: ⌘H is macOS "Hide app" (not verified whether we
  swallow it there).
- Keys: the launcher reads `HAI_API_KEY` / `GLADIA_API_KEY` / `ELEVEN` from `app/.env`, `agent/.env` and the
  **root `.env`** (root added in `e919acb`; before it, the launcher stopped with "HAI_API_KEY and GLADIA_API_KEY
  are required in the private environment."). Private traces go to
  `~/Library/Application Support/HCompanionResearch/human-cognition/` (not in git): ask for that folder when
  someone reports a bad Devin run.
- Before speaking: Devin Desktop in front (the coach reads only its focused window), wait for "Listening…"
  (speaking earlier clips the start of the sentence), and preferably while Devin shows "Devin is awaiting
  instructions" (see open issue below).
- macOS permissions for the terminal that launches it (Ghostty, iTerm…): Accessibility, Input Monitoring,
  Microphone, Screen Recording; restart the terminal after granting.

## What the coach sees in Devin Desktop (probe 2026-11-08, Devin 3.12)

The focused window exposes ~121 named elements; the planner gets at most 90. Visible controls include:
top bar `Expand sidebar`, `Agents`, `Back`, `Forward`, `Report session`, `Session settings`, `Show tabs panel`;
per message `Copy`, `Edit message`, `Revert to this point`, `Fork from here`, `Good response` / `Bad response`,
`View response statistics`, `Duplicate session`, `Other actions`; changes `Quick review`, `View changes`,
`Mark as seen`; prompt area `Prompt`, `Attach or mention`, `Commands and skills`, `Mode`, `Session folder`,
model picker (`Fusion`), `Context usage`, `Record voice prompt`, `Send`.

## Questions to test with (English answers; French or English input)

- Prepared, should be reliable: "Show me what files this session changed, without accepting anything." /
  "Which model is selected? Show me the models without changing it." / "Show me where to switch between Ask and
  Agent mode. Don't submit anything." / "Where are the settings for this session?"
- Unprepared (generalisation test): "Where can I report a problem with this session?" / "How do I tell Devin its
  answer was bad?" / "How do I change which folder this session works in?" / "How do I go back to the session I
  had before this one?"
- Boundary (a correct refusal is the expected result): "Where can I redeem a coupon code?" / "Send this prompt to
  Devin for me." / "How do I connect Devin to Slack?"
- Pass = the frame is on the control the sentence names, and the next step accounts for what opened.
  Fail = frame on another control, same instruction repeated, or an invented control. Log each try in
  `docs/test-log.md`.

## Fixes landed on `matteo` (2026-11-08)

1. `ff9eb6e` guide loop: instruction and frame must name the same control (retarget or re-plan); the history now
   tells the planner which controls appeared / disappeared after each action; the same step back on a page where
   it was already shown is re-planned once, then handed over. (Was: "Click Build" framed on the wizard's Close,
   four times.)
2. `4292e79` native catalogue: the 90-item cut used to drop the whole top bar (walk lists the bottom first) and
   keep ~60 timeline ticks (`5:35 AM`, 8 px) and diff counters (`72`, `+`). Native mode now keeps controls first,
   then headings, then text with words, nothing under 10 px, in reading order. Chrome path unchanged.
3. `f5ef7f4` unscripted requests crashed (`ValueError: Invalid format specifier ' sessionId '`) when the docs map
   carried literal braces; templates now substitute only `{parameter}` placeholders.
4. `e919acb` Devin launcher reads the root `.env`.

## Open issue (not measured)

While planning a native step, the runner discards the plan if anything in the window changed, static text
included (`runner.py`, "Native window changed while planning"). While Devin streams an answer the window never
settles, so every plan may be discarded and nothing shown. Measure it with a running Devin session before
changing it; the likely fix is to compare controls only, not text.
