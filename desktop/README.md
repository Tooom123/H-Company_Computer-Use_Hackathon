# H Companion — desktop app (Tom)

The assistant's home window, like a dictation app: you work in your software, the app sits next to it.
Plain Electron, no build step. It steers the agent that runs on this Mac (`hcs-agent talk`).

| Page | What it does |
| --- | --- |
| Home | Live status (listening, step N of M, taking over, checking, verified), the current task with a **Stop** button, the **autonomy** setting, this month's numbers. |
| Activity | Last sessions from the agent's reports: verified / to support / stopped, duration, cost, simulated flag; opens the case in the support dashboard. |
| Usage & plan | Plan credits (Starter 25 sessions / month, Pro, Fix pack 100 verified fixes) with Stripe checkout (test mode), and what each service costs: H compute this month and live sessions, ElevenLabs characters, Gladia / Linkup connected. |
| Voice | Spoken notes on/off, voice (Sarah, Jessica, Lily, Alice), speed, test; push-to-talk key. |
| Vision | Opens Édouard's Vision Lab (`app/`). |

**Window**: frameless on Linux and Windows with its own bar: drag it to move the window, minimise / maximise /
close on the right, Ctrl+W closes, Ctrl+M minimises (GNOME on Wayland gave the window no title bar at all).
macOS keeps its native traffic lights.

**Autonomy slider**: three stops, drag the thumb, click a stop or a label, or use the arrow keys (1/2/3 too).
It snaps on release and says when the change hit the running task ("Taking over the current task now").
Labels and hints come from the agent's `/status` when present, so they match the Magnet.

**Autonomy moved into the app**: while the app is open, the Magnet slider leaves the screen; close the app and
it comes back. Changing the level mid-task applies at once ("Do it, I watch" during a guide = takeover).

## Run

```bash
uv run hcs-agent talk          # repo root, on the Mac (the app also works with `run`)
cd desktop && npm install && npm start
```

The app talks to the agent's control point on `127.0.0.1:8768` (`agent/src/hcs_agent/control.py`) and to the
support backend on `:8766` (checkout, dashboard). No key lives in the app.
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
- Gladia / Linkup usage numbers (their APIs), plan linked to the Stripe customer instead of a local choice.
- Gaze from the Vision Lab feeding the agent (where the user is stuck).
