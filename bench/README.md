# Gaze-assisted grounding benchmark

**Question.** Today the agent sends Holo the whole screen and asks it to find the control. If we know roughly
where the user is looking (the webcam honeycomb, `heatmap/vision.html`), can we send only that part of the
screen, pay less compute per screenshot, and still find the control, falling back to the full screen when the
gaze was elsewhere? This is experiment A of `docs/gaze-research-protocol.md`, run on Holo.

| Mode | Image sent to Holo | When it misses |
| --- | --- | --- |
| **F** full screen | whole 1440×900 screen downscaled to 1024 px wide: exactly the agent's request today (`agent/src/hcs_agent/grounding.py`, same prompt, same tool, temperature 0, thinking off) | — |
| **Fn** full native | whole screen at 1440 px: control for sharpness | — |
| **G** gaze crop | heatmap ROI around the gaze + 40 px, at least 512×320, native resolution, with a "not here" escape | the full screen (F) is used; **both calls are counted** |
| **G variants** | `plain` (F's prompt), `min768` (crop ≥ 768×480), `min768plain` (both), `up1024` (crop upscaled) | same fallback |
| **C** centre crop | same size as G's crop, at the screen centre: control without gaze | same fallback |

Measured per call: success (the centre Holo returns, mapped back to screen pixels, is inside the target's box,
± 2 px), wall time of the request, prompt / completion tokens (API usage) and cost from the API's prices, pixels and
bytes sent. Text-only baselines isolate the fixed prompt + tool tokens. Calls are shuffled across modes and models.
Statistics: Wilson intervals for rates, bootstrap for medians, exact McNemar for paired comparisons.

## Run

```bash
set -a; . backend/.env; set +a        # HAI_API_KEY (never printed, never committed)
# 1. dataset: Electron renders the screens and the real websites of sites.txt; crops from heatmap/gaze-heatmap.js
ELECTRON_RUN_AS_NODE= desktop/node_modules/electron/dist/electron bench/make_dataset.mjs --errors 60,120,200 --draws 2 --elsewhere 1
# 2. dry run (no key): pixels, how often the target is in the crop, preview images of what G sends
.venv/bin/python bench/run_bench.py --dry-run
# 3. real run; resumable (--resume <dir>), reports rebuilt without calls (--report <dir>)
.venv/bin/python bench/run_bench.py --models holo4-35b-a3b,holo4-27b --workers 4 \
    --variants "min768plain:gaze60,gaze120,gaze200,elsewhere"
```

Every call is appended to `results/<date>/calls.jsonl` as soon as it returns; `report.md` and `summary.json` are
built from it. Rate-limited calls (HTTP 429) are recorded as errors and retried by `--resume`.

## Dataset (`bench/data/`, `bench/data-confirm/`, committed, reproducible with `--seed`)

- **Real websites** captured once at 1440×900, logged out, cookie banners included (`sites.txt`: Wikipedia EN/FR,
  Hacker News, python.org, MDN, gov.uk, odoo.com, hcompany.ai, GitHub, npm, Stack Overflow, Le Monde, Craigslist).
  Targets drawn automatically among visible, unobstructed controls whose label is unique on the page, spread over
  the screen; icon buttons are named by their aria-label.
- **3 synthetic Odoo-like screens** (`screens/`): CRM pipeline, settings, draft invoice, with hand-written tasks and
  many look-alike controls (stars, clocks, trash icons, checkboxes).
- **Gaze**: per task, 2 draws per webcam quality (median error 60 / 120 / 200 px, 2-D gaussian around the target)
  and 1 "looking elsewhere" draw (≥ 300 px away). It is decided before any model call and never uses the answer.

## Results (H Models API, real calls)

Two runs, both with the agent's grounding request (`holo4-35b-a3b`, temperature 0, thinking off):

- **Exploration** `results/20261108-024922/` — 5,206 calls, 3 models (holo4-35b-a3b, holo4-27b, holo3-1-35b-a3b),
  15 screens (12 real websites + 3 synthetic Odoo-like), 104 tasks, 728 gaze trials, plus G variants.
- **Confirmation** `results/20261108-050543/` — 2,018 calls on a **fresh dataset** (`data-confirm/`, seed 7,
  sites re-captured, new targets and gaze draws): 112 tasks, 784 gaze trials. It tests the variant chosen
  during exploration, so that choice is not judged on the data it was picked from.

Confirmation run, holo4-35b-a3b (95 % intervals in the report):

| strategy | success | median time | cost / 1000 locates | pixels sent |
| --- | --- | --- | --- | --- |
| F · full screen 1024 px (today) | 106/112 (95 %) | 1.25 s | $0.533 | 655,360 |
| G · first crop (≥ 512×320), gaze ~120 px | 187/223 (84 %) | 1.02 s | $0.455 | 217,600 |
| **G · crop ≥ 768×480, F's prompt, gaze ~60 px** | **216/223 (97 %)** | **1.13 s** | **$0.490** | 368,640 |
| **G · crop ≥ 768×480, F's prompt, gaze ~120 px** | **211/224 (94 %)** | **1.19 s** | **$0.496** | 368,640 |
| G · crop ≥ 768×480, F's prompt, gaze ~200 px | 217/224 (97 %) | 1.23 s | $0.530 | 476,880 |
| C · centre crop of the same size, no gaze | 205/224 (92 %) | 2.01 s | $0.794 | 217,600 |

What the two runs support:

1. **A tight crop loses accuracy.** With a crop of at least 512×320, Holo often picks a neighbour among small,
   dense links (Hacker News, Wikipedia), although the target is inside the crop: 84–87 % vs 92–95 % for F,
   significant in both runs. Not a coordinate bug (median offset ~1 px in every mode), not the crop's edge, not
   the "zoomed crop" sentence (removing it changes nothing).
2. **A less tight crop fixes it.** At least 768×480 around the gaze, with F's own prompt: **as accurate as the
   full screen** (94–97 % vs 95 %; no significant difference on the fresh data, p = 0.23–1.0) and far better than
   the tight crop (+25 / −2 trials, p < 0.001). A gain over F seen in the exploration run (97 % vs 92 %, p = 0.02)
   did **not** replicate: we claim equal accuracy, not better.
3. **What it saves, at equal accuracy:** 43 % fewer pixels and ~64 % fewer image tokens (207 vs 581), but only
   **~7 % per call** in cost and **5–10 %** in time, because ~540 prompt + tool tokens are paid on every call
   whatever the image. The better the webcam, the bigger the saving; a lighter tool schema would multiply it.
4. **The gaze is what makes the crop usable.** The same crop at the screen centre must fall back to the full
   screen 79 % of the time (cost $0.794 vs $0.496) and is less accurate than the gaze crop (p = 0.009).
5. **Looking elsewhere is safe.** When the user looked elsewhere, Holo said "not here" 94 % of the time and the
   fallback recovered: 93 % success, at the price of two calls (~2 s).
6. Across models (exploration): holo4-27b is the fastest (0.8–1.1 s) and most repeatable (100 % same answer
   twice) but costs more per token; holo3-1-35b-a3b loses the most accuracy with tight crops.

## Honest limits

- Synthetic screens and simulated gaze: a pilot on the method, not a result on real users or real software.
  Next: real Odoo screenshots with annotated targets, and gaze recorded on the vision page instead of simulated.
- G sends native pixels while F is downscaled; Fn (full screen at native resolution) is the sharpness control:
  95–98 %, at 1.4× F's cost.
- Latency includes network and rate-limit waits; they hit both modes alike, but run it on a quiet connection.
