# H Companion — desktop app (Tom)

The assistant's home window, like a dictation app: you work in your software, the app sits next to it.
Plain Electron, no build step. It steers the agent that runs on this Mac (`hcs-agent talk`).

| Page | What it does |
| --- | --- |
| Home | Live status (your turn · step N of M, I'm doing it, checking it worked, done ✓), the current task with a **Stop** button, the **Magnet** (autonomy) drawn like the overlay, this month's tasks / checked / typical task time. |
| Activity | Last tasks from the agent's reports: checked / to support / stopped, guided or done by the assistant, duration, simulated flag. |
| Voice | Spoken notes on/off, voice (Sarah, Jessica, Bella, Matilda: plain American), speed, test; **push-to-talk key** (⌘H, ⌘J, Right ⌥, F9), applied live. |
| Vision | **Recalibrate**: opens Édouard's Vision Lab (in testing) on the calibration screen. |

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
npm run smoke -- --section=usage           # renders, writes smoke-usage.png, quits
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
