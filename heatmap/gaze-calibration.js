// Calibration and validation for the vision page. Pure functions (no DOM, no camera), tested with node --test.
// The grids are Édouard's (app/src/lib/calibration-targets.ts, profile "standard"): 9 targets to learn,
// 4 different targets to measure the error, so the error is never measured on points the model learnt.

export const CALIBRATION = [0.18, 0.5, 0.82].flatMap((y) => [0.12, 0.5, 0.88].map((x) => ({ x, y })));
export const VALIDATION = [{ x: 0.3, y: 0.32 }, { x: 0.7, y: 0.68 }, { x: 0.7, y: 0.32 }, { x: 0.3, y: 0.68 }];
export const CLICKS_PER_TARGET = 5;

/** Relative targets -> viewport pixels. */
export function toPixels(points, width, height) {
  return points.map((p) => ({ x: Math.round(p.x * width), y: Math.round(p.y * height) }));
}

export function quantile(sorted, q) {
  if (!sorted.length) return null;
  const i = (sorted.length - 1) * q;
  const lo = Math.floor(i);
  const hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

/**
 * Error of the gaze predictions gathered while the user looked at each validation target.
 * `runs`: [{ target: {x,y}, samples: [{x,y}] }]. Each target counts once (its median distance), so a target
 * with more samples does not weigh more. Returns px stats, or null when no target got a sample.
 */
export function validationError(runs) {
  const perTarget = runs
    .filter((r) => r.samples.length)
    .map((r) => {
      const d = r.samples.map((s) => Math.hypot(s.x - r.target.x, s.y - r.target.y)).sort((a, b) => a - b);
      return quantile(d, 0.5);
    })
    .sort((a, b) => a - b);
  if (!perTarget.length) return null;
  return {
    medianPx: Math.round(quantile(perTarget, 0.5)),
    worstPx: Math.round(perTarget.at(-1)),
    targets: perTarget.length,
    missing: runs.length - perTarget.length,
  };
}

/** How the error reads for a person, and how it sizes the honeycomb (setUncertainty). */
export function accuracyLabel(medianPx) {
  if (medianPx === null || medianPx === undefined) return "not measured";
  if (medianPx < 120) return "good";
  if (medianPx < 220) return "fair: big buttons only";
  return "poor: recalibrate (light, distance, head still)";
}

/** Samples per second over a sliding window of timestamps (ms). */
export function rate(timestamps, now, windowMs = 2000) {
  const n = timestamps.filter((t) => now - t <= windowMs).length;
  return Math.round((n * 1000) / windowMs);
}
