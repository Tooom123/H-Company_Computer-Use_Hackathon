# Live pitch: H Platform → Companion → support report

Prepared on 2026-11-08 from main `287c4c1`, with the safe Vision calibration fixes retained.
Branch: `edouard/demo-live-crop`. No public deployment is needed for this pitch.

## The short live sequence

1. Open `https://platform.hcompany.ai/` in Chrome, with the sidebar visible.
2. Keep H Companion's Vision option on and the calibrated tracker running. Look toward the sidebar.
3. Hold **Right Option**, ask **“Show me where to create a new agent, without starting a task.”**, then release.
4. Follow the coach's instruction. Finish the interaction before switching to the dashboard.
5. Open `http://127.0.0.1:8795/dashboard/live` to show the actual model image and the report received by the backend.
6. In Companion's Activity view, rate usefulness yourself. The dashboard distinguishes this human label from automatic verification.

An optional second question is **“How can I run an agent without taking over my computer? Show me where to configure it.”**
These are rehearsal prompts, not a claim that the current end-to-end take has passed. Rehearse the first one before adding the second.

## What the image panel proves

- The saved JPEG is byte-for-byte the image attached to the instrumented H Models API request.
- Its dimensions, SHA-256, crop coordinates and screen-area ratio come from that request.
- Latency is the measured request duration including retries. Input tokens are the API's reported total for text + image.
- Crop and full-screen requests remain separate. A full-screen fallback is not hidden.
- The panel covers the instrumented Models API visual requests, not an exhaustive archive of Agents API screenshots.
- Reduced screen area does **not** establish token savings. Do not claim a percentage saving without a paired measurement.

The explicit visual demo option asks Holo to localise the first actionable target of a dynamically planned guide even when accessibility already provides coordinates. Subsequent steps keep the fast accessibility path. In normal mode this extra call is disabled. It can add latency; it is a real inference, not a visual simulation.

## Local launch and credentials

Use the installed **H Companion.app**, or from this checkout:

```sh
/usr/bin/python3 scripts/start-devin-companion.py --profile hcompany-vision
```

On Edouard's Mac, `main-vision-coach/launcher.json` in the private HCompanionResearch directory has `pitch_demo: true`. This adds `--record-vision --visual-grounding-demo` to the human runtime. Set it to false before restarting the engine to return to the normal fast path.

Other machines can pass these flags to `scripts/run-h-company-human.py` with their existing private environment and distinct local ports. No credential is included in this document.

The dashboard retains its HTTP Basic authentication. Its username/password are in the private runtime's `credentials.json`. The ingest token is for the agent only. If browser automation refuses the HTTP Basic prompt, open a normal Chrome tab and sign in there before using the viewer.

Private data on this Mac stays below `~/Library/Application Support/HCompanionResearch/main-vision-coach/`:

- `episodes/`: local session traces and reports;
- `backend.sqlite3`: reports and live events received through the existing uplink;
- `vision-payloads/`: opt-in exact JPEG payloads and request metadata.

None of these files belong in Git. Webcam images are not recorded by this feature.

## Stage checks

- Engine control: `http://127.0.0.1:8794/status` with `X-HCS-App: 1`.
- Vision must report `enabled: true`, `live: true`; after an engine-only restart restore the Vision toggle if needed. Do not restart the desktop or tracker and lose calibration.
- Dashboard: sign in before presenting. A case appears when the intervention ends; events appear while it runs.
- Use Stop task if the coach loops. An interrupted run must remain labelled interrupted, not successful.
- Keep the portal on the same Mac for this pitch. `hcompanion.help` is the landing page, not this private live dashboard.

Validation: 111 targeted automated checks passed (guidance, gaze cropping, exact image payload persistence, authenticated routes, launcher and backend). A fresh live voice/crop/report rehearsal is still required.
