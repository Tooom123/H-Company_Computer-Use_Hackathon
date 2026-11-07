# app (Edouard)

Electron user app: describe the goal and role, show what the assistant will observe and change, collect
approval, display progress and the stop button, show the verified result or the escalation, collect feedback.

Talks to the local agent API (`hcs-agent serve`, `127.0.0.1:8765`):

| Method | Path | Body / result |
| --- | --- | --- |
| POST | `/interventions` | `InterventionRequest` → snapshot with `plan` (state `awaiting_approval`) |
| POST | `/interventions/{id}/approve` | `ApproveCommand` |
| POST | `/interventions/{id}/stop` | `StopCommand` |
| POST | `/interventions/{id}/next` | `NextCommand` — guide mode, after a `guidance` event (state `awaiting_user`) |
| POST | `/interventions/{id}/autonomy` | `AutonomyCommand {level: 0|1|2}` — the Magnet, live; 2 while guiding = the agent takes over |
| POST | `/interventions/{id}/feedback` | `FeedbackCommand` |
| GET | `/interventions/{id}` | snapshot |
| GET | `/interventions/{id}/report` | `InterventionReport` (425 until finished) |
| WS | `/interventions/{id}/ws` | `AgentEvent` stream (history replayed first, ends on `finished`) |

Schemas: `../contracts/`. Run the agent in simulated mode while building: `HCS_MOCK=1 hcs-agent serve`.
Show a visible "simulated" badge whenever `event.simulated` is true.

Request `mode` is `act` (agent does it) or `guide` (agent explains and points), `autonomy` 0-2 is the Magnet
level. Each `guidance` event carries `step` with `instruction`, `why`, `kind` (click / type / key / info / wait),
`pointer` (screen points), `box` (x, y, w, h of the control) and `annotations[]` (extra marks with their own
`box` and short `text`): draw them on screen (the Python CLI draws a hand-sketched overlay; the app may do the
same or render a side card). Call `/next` with `{done: true}` when the user did it, `{done: false, note}` when
stuck. Snapshot fields `takeover` and `mode` tell whether the agent is now acting; in that case `step` events
with `detail.tools` are the agent's actions (`detail.pointer`, `detail.element`) for live narration.

```bash
npm install
npm run dev
```
