# H Companion — desktop app (Tom)

The assistant's home window, like a dictation app: you work in your software, the app sits next to it.
Plain Electron, no build step. It steers the agent that runs on this Mac (`hcs-agent talk`).

Four tabs centred on top, like a browser (the active one with a red-tinted shadow), and the landing's stick
figure sitting on the edge of the bar, legs swinging:

| Tab | What it does |
| --- | --- |
| Home | Idle: Matteo's paper badge "⌘H: new request" (the same words as on screen; "Listening…" only while the key is held). During a task: the task, "Now you: <step>" / "I'm doing it", the steps, **Stop**. Autonomy: a wide pencil slider on a paper scrap, the three levels written out under the rail (Show me, Help if I'm stuck, Do it, I watch), the chosen one a red dot in scribbled loops (the overlay's strokes). This month: tasks, checked, typical time. |
| Activity | The tasks you asked for, checked / to support / stopped, and your verdict **✓ / ✗**, the chosen one circled in red pencil like a graded paper: written in the report's `feedback.useful` and sent again to the support backend (debug, learning what works). |
| Voice | Spoken notes on/off, voice (Sarah, Jessica, Bella, Matilda: plain American), speed, test; **push-to-talk key** (⌘H, ⌘J, Right ⌥, F9), applied live. |
| Vision | **Recalibrate**: opens Édouard's Vision Lab on the calibration screen. |

User side only: costs, H compute and the plan belong to the admin / IT side (support backend), not here.
The window is excluded from screen capture (like the overlay): H never sees it and the guide's screen watcher
does not take its live updates for the user acting; clicks inside it never count as doing a step.
`HCS_APP_CAPTURABLE=1` makes it recordable for a demo video.

**Autonomy moved into the app**: while the app is open, the Magnet slider leaves the screen; close the app and
it comes back. Changing the level mid-task applies at once ("Do it, I watch" during a guide = takeover).
Voice, speed and key chosen in the app are remembered and pushed again when the assistant restarts.

## Run

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

- Menu-bar icon and a small floating pill (status + Stop) for when the window is hidden.
- Approval prompt in the app when `talk --confirm` is used.
- Admin / IT page for costs and plan (H compute, ElevenLabs, Gladia, Linkup) in the support backend.
- Gaze from the Vision Lab feeding the agent (where the user is stuck).

## Window and autonomy slider

- Frameless on Linux and Windows (GNOME on Wayland gave the window no title bar: it could not be moved,
  minimised or closed). The black tab bar is the title bar: drag it to move the window; minimise / maximise /
  close at its top right; Ctrl+W closes, Ctrl+M minimises. macOS keeps its traffic lights.
- Autonomy: drag the red dot along the rail, click anywhere on the scrap (nearest level), or arrow keys / 1 2 3.
  It snaps on release, applies at once, and says when it hit the running task or when the assistant did not answer.
