# Gaze heatmap (Tom → Edouard)

Turns a noisy gaze signal plus the clickable things on screen into a cloud of red circles. Each circle's
opacity is the probability that the user is about to act there. No dependency, plain ES module.

```bash
cd heatmap && python3 -m http.server 5174 --bind 127.0.0.1   # http://127.0.0.1:5174/
node --test                                                  # unit tests on the math
```

The test page is blank, with 3 buttons at random places (`R` to shuffle). The mouse stands in for the eyes,
sampled at 30 Hz like a webcam tracker, with adjustable jitter. The HUD shows the probability per button,
the share "looking at nothing", the ROI, and how many clicks were predicted. `?at=x,y` pins a fake gaze
point, `?seed=n` fixes the layout.

## Interface

Input is the tracker's existing type (`app/src/lib/types.ts` on `edouard/gaze-desktop`):

```ts
type GazeSample = { x: number; y: number; emittedAt: number }   // viewport px, ms
```

```js
import { GazeHeatmap, scanTargets, computeHeatmap } from "./gaze-heatmap.js";

const heat = new GazeHeatmap({ canvas, onUpdate: (state) => { /* state.roi, state.best ... */ } });
heat.start();

tracker → heat.push(sample)            // GazeSample, or null when tracking is lost
status  → heat.setUncertainty(px)      // TrackerStatus.calibrationErrorPx widens the cloud
targets → heat.setTargets([{ id, rect, label?, weight? }])   // from the accessibility tree / Holo
          // or leave unset: clickable DOM elements are scanned each frame (scanTargets)
```

`state` (also returned by the pure `computeHeatmap(center, sigma, targets, opts)`):

| Field | Meaning |
| --- | --- |
| `center`, `sigma` | smoothed gaze point and its uncertainty (px): max of floor, calibration error, sample dispersion |
| `circles[]` | `{x, y, r, gaze, context, p}`: central circle + rings at 0.9σ, 1.8σ and 2.7σ |
| `targets[]` | `{id, label, rect, p}` sorted by probability |
| `best` | most probable target, or `null` when the user is most likely looking at nothing |
| `pNone` | share of probability on no target (reading, looking around) |
| `roi` | `Rect` covering 80 % of the mass: a candidate crop for what is sent to Holo |

## The rule

`p(circle) ∝ gaze(circle) × (floor + contextWeight × context(circle))`

- `gaze`: gaussian prior, 1 at the centre and lower on the outer rings.
- `context`: how close the circle is to a clickable target, `exp(-d² / 2r²)`, where `d` is the distance to
  the target's rectangle (0 inside). `weight` on a target can make it more or less likely.
- `contextWeight = 0` gives a pure gaze cloud.

- Dwell: a target whose probability stays above `dwellMinP` builds up intent (0 → 1 over `dwellFullMs`,
  draining `dwellDecay` times faster). Intent multiplies the target's weight by `1 + dwellBoost × intent`.
  Each `state.targets[i].intent` exposes it; on screen it strengthens the halo of the winning target.
- Screen edges: cells whose centre is off screen are dropped and the probability is renormalised.

Display: a high-contrast curve so unlikely cells fade out, a stronger outline on the cells over the winning
target, a halo on that target, and `shape: "hex" | "circle"`: honeycomb by default (hexagons tile with no holes),
circles with `?shape=circle` or the HUD checkbox in the test page.

All the knobs live in `DEFAULTS`: window, half-life, sigma bounds, rings, context weight, dwell, shape, ROI.
Next, on Edouard's side: per-target `weight` from the task context (the next step of the procedure up,
destructive actions down).
