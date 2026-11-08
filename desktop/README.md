# H Companion — desktop app (Tom)

The assistant's home window, like a dictation app: you work in your software, the app sits next to it.
Plain Electron, no build step. It steers the agent that runs on this Mac (`hcs-agent talk`).

Five tabs centred on top, like a browser (the active one with a red-tinted shadow), and the landing's stick
figure sitting on the edge of the bar, legs swinging:

| Tab | What it does |
| --- | --- |
| Home | Idle: Matteo's paper badge "⌃⇧H: new request" (the same words as on screen; "Listening…" only while the key is held). During a task: the task, "Now you: <step>" / "I'm doing it", the steps, **Stop**. Autonomy: a wide pencil slider on a paper scrap, the three levels written out under the rail (Show me, Help if I'm stuck, Do it, I watch), the chosen one a red dot in scribbled loops (the overlay's strokes). This month: tasks, checked, typical time. |
| Activity | The tasks you asked for, checked / to support / stopped, and your verdict **✓ / ✗**, the chosen one circled in red pencil like a graded paper: written in the report's `feedback.useful` and sent again to the support backend (debug, learning what works). |
| Mon retour | Explicit spoken or written comment, separate task-success and usefulness labels. No label is preselected. |
| Voice | Spoken notes on/off, voice (Sarah, Jessica, Bella, Matilda: plain American), speed, test; **push-to-talk key** (⌃⇧H, ⌘J, Right ⌥, F9), applied live. |
| Vision | **Recalibrate**: opens Édouard's Vision Lab on the calibration screen. |

User side only: costs, H compute and the plan belong to the admin / IT side (support backend), not here.
The window is excluded from screen capture (like the overlay): H never sees it and the guide's screen watcher
does not take its live updates for the user acting; clicks inside it never count as doing a step.
`HCS_APP_CAPTURABLE=1` makes it recordable for a demo video.

**Autonomy moved into the app**: while the panel is visible, the Magnet slider leaves the screen; hide the panel and
it comes back. On macOS the close button hides the panel and keeps the menu-bar companion available.
Changing the level mid-task applies at once ("Do it, I watch" during a guide = takeover).
Preset voice, speed and safe key choices are remembered. An explicitly configured custom voice wins over an old preset; observation-only sessions keep autonomy at zero.

## Stop a task yourself

- **Button:** while a task runs, **Stop task** stays in the bar just below the tabs, including Voice and Mon retour. The Home card also keeps its Stop button. The macOS menu-bar icon also provides **Stop task** and **Open H Companion**, even when the window is hidden.
- **Voice:** hold the push-to-talk shortcut shown by the app (normally **Ctrl+Shift+H**), say **“Stop”**, **“Stop task”**, **“Arrête”** or **“Arrête la tâche”**, then release. Casing, accents and final punctuation are tolerated; longer sentences mentioning Stop remain normal requests. “Stop the task” is also accepted. Recognition occurs after transcription, not while the microphone is still held.
- The button shows **Stopping…** while stopping. Acceptance means a stop was requested; **Task stopped** only appears once the runtime reports that terminal state. A failed request stays visible and can be retried.
- If **Dicter mon retour** was armed, the next transcription is feedback, even when it is just “stop”. Use the button to stop in that case. Stopping never creates feedback labels or a new task.

## Run

### Finder / menu-bar launcher for the Devin pilot (macOS)

On the demo Mac, **Applications → H Companion.app** is the Finder/Spotlight entry
point. It has the companion icon and invokes the same launcher below, reopening
the existing window or starting the coach as needed. To install that local
shortcut on another Mac after setting up the dependencies:

```sh
python3 scripts/install-macos-launcher.py
# Optional shared Applications folder, if writable:
python3 scripts/install-macos-launcher.py --destination '/Applications/H Companion.app'
```

The default destination is `~/Applications/H Companion.app`. The installer refuses
to overwrite an existing app. It uses the installed Swift compiler and macOS icon
tools; no credentials are embedded. This shortcut points to this local checkout
and Python environment: it is not yet a standalone distributable application.

Double-click **`Launch H Companion.command`** at the repository root. This starts
the native Devin coach on ports 8780/8781 and opens its panel. The small companion
icon in the macOS menu bar offers **Open H Companion**, **Stop task**,
**Start Devin coach** (reuse or restart the coach) and **Quit H Companion**.
Closing the panel keeps that icon; quitting the desktop app removes the icon.
The coach is a separate process: use **Stop task** to stop the current intervention.

The launcher detaches the runtime from the terminal and writes logs only to
`~/Library/Application Support/HCompanionResearch/human-cognition/`.
It reuses a ready native Devin runtime whose PID matches its metadata, refuses
occupied ports belonging to another runtime, and never stops unrelated processes.
Repeated panel launches reopen the existing window. There is no login-time service
or automatic background restart.

Dependencies: run `uv sync --all-packages` and `npm ci --prefix desktop`, or set
`HCS_PILOT_PYTHON` to an existing Python environment. This Mac can also keep its
interpreter path (not keys) in private `human-cognition/launcher.json`:
`{"python":"/absolute/path/to/venv/bin/python"}`. The generic launcher itself uses
only Python's standard library. Secrets continue to be read by the existing runtime.

### Development / other software

```bash
uv run hcs-agent talk          # repo root, on the Mac (the app also works with `run`)
cd desktop && npm install && npm start
```

The app talks to the agent's control point on `127.0.0.1:8768` (`agent/src/hcs_agent/control.py`) and to the
no key lives in the app.
Env: `HCS_CONTROL_URL`, `HCS_BACKEND_URL`; agent side `HCS_CONTROL=0` disables the control point,
`HCS_CONTROL_PORT` moves it.

## Check without a Mac

```bash
npm test                                   # UI logic (node --test)
npm run smoke -- --section=activity        # renders, writes smoke-activity.png, quits (own temp profile)
HCS_SMOKE_JS='document.getElementById("stopBtn").click()' npm run smoke   # click, then capture
```

Verified on Linux against a simulated agent (`hcs-agent run --mock --mode guide`): live step, autonomy click →
takeover, Stop click → abandoned (stop latency 0 s), Magnet hidden/shown with the app.
Not yet seen on the Mac: the Magnet hide/show (AppKit), hand fonts, the Vision Lab start.

## Next (to iterate with Matteo)

- A small floating pill (status + Stop) for when the window is hidden.
- Approval prompt in the app when `talk --confirm` is used.
- Admin / IT page for costs and plan (H compute, ElevenLabs, Gladia, Linkup) in the support backend.
- Gaze from the Vision Lab feeding the agent (where the user is stuck).

## Window and autonomy slider

- Frameless on Linux and Windows (GNOME on Wayland gave the window no title bar: it could not be moved,
  minimised or closed). The black tab bar is the title bar: drag it to move the window; minimise / maximise /
  close at its top right; Ctrl+W closes, Ctrl+M minimises. macOS keeps its traffic lights.
- Autonomy: drag the red dot along the rail, click anywhere on the scrap (nearest level), or arrow keys / 1 2 3.
  It snaps on release, applies at once, and says when it hit the running task or when the assistant did not answer.
