# Gaze-assisted grounding benchmark (Tom)

**Question.** Today the agent sends Holo the whole screen and asks it to find the control. If we know roughly
where the user is looking (the webcam honeycomb, `heatmap/vision.html`), can we send only that part of the
screen, pay less compute per screenshot, and still find the control, falling back to the full screen when the
gaze was elsewhere? This is experiment A of `docs/gaze-research-protocol.md` (modes F and G), on Holo.

| Mode | Image sent to Holo | When it misses |
| --- | --- | --- |
| **F** full screen | whole 1440×900 screen, downscaled to 1024 px wide: exactly the agent's request today (`agent/src/hcs_agent/grounding.py`, same prompt, same tool, thinking off) | — |
| **G** gaze crop | heatmap ROI around the gaze + 40 px, at least 512×320, native resolution | Holo answers "not here" → the full screen is sent; **both calls are counted** |

Measured per trial: success (the centre Holo returns, mapped back to screen pixels, is inside the target's box),
wall time, prompt / completion tokens (API usage), pixels and bytes sent. F and G alternate order.

## Run

```bash
# 1. measure your gaze error on the vision page (accuracy after calibration, e.g. ~120 px)
# 2. build the dataset with it (Electron renders the screens; the crop comes from heatmap/gaze-heatmap.js)
ELECTRON_RUN_AS_NODE= desktop/node_modules/electron/dist/electron bench/make_dataset.mjs --error-px 120 --repeats 3 --miss-rate 0.1
# 3. dry run (no key): pixels, how often the target is in the crop, preview images of what G sends
.venv/bin/python bench/run_bench.py --dry-run
# 4. real run (H key, H Models API; ~2 calls per trial, ~100 calls for the 51 trials)
HAI_API_KEY=... .venv/bin/python bench/run_bench.py
```

Results go to `bench/results/<date>/` (`report.md`, `results.json`, `previews/`). Commit the real ones.

## Dataset (`bench/data/`, committed, reproducible with `--seed`)

- 3 synthetic Odoo-like screens (`bench/screens/`): CRM pipeline, settings, draft invoice. Dense on purpose,
  with repeated controls (stars, clocks, trash icons, checkboxes) where a crop around the gaze removes look-alikes.
- 17 tasks × 3 gaze draws = 51 trials. Gaze = target centre + 2-D gaussian noise whose **median error is the one
  measured on the vision page**; 10 % of trials look elsewhere (≥ 300 px away) to exercise the fallback.
- The gaze is decided before any model call and never uses the answer (protocol rule).

## Dry run so far (Linux, no key)

| | F | G |
| --- | --- | --- |
| median pixels sent | 655,360 | 247,296 (38 % of F) |
| target fully inside what is sent | 51/51 | 47/51 (the 4 "looking elsewhere" trials fall back) |

## Honest limits

- Synthetic screens and simulated gaze: a pilot on the method, not a result on real users or real software.
  Next: real Odoo screenshots with annotated targets, and gaze recorded on the vision page instead of simulated.
- G sends a crop at native resolution while F is downscaled: part of any accuracy gain may come from the extra
  sharpness, not from the gaze. A "crop without gaze" control (fixed centre crop) separates the two (protocol C/O).
- Latency includes network and rate-limit waits; they hit both modes alike, but run it on a quiet connection.
