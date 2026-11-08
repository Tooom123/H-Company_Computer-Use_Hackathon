# Gaze × controls × intent → crop · `holo4-35b-a3b`

112 tasks with a user-style request, conditions gaze120, elsewhere. Crop ≥ 768×480, F's prompt + "not here" → full-screen fallback (both calls paid). Success = Holo's centre inside the target box. 95 % Wilson intervals; paired exact McNemar vs F.

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

