# Gaze-assisted grounding benchmark

Run 2026-11-08 04:05 UTC · 16 screens (13 real websites, 3 synthetic Odoo-like) · 112 tasks · 784 gaze trials · 2014 calls.

**Question.** The agent sends Holo the whole screen to find a control. If a webcam tells us roughly where the user looks, can we send only that part, pay less per screenshot, and still find it — falling back to the full screen when the gaze was elsewhere?

- **F** full screen downscaled to 1024 px (what the agent sends today) · **Fn** full screen at native 1440 px (sharpness control) · **G** crop around the gaze (heatmap ROI + 40 px, ≥ 512×320, native pixels), with fallback to F when Holo says the control is not in the crop (both calls paid).
- Success = the centre Holo returns, mapped to screen pixels, lies inside the target's box (± 2 px). 95 % intervals: Wilson (rates), bootstrap (medians, means). Paired test vs F: exact McNemar.
- Gaze is simulated around the target with a median error of 60, 120, 200 px (good / fair / poor webcam), plus "looking elsewhere" trials (≥ 300 px away). Latency = one HTTPS request from Paris to the API (US datacenter), rate-limit waits excluded.

## `holo4-35b-a3b`

| strategy | success [95 % CI] | median time [95 % CI] | prompt tokens (mean) | cost / 1000 locates | pixels (median) | paired vs F |
|---|---|---|---|---|---|---|
| F · full 1024 (today) | 106/112 (95%) [89%–98%] | 1.25 s [1.20–1.31] | 1,119 | $0.533 | 655,360 | — |
| Fn · full native | 108/112 (96%) [91%–99%] | 1.52 s [1.45–1.54] | 1,739 | $0.718 | 1,296,000 | +4 / −2, p=0.69 |
| G · gaze ~60 px | 191/224 (85%) [80%–89%] | 1.02 s [1.01–1.02] | 803 | $0.442 | 182,272 | +7 / −28, p=0.00 |
| G · gaze ~120 px | 187/223 (84%) [78%–88%] | 1.02 s [1.02–1.03] | 843 | $0.455 | 217,600 | +5 / −29, p=0.00 |
| G · gaze ~200 px | 210/223 (94%) [90%–97%] | 1.22 s [1.19–1.23] | 1,056 | $0.522 | 395,620 | +6 / −7, p=1.00 |
| G · looking elsewhere | 103/111 (93%) [86%–96%] | 2.07 s [2.00–2.13] | 1,873 | $0.868 | 247,296 | +0 / −2, p=0.50 |
| G · mix: fair webcam + 10 % elsewhere | 209/248 (84%) [79%–88%] | 1.03 s [1.02–1.10] | 936 | $0.493 | 217,600 | +5 / −30, p=0.00 |
| C · centre crop, no gaze (size of G ~120 px) | 205/224 (92%) [87%–95%] | 2.01 s [1.93–2.07] | 1,692 | $0.794 | 217,600 | +0 / −7, p=0.02 |
| G variant `min768plain` · gaze ~60 px | 216/223 (97%) [94%–98%] | 1.13 s [1.04–1.17] | 957 | $0.490 | 368,640 | +9 / −4, p=0.27 · vs G: +28 / −2, p=0.00 |
| G variant `min768plain` · gaze ~120 px | 211/224 (94%) [90%–97%] | 1.19 s [1.12–1.23] | 974 | $0.496 | 368,640 | +6 / −7, p=1.00 · vs G: +25 / −2, p=0.00 |
| G variant `min768plain` · gaze ~200 px | 217/224 (97%) [94%–98%] | 1.23 s [1.22–1.24] | 1,088 | $0.530 | 476,880 | +8 / −3, p=0.23 · vs G: +8 / −2, p=0.11 |
| G variant `min768plain` · looking elsewhere | 103/112 (92%) [85%–96%] | 2.13 s [2.02–2.22] | 1,839 | $0.861 | 370,944 | +2 / −5, p=0.45 · vs G: +3 / −4, p=1.00 |

Gaze vs centre crop of the same size, same trials: gaze right and centre wrong 11, the reverse 28 (n=223, McNemar p=0.00948). Centre crop fell back 177/224 (79%).

| G condition | target inside the crop | fell back to full screen | said "not here" although inside | answered in the crop but wrong |
|---|---|---|---|---|
| G · gaze ~60 px | 221/224 (99%) | 6/224 (3%) | 6/221 (3%) | 31/224 (14%) |
| G · gaze ~120 px | 213/223 (96%) | 7/223 (3%) | 6/213 (3%) | 34/223 (15%) |
| G · gaze ~200 px | 213/223 (96%) | 11/223 (5%) | 9/213 (4%) | 11/223 (5%) |
| G · looking elsewhere | 4/111 (4%) | 104/111 (94%) | 0/4 (0%) | 3/111 (3%) |

Fixed text + tool tokens: 538 (full-screen prompt), 648 (crop prompt, with the not_found tool). Image tokens only: F ≈ 581, G crop ≈ 207 (36% of F).

| by site | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| synthetic | 17 | 16/17 (94%) | 33/34 (97%) | 4/34 (12%) | 85% |
| web | 95 | 90/95 (95%) | 154/189 (81%) | 3/189 (2%) | 74% |

| by target | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| icon | 8 | 7/8 (88%) | 10/16 (62%) | 0/16 (0%) | 71% |
| text | 104 | 99/104 (95%) | 177/207 (86%) | 7/207 (3%) | 76% |

| by target size | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| large | 15 | 15/15 (100%) | 27/30 (90%) | 0/30 (0%) | 71% |
| medium | 46 | 45/46 (98%) | 87/92 (95%) | 0/92 (0%) | 71% |
| small | 51 | 46/51 (90%) | 73/101 (72%) | 7/101 (7%) | 80% |

| by screen | F success | G (~120 px) success | G fallback |
|---|---|---|---|
| crm | 5/6 (83%) | 11/12 (92%) | 0/12 (0%) |
| invoice | 6/6 (100%) | 12/12 (100%) | 4/12 (33%) |
| settings | 5/5 (100%) | 10/10 (100%) | 0/10 (0%) |
| wikipedia | 8/8 (100%) | 14/16 (88%) | 0/16 (0%) |
| wikipedia-fr | 8/8 (100%) | 12/16 (75%) | 0/16 (0%) |
| hackernews | 6/8 (75%) | 3/16 (19%) | 0/16 (0%) |
| python | 8/8 (100%) | 16/16 (100%) | 0/16 (0%) |
| mdn | 7/7 (100%) | 14/14 (100%) | 0/14 (0%) |
| govuk | 5/5 (100%) | 9/10 (90%) | 0/10 (0%) |
| odoo | 8/8 (100%) | 16/16 (100%) | 0/16 (0%) |
| hcompany | 7/7 (100%) | 13/14 (93%) | 0/14 (0%) |
| github | 7/8 (88%) | 11/15 (73%) | 0/15 (0%) |
| npm | 8/8 (100%) | 15/16 (94%) | 0/16 (0%) |
| stackoverflow | 7/8 (88%) | 13/16 (81%) | 0/16 (0%) |
| lemonde | 3/4 (75%) | 5/8 (62%) | 2/8 (25%) |
| craigslist | 8/8 (100%) | 13/16 (81%) | 1/16 (6%) |

## Limits

- Simulated gaze (gaussian around the target, error from webcam qualities measured on the vision page), not recorded gaze; real websites captured once, logged out, cookie banners included; synthetic Odoo-like screens with hand-written tasks. A pilot on the method, not a result on users (protocol, experiment A).
- Real-site tasks are drawn automatically among controls with a unique label; icon targets are named by their aria-label. Instructions name the control, they are not user goals.
- The fallback reuses the task's F answer (same image, same request, temperature 0) and adds its cost and time.
- Prices from the API's /models at run time: {"holo4-35b-a3b": {"prompt": 3e-07, "completion": 2e-06}} (USD per token).
