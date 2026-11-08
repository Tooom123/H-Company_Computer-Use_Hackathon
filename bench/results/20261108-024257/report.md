# Gaze-assisted grounding benchmark — 2026-11-08 01:43 UTC

2 trials on 1 synthetic screens (1440×900), simulated gaze with a median error of 120 px, 10 % of trials looking elsewhere (1 here). Crop = heatmap ROI + 40 px, min 512×320.

Model: `holo4-35b-a3b` (H Models API, thinking off), same request as the agent's grounding.

| | Full screen (F) | Gaze crop + fallback (G) |
|---|---|---|
| success (centre inside the target) | 2/2 | 2/2 |
| median time per locate | 2.60 s | 1.67 s (64% of F) |
| mean prompt tokens | 1118 | 1323 (118% of F) |
| median pixels sent | 655,360.0 | 187,904.0 (29% of F) |
| fell back to full screen | — | 1/2 |

G's time and tokens include the fallback calls (both calls are paid when the crop misses).
Synthetic screens and simulated gaze: a pilot on the method, not a result on real users (see docs/gaze-research-protocol.md, experiment A).
