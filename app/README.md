# app (Edouard)

Electron user app: describe the goal and role, show what the assistant will observe and change, collect
approval, display progress and the stop button, show the verified result or the escalation, collect feedback.

Talks to the local agent API (`hcs-agent serve`, `127.0.0.1:8765`):

| Method | Path | Body / result |
| --- | --- | --- |
| POST | `/interventions` | `InterventionRequest` → snapshot with `plan` (state `awaiting_approval`) |
| POST | `/interventions/{id}/approve` | `ApproveCommand` |
| POST | `/interventions/{id}/stop` | `StopCommand` |
| POST | `/interventions/{id}/feedback` | `FeedbackCommand` |
| GET | `/interventions/{id}` | snapshot |
| GET | `/interventions/{id}/report` | `InterventionReport` (425 until finished) |
| WS | `/interventions/{id}/ws` | `AgentEvent` stream (history replayed first, ends on `finished`) |

Schemas: `../contracts/`. Run the agent in simulated mode while building: `HCS_MOCK=1 hcs-agent serve`.
Show a visible "simulated" badge whenever `event.simulated` is true.

```bash
npm install
npm run dev
```
