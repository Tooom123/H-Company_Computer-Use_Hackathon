# Gaze × controls × intent → crop · `holo4-35b-a3b`

30 tasks with a user-style request, conditions gaze120, elsewhere. Crop ≥ 768×480, F's prompt + "not here" → full-screen fallback (both calls paid). Success = Holo's centre inside the target box. 95 % Wilson intervals; paired exact McNemar vs F.

## gaze120

| strategy | success [95 % CI] | target in crop | fallback | median time | cost / 1000 | pixels (median) | vs F |
|---|---|---|---|---|---|---|---|
| F · full screen (today) | 23/30 (77%) [59%–88%] | 100% | 0% | 1.31 s | $0.536 | 655,360 | — |
| G · gaze only | 26/30 (87%) [70%–95%] | 100% | 23% | 1.23 s | $0.593 | 368,640 | +3 / −0, p=0.25 |
| GC · gaze × controls | 25/30 (83%) [66%–93%] | 100% | 30% | 1.25 s | $0.641 | 394,368 | +2 / −0, p=0.50 |
| I · intent × controls (no webcam) | 25/30 (83%) [66%–93%] | 93% | 20% | 1.24 s | $0.612 | 559,104 | +3 / −1, p=0.62 |
| GCI · gaze × controls × intent | 25/30 (83%) [66%–93%] | 100% | 17% | 1.23 s | $0.566 | 368,640 | +3 / −1, p=0.62 |

- paraphrased requests: I 14/17, target in crop 94% · GCI 14/17, target in crop 100%
- requests quoting the label: I 11/13, target in crop 92% · GCI 11/13, target in crop 100%

## elsewhere

| strategy | success [95 % CI] | target in crop | fallback | median time | cost / 1000 | pixels (median) | vs F |
|---|---|---|---|---|---|---|---|
| F · full screen (today) | 23/30 (77%) [59%–88%] | 100% | 0% | 1.31 s | $0.536 | 655,360 | — |
| G · gaze only | 22/30 (73%) [56%–86%] | 20% | 80% | 2.16 s | $0.854 | 1,024,000 | +0 / −1, p=1.00 |
| GC · gaze × controls | 23/30 (77%) [59%–88%] | 47% | 67% | 2.24 s | $0.845 | 1,024,000 | +0 / −0, p=1.00 |
| I · intent × controls (no webcam) | 25/30 (83%) [66%–93%] | 93% | 20% | 1.24 s | $0.612 | 559,104 | +3 / −1, p=0.62 |
| GCI · gaze × controls × intent | 23/30 (77%) [59%–88%] | 83% | 40% | 1.60 s | $0.723 | 776,192 | +0 / −0, p=1.00 |

- paraphrased requests: I 14/17, target in crop 94% · GCI 11/17, target in crop 76%
- requests quoting the label: I 11/13, target in crop 92% · GCI 12/13, target in crop 92%

