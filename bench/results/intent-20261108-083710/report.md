# Gaze × controls × intent → crop · `holo4-35b-a3b`

112 tasks with a user-style request, conditions gaze60, gaze120, gaze200, elsewhere. Crop ≥ 768×480, F's prompt + "not here" → full-screen fallback (both calls paid). Success = Holo's centre inside the target box. 95 % Wilson intervals; paired exact McNemar vs F.

## gaze60

| strategy | success [95 % CI] | target in crop | fallback | median time | cost / 1000 | pixels (median) | vs F |
|---|---|---|---|---|---|---|---|
| F · full screen (today) | 84/112 (75%) [66%–82%] | 100% | 0% | 1.27 s | $0.535 | 655,360 | — |
| G · gaze only | 96/112 (86%) [78%–91%] | 100% | 14% | 1.11 s | $0.547 | 368,640 | +14 / −2, p=0.00 |
| GC · gaze × controls | 95/112 (85%) [77%–90%] | 100% | 17% | 1.21 s | $0.570 | 368,640 | +14 / −3, p=0.01 |
| I · intent × controls (no webcam) | 89/112 (79%) [71%–86%] | 89% | 18% | 1.22 s | $0.594 | 496,256 | +6 / −1, p=0.12 |
| GCI · gaze × controls × intent | 94/112 (84%) [76%–90%] | 100% | 14% | 1.13 s | $0.556 | 368,640 | +12 / −2, p=0.01 |
| GCIa · GCI, "not here" only when gaze and intent disagree | 92/112 (82%) [74%–88%] | 100% | 12% | 1.21 s | $0.531 | 368,640 | +12 / −4, p=0.08 |

- paraphrased requests: I 48/67, target in crop 87% · GCI 54/67, target in crop 100%
- requests quoting the label: I 41/45, target in crop 93% · GCI 40/45, target in crop 100%

## gaze120

| strategy | success [95 % CI] | target in crop | fallback | median time | cost / 1000 | pixels (median) | vs F |
|---|---|---|---|---|---|---|---|
| F · full screen (today) | 84/112 (75%) [66%–82%] | 100% | 0% | 1.27 s | $0.535 | 655,360 | — |
| G · gaze only | 95/112 (85%) [77%–90%] | 98% | 14% | 1.04 s | $0.547 | 368,640 | +12 / −1, p=0.00 |
| GC · gaze × controls | 95/112 (85%) [77%–90%] | 100% | 18% | 1.23 s | $0.574 | 368,640 | +11 / −0, p=0.00 |
| I · intent × controls (no webcam) | 89/112 (79%) [71%–86%] | 89% | 18% | 1.22 s | $0.594 | 496,256 | +6 / −1, p=0.12 |
| GCI · gaze × controls × intent | 92/112 (82%) [74%–88%] | 100% | 14% | 1.14 s | $0.552 | 368,640 | +9 / −1, p=0.02 |
| GCIa · GCI, "not here" only when gaze and intent disagree | 90/112 (80%) [72%–87%] | 100% | 12% | 1.23 s | $0.528 | 368,640 | +9 / −3, p=0.15 |

- paraphrased requests: I 48/67, target in crop 87% · GCI 52/67, target in crop 100%
- requests quoting the label: I 41/45, target in crop 93% · GCI 40/45, target in crop 100%

## gaze200

| strategy | success [95 % CI] | target in crop | fallback | median time | cost / 1000 | pixels (median) | vs F |
|---|---|---|---|---|---|---|---|
| F · full screen (today) | 84/112 (75%) [66%–82%] | 100% | 0% | 1.27 s | $0.535 | 655,360 | — |
| G · gaze only | 92/112 (82%) [74%–88%] | 95% | 20% | 1.23 s | $0.601 | 460,800 | +11 / −3, p=0.06 |
| GC · gaze × controls | 89/112 (79%) [71%–86%] | 100% | 15% | 1.23 s | $0.569 | 395,136 | +8 / −3, p=0.23 |
| I · intent × controls (no webcam) | 89/112 (79%) [71%–86%] | 89% | 18% | 1.22 s | $0.594 | 496,256 | +6 / −1, p=0.12 |
| GCI · gaze × controls × intent | 92/112 (82%) [74%–88%] | 100% | 15% | 1.23 s | $0.566 | 386,690 | +11 / −3, p=0.06 |
| GCIa · GCI, "not here" only when gaze and intent disagree | 92/112 (82%) [74%–88%] | 100% | 11% | 1.23 s | $0.532 | 381,888 | +12 / −4, p=0.08 |

- paraphrased requests: I 48/67, target in crop 87% · GCI 52/67, target in crop 100%
- requests quoting the label: I 41/45, target in crop 93% · GCI 40/45, target in crop 100%

## elsewhere

| strategy | success [95 % CI] | target in crop | fallback | median time | cost / 1000 | pixels (median) | vs F |
|---|---|---|---|---|---|---|---|
| F · full screen (today) | 84/112 (75%) [66%–82%] | 100% | 0% | 1.27 s | $0.535 | 655,360 | — |
| G · gaze only | 82/112 (73%) [64%–81%] | 12% | 87% | 2.20 s | $0.892 | 1,024,000 | +0 / −2, p=0.50 |
| GC · gaze × controls | 86/112 (77%) [68%–84%] | 44% | 58% | 2.08 s | $0.792 | 1,024,000 | +5 / −3, p=0.73 |
| I · intent × controls (no webcam) | 89/112 (79%) [71%–86%] | 89% | 18% | 1.22 s | $0.594 | 496,256 | +6 / −1, p=0.12 |
| GCI · gaze × controls × intent | 88/112 (79%) [70%–85%] | 72% | 39% | 1.76 s | $0.720 | 757,760 | +6 / −2, p=0.29 |
| GCIa · GCI, "not here" only when gaze and intent disagree | 86/112 (77%) [68%–84%] | 72% | 38% | 1.72 s | $0.711 | 742,912 | +6 / −4, p=0.75 |

- paraphrased requests: I 48/67, target in crop 87% · GCI 46/67, target in crop 64%
- requests quoting the label: I 41/45, target in crop 93% · GCI 42/45, target in crop 84%

## Global · all conditions, equal weight

| strategy | success | mean time | cost / 1000 | fallback |
|---|---|---|---|---|
| F · full screen (today) | 75.0% | 1.32 s | $0.535 | 0% |
| G · gaze only | 81.5% | 1.62 s | $0.647 | 34% |
| GC · gaze × controls | 81.5% | 1.62 s | $0.626 | 27% |
| I · intent × controls (no webcam) | 79.5% | 1.46 s | $0.594 | 18% |
| GCI · gaze × controls × intent | 81.7% | 1.57 s | $0.599 | 21% |
| GCIa · GCI, "not here" only when gaze and intent disagree | 80.4% | 1.49 s | $0.576 | 18% |

## Global · realistic: fair webcam 90 %, looking elsewhere 10 %

| strategy | success | mean time | cost / 1000 | fallback |
|---|---|---|---|---|
| F · full screen (today) | 75.0% | 1.32 s | $0.535 | 0% |
| G · gaze only | 83.7% | 1.46 s | $0.581 | 22% |
| GC · gaze × controls | 84.0% | 1.53 s | $0.596 | 22% |
| I · intent × controls (no webcam) | 79.5% | 1.46 s | $0.594 | 18% |
| GCI · gaze × controls × intent | 81.8% | 1.46 s | $0.569 | 17% |
| GCIa · GCI, "not here" only when gaze and intent disagree | 80.0% | 1.42 s | $0.547 | 14% |

## Global · distracted: fair webcam 70 %, looking elsewhere 30 %

| strategy | success | mean time | cost / 1000 | fallback |
|---|---|---|---|---|
| F · full screen (today) | 75.0% | 1.32 s | $0.535 | 0% |
| G · gaze only | 81.3% | 1.62 s | $0.650 | 36% |
| GC · gaze × controls | 82.4% | 1.65 s | $0.639 | 30% |
| I · intent × controls (no webcam) | 79.5% | 1.46 s | $0.594 | 18% |
| GCI · gaze × controls × intent | 81.1% | 1.55 s | $0.603 | 22% |
| GCIa · GCI, "not here" only when gaze and intent disagree | 79.3% | 1.51 s | $0.583 | 19% |

