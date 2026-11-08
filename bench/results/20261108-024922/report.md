# Gaze-assisted grounding benchmark

Run 2026-11-08 01:49 UTC · 15 screens (12 real websites, 3 synthetic Odoo-like) · 104 tasks · 728 gaze trials · 5206 calls.

**Question.** The agent sends Holo the whole screen to find a control. If a webcam tells us roughly where the user looks, can we send only that part, pay less per screenshot, and still find it — falling back to the full screen when the gaze was elsewhere?

- **F** full screen downscaled to 1024 px (what the agent sends today) · **Fn** full screen at native 1440 px (sharpness control) · **G** crop around the gaze (heatmap ROI + 40 px, ≥ 512×320, native pixels), with fallback to F when Holo says the control is not in the crop (both calls paid).
- Success = the centre Holo returns, mapped to screen pixels, lies inside the target's box (± 2 px). 95 % intervals: Wilson (rates), bootstrap (medians, means). Paired test vs F: exact McNemar.
- Gaze is simulated around the target with a median error of 60, 120, 200 px (good / fair / poor webcam), plus "looking elsewhere" trials (≥ 300 px away). Latency = one HTTPS request from Paris to the API (US datacenter), rate-limit waits excluded.

## `holo3-1-35b-a3b`

| strategy | success [95 % CI] | median time [95 % CI] | prompt tokens (mean) | cost / 1000 locates | pixels (median) | paired vs F |
|---|---|---|---|---|---|---|
| F · full 1024 (today) | 96/104 (92%) [86%–96%] | 1.31 s [1.24–1.36] | 1,118 | $0.455 | 655,360 | — |
| Fn · full native | 101/104 (97%) [92%–99%] | 1.54 s [1.45–1.63] | 1,738 | $0.610 | 1,296,000 | +6 / −1, p=0.12 |
| G · gaze ~60 px | 162/208 (78%) [72%–83%] | 1.02 s [1.02–1.05] | 850 | $0.397 | 182,272 | +7 / −37, p=0.00 |
| G · gaze ~120 px | 157/208 (75%) [69%–81%] | 1.05 s [1.02–1.13] | 895 | $0.410 | 217,600 | +7 / −42, p=0.00 |
| G · gaze ~200 px | 174/208 (84%) [78%–88%] | 1.25 s [1.23–1.32] | 1,106 | $0.466 | 430,218 | +9 / −27, p=0.00 |
| G · looking elsewhere | 94/104 (90%) [83%–95%] | 2.10 s [2.00–2.18] | 1,880 | $0.738 | 247,296 | +0 / −2, p=0.50 |
| G · mix: fair webcam + 10 % elsewhere | 177/231 (77%) [71%–82%] | 1.12 s [1.04–1.16] | 995 | $0.445 | 217,600 | +7 / −43, p=0.00 |
| C · centre crop, no gaze (size of G ~120 px) | 186/208 (89%) [85%–93%] | 2.13 s [2.04–2.16] | 1,760 | $0.703 | 217,600 | +0 / −6, p=0.03 |

Gaze vs centre crop of the same size, same trials: gaze right and centre wrong 9, the reverse 38 (n=208, McNemar p=2.49e-05). Centre crop fell back 177/208 (85%).

| G condition | target inside the crop | fell back to full screen | said "not here" although inside | answered in the crop but wrong |
|---|---|---|---|---|
| G · gaze ~60 px | 204/208 (98%) | 14/208 (7%) | 13/204 (6%) | 41/208 (20%) |
| G · gaze ~120 px | 199/208 (96%) | 16/208 (8%) | 11/199 (6%) | 47/208 (23%) |
| G · gaze ~200 px | 199/208 (96%) | 19/208 (9%) | 16/199 (8%) | 30/208 (14%) |
| G · looking elsewhere | 2/104 (2%) | 98/104 (94%) | 0/2 (0%) | 4/104 (4%) |

Fixed text + tool tokens: 538 (full-screen prompt), 648 (crop prompt, with the not_found tool). Image tokens only: F ≈ 580, G crop ≈ 209 (36% of F).

| by site | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| synthetic | 17 | 17/17 (100%) | 28/34 (82%) | 5/34 (15%) | 86% |
| web | 87 | 79/87 (91%) | 129/174 (74%) | 11/174 (6%) | 79% |

| by target | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| icon | 5 | 4/5 (80%) | 6/10 (60%) | 3/10 (30%) | 100% |
| text | 99 | 92/99 (93%) | 151/198 (76%) | 13/198 (7%) | 79% |

| by target size | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| large | 15 | 13/15 (87%) | 25/30 (83%) | 2/30 (7%) | 79% |
| medium | 41 | 39/41 (95%) | 73/82 (89%) | 5/82 (6%) | 76% |
| small | 48 | 44/48 (92%) | 59/96 (61%) | 9/96 (9%) | 83% |

| by screen | F success | G (~120 px) success | G fallback |
|---|---|---|---|
| crm | 6/6 (100%) | 12/12 (100%) | 0/12 (0%) |
| invoice | 6/6 (100%) | 12/12 (100%) | 5/12 (42%) |
| settings | 5/5 (100%) | 4/10 (40%) | 0/10 (0%) |
| wikipedia | 8/8 (100%) | 10/16 (62%) | 1/16 (6%) |
| wikipedia-fr | 7/8 (88%) | 11/16 (69%) | 1/16 (6%) |
| hackernews | 6/8 (75%) | 4/16 (25%) | 2/16 (12%) |
| python | 7/8 (88%) | 16/16 (100%) | 0/16 (0%) |
| mdn | 7/7 (100%) | 13/14 (93%) | 1/14 (7%) |
| govuk | 5/5 (100%) | 7/10 (70%) | 0/10 (0%) |
| odoo | 8/8 (100%) | 16/16 (100%) | 0/16 (0%) |
| hcompany | 7/7 (100%) | 12/14 (86%) | 0/14 (0%) |
| github | 8/8 (100%) | 13/16 (81%) | 2/16 (12%) |
| stackoverflow | 6/8 (75%) | 8/16 (50%) | 1/16 (6%) |
| lemonde | 2/4 (50%) | 5/8 (62%) | 3/8 (38%) |
| craigslist | 8/8 (100%) | 14/16 (88%) | 0/16 (0%) |

Repeatability (F asked twice, temperature 0): same answer (± 3 px) in 94/104 (90%); median time 1.25 s on the second ask.

## `holo4-27b`

| strategy | success [95 % CI] | median time [95 % CI] | prompt tokens (mean) | cost / 1000 locates | pixels (median) | paired vs F |
|---|---|---|---|---|---|---|
| F · full 1024 (today) | 99/104 (95%) [89%–98%] | 1.09 s [1.01–1.11] | 1,118 | $0.750 | 655,360 | — |
| Fn · full native | 101/104 (97%) [92%–99%] | 1.22 s [1.15–1.27] | 1,738 | $0.997 | 1,296,000 | +3 / −1, p=0.62 |
| G · gaze ~60 px | 178/208 (86%) [80%–90%] | 0.82 s [0.78–0.82] | 796 | $0.625 | 182,272 | +1 / −21, p=0.00 |
| G · gaze ~120 px | 186/208 (89%) [85%–93%] | 0.82 s [0.81–0.83] | 862 | $0.657 | 217,600 | +2 / −14, p=0.00 |
| G · gaze ~200 px | 199/208 (96%) [92%–98%] | 1.01 s [0.92–1.02] | 1,057 | $0.736 | 430,218 | +3 / −2, p=1.00 |
| G · looking elsewhere | 94/104 (90%) [83%–95%] | 1.80 s [1.71–1.84] | 1,847 | $1.244 | 247,296 | +0 / −5, p=0.06 |
| G · mix: fair webcam + 10 % elsewhere | 204/231 (88%) [84%–92%] | 0.82 s [0.82–0.84] | 947 | $0.708 | 218,112 | +2 / −17, p=0.00 |
| C · centre crop, no gaze (size of G ~120 px) | 193/208 (93%) [88%–96%] | 1.71 s [1.63–1.80] | 1,706 | $1.165 | 217,600 | +0 / −5, p=0.06 |

Gaze vs centre crop of the same size, same trials: gaze right and centre wrong 6, the reverse 13 (n=208, McNemar p=0.167). Centre crop fell back 167/208 (80%).

| G condition | target inside the crop | fell back to full screen | said "not here" although inside | answered in the crop but wrong |
|---|---|---|---|---|
| G · gaze ~60 px | 204/208 (98%) | 4/208 (2%) | 4/204 (2%) | 28/208 (13%) |
| G · gaze ~120 px | 199/208 (96%) | 10/208 (5%) | 9/199 (5%) | 20/208 (10%) |
| G · gaze ~200 px | 199/208 (96%) | 10/208 (5%) | 8/199 (4%) | 7/208 (3%) |
| G · looking elsewhere | 2/104 (2%) | 95/104 (91%) | 0/2 (0%) | 5/104 (5%) |

Fixed text + tool tokens: 538 (full-screen prompt), 648 (crop prompt, with the not_found tool). Image tokens only: F ≈ 580, G crop ≈ 209 (36% of F).

| by site | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| synthetic | 17 | 17/17 (100%) | 33/34 (97%) | 4/34 (12%) | 84% |
| web | 87 | 82/87 (94%) | 153/174 (88%) | 6/174 (3%) | 76% |

| by target | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| icon | 5 | 5/5 (100%) | 10/10 (100%) | 4/10 (40%) | 110% |
| text | 99 | 94/99 (95%) | 176/198 (89%) | 6/198 (3%) | 75% |

| by target size | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| large | 15 | 14/15 (93%) | 29/30 (97%) | 0/30 (0%) | 73% |
| medium | 41 | 41/41 (100%) | 80/82 (98%) | 5/82 (6%) | 76% |
| small | 48 | 44/48 (92%) | 77/96 (80%) | 5/96 (5%) | 79% |

| by screen | F success | G (~120 px) success | G fallback |
|---|---|---|---|
| crm | 6/6 (100%) | 12/12 (100%) | 0/12 (0%) |
| invoice | 6/6 (100%) | 11/12 (92%) | 4/12 (33%) |
| settings | 5/5 (100%) | 10/10 (100%) | 0/10 (0%) |
| wikipedia | 8/8 (100%) | 15/16 (94%) | 0/16 (0%) |
| wikipedia-fr | 8/8 (100%) | 14/16 (88%) | 0/16 (0%) |
| hackernews | 5/8 (62%) | 5/16 (31%) | 0/16 (0%) |
| python | 8/8 (100%) | 16/16 (100%) | 0/16 (0%) |
| mdn | 7/7 (100%) | 13/14 (93%) | 0/14 (0%) |
| govuk | 5/5 (100%) | 9/10 (90%) | 2/10 (20%) |
| odoo | 8/8 (100%) | 16/16 (100%) | 0/16 (0%) |
| hcompany | 7/7 (100%) | 14/14 (100%) | 0/14 (0%) |
| github | 8/8 (100%) | 16/16 (100%) | 2/16 (12%) |
| stackoverflow | 8/8 (100%) | 15/16 (94%) | 0/16 (0%) |
| lemonde | 2/4 (50%) | 6/8 (75%) | 2/8 (25%) |
| craigslist | 8/8 (100%) | 14/16 (88%) | 0/16 (0%) |

Repeatability (F asked twice, temperature 0): same answer (± 3 px) in 104/104 (100%); median time 1.01 s on the second ask.

## `holo4-35b-a3b`

| strategy | success [95 % CI] | median time [95 % CI] | prompt tokens (mean) | cost / 1000 locates | pixels (median) | paired vs F |
|---|---|---|---|---|---|---|
| F · full 1024 (today) | 96/104 (92%) [86%–96%] | 1.21 s [1.19–1.29] | 1,118 | $0.533 | 655,360 | — |
| Fn · full native | 102/104 (98%) [93%–99%] | 1.49 s [1.43–1.55] | 1,738 | $0.718 | 1,296,000 | +7 / −1, p=0.07 |
| G · gaze ~60 px | 175/208 (84%) [79%–88%] | 1.02 s [1.02–1.02] | 812 | $0.446 | 182,272 | +10 / −27, p=0.01 |
| G · gaze ~120 px | 180/208 (87%) [81%–91%] | 1.02 s [1.02–1.02] | 868 | $0.466 | 217,600 | +8 / −20, p=0.04 |
| G · gaze ~200 px | 191/208 (92%) [87%–95%] | 1.17 s [1.08–1.23] | 1,025 | $0.507 | 430,218 | +10 / −11, p=1.00 |
| G · looking elsewhere | 92/104 (88%) [81%–93%] | 2.01 s [1.91–2.10] | 1,869 | $0.876 | 247,296 | +0 / −4, p=0.12 |
| G · mix: fair webcam + 10 % elsewhere | 199/231 (86%) [81%–90%] | 1.02 s [1.02–1.04] | 962 | $0.504 | 218,112 | +8 / −22, p=0.02 |
| C · centre crop, no gaze (size of G ~120 px) | 186/208 (89%) [85%–93%] | 1.96 s [1.86–2.01] | 1,722 | $0.812 | 217,600 | +2 / −8, p=0.11 |
| G variant `plain` · gaze ~60 px | 175/208 (84%) [79%–88%] | 1.02 s [1.02–1.03] | 796 | $0.442 | 182,272 | +10 / −27, p=0.01 · vs G: +2 / −2, p=1.00 |
| G variant `plain` · gaze ~120 px | 179/208 (86%) [81%–90%] | 1.03 s [1.02–1.10] | 852 | $0.463 | 217,600 | +8 / −21, p=0.02 · vs G: +2 / −3, p=1.00 |
| G variant `min768` · gaze ~60 px | 197/208 (95%) [91%–97%] | 1.13 s [1.04–1.20] | 959 | $0.486 | 368,640 | +13 / −8, p=0.38 · vs G: +27 / −5, p=0.00 |
| G variant `min768` · gaze ~120 px | 198/208 (95%) [91%–97%] | 1.19 s [1.12–1.23] | 987 | $0.497 | 368,640 | +13 / −7, p=0.26 · vs G: +21 / −3, p=0.00 |
| G variant `up1024` · gaze ~120 px | 202/208 (97%) [94%–99%] | 1.42 s [1.40–1.50] | 1,499 | $0.657 | 870,400 | +13 / −3, p=0.02 · vs G: +23 / −1, p=0.00 |
| G variant `min768plain` · gaze ~60 px | 202/208 (97%) [94%–99%] | 1.16 s [1.11–1.21] | 954 | $0.489 | 368,640 | +13 / −3, p=0.02 · vs G: +28 / −1, p=0.00 |
| G variant `min768plain` · gaze ~120 px | 201/208 (97%) [93%–98%] | 1.15 s [1.05–1.20] | 971 | $0.493 | 368,640 | +14 / −5, p=0.06 · vs G: +22 / −1, p=0.00 |

Gaze vs centre crop of the same size, same trials: gaze right and centre wrong 11, the reverse 17 (n=208, McNemar p=0.345). Centre crop fell back 170/208 (82%).

| G condition | target inside the crop | fell back to full screen | said "not here" although inside | answered in the crop but wrong |
|---|---|---|---|---|
| G · gaze ~60 px | 204/208 (98%) | 7/208 (3%) | 7/204 (3%) | 31/208 (15%) |
| G · gaze ~120 px | 199/208 (96%) | 11/208 (5%) | 8/199 (4%) | 24/208 (12%) |
| G · gaze ~200 px | 199/208 (96%) | 4/208 (2%) | 2/199 (1%) | 15/208 (7%) |
| G · looking elsewhere | 2/104 (2%) | 97/104 (93%) | 0/2 (0%) | 5/104 (5%) |

Fixed text + tool tokens: 538 (full-screen prompt), 648 (crop prompt, with the not_found tool). Image tokens only: F ≈ 580, G crop ≈ 209 (36% of F).

| by site | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| synthetic | 17 | 16/17 (94%) | 34/34 (100%) | 5/34 (15%) | 86% |
| web | 87 | 80/87 (92%) | 146/174 (84%) | 6/174 (3%) | 76% |

| by target | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| icon | 5 | 3/5 (60%) | 6/10 (60%) | 2/10 (20%) | 90% |
| text | 99 | 93/99 (94%) | 174/198 (88%) | 9/198 (5%) | 77% |

| by target size | n tasks | F success | G (~120 px) success | G fallback | G tokens vs F |
|---|---|---|---|---|---|
| large | 15 | 13/15 (87%) | 28/30 (93%) | 2/30 (7%) | 79% |
| medium | 41 | 40/41 (98%) | 76/82 (93%) | 2/82 (2%) | 73% |
| small | 48 | 43/48 (90%) | 76/96 (79%) | 7/96 (7%) | 81% |

| by screen | F success | G (~120 px) success | G fallback |
|---|---|---|---|
| crm | 5/6 (83%) | 12/12 (100%) | 0/12 (0%) |
| invoice | 6/6 (100%) | 12/12 (100%) | 5/12 (42%) |
| settings | 5/5 (100%) | 10/10 (100%) | 0/10 (0%) |
| wikipedia | 8/8 (100%) | 15/16 (94%) | 0/16 (0%) |
| wikipedia-fr | 8/8 (100%) | 13/16 (81%) | 1/16 (6%) |
| hackernews | 5/8 (62%) | 5/16 (31%) | 0/16 (0%) |
| python | 7/8 (88%) | 16/16 (100%) | 0/16 (0%) |
| mdn | 7/7 (100%) | 14/14 (100%) | 1/14 (7%) |
| govuk | 5/5 (100%) | 10/10 (100%) | 0/10 (0%) |
| odoo | 8/8 (100%) | 16/16 (100%) | 0/16 (0%) |
| hcompany | 7/7 (100%) | 13/14 (93%) | 0/14 (0%) |
| github | 8/8 (100%) | 13/16 (81%) | 0/16 (0%) |
| stackoverflow | 6/8 (75%) | 11/16 (69%) | 2/16 (12%) |
| lemonde | 3/4 (75%) | 6/8 (75%) | 2/8 (25%) |
| craigslist | 8/8 (100%) | 14/16 (88%) | 0/16 (0%) |

Repeatability (F asked twice, temperature 0): same answer (± 3 px) in 104/104 (100%); median time 1.20 s on the second ask.

## Limits

- Simulated gaze (gaussian around the target, error from webcam qualities measured on the vision page), not recorded gaze; real websites captured once, logged out, cookie banners included; synthetic Odoo-like screens with hand-written tasks. A pilot on the method, not a result on users (protocol, experiment A).
- Real-site tasks are drawn automatically among controls with a unique label; icon targets are named by their aria-label. Instructions name the control, they are not user goals.
- The fallback reuses the task's F answer (same image, same request, temperature 0) and adds its cost and time.
- Prices from the API's /models at run time: {"holo3-1-35b-a3b": {"prompt": 2.5e-07, "completion": 1.8e-06}, "holo4-27b": {"prompt": 4e-07, "completion": 3e-06}, "holo4-35b-a3b": {"prompt": 3e-07, "completion": 2e-06}} (USD per token).
