// Gaze heatmap: turns a noisy gaze (or mouse) signal plus the clickable targets on screen into a
// cloud of circles whose opacity is the probability that the user is about to act there.
//
// Input contract (same as Edouard's tracker, app/src/lib/types.ts):
//   GazeSample = { x: number, y: number, emittedAt: number }   // viewport px, emittedAt in ms
//   push(null) when tracking is lost; setUncertainty(calibrationErrorPx) after calibration.
// Targets: scanned from the DOM (buttons, links, inputs...) or given explicitly with setTargets()
//   when they come from elsewhere (accessibility tree, Holo element localization, screenshots).
// Output (HeatmapState): center, sigma, circles [{x,y,r,p}], targets [{id,rect,p}], best, roi (Rect).
//
// No dependency, no DOM needed for the math: computeHeatmap() is a pure function.

/** @typedef {{x:number,y:number,emittedAt:number}} GazeSample */
/** @typedef {{x:number,y:number,width:number,height:number}} Rect */
/** @typedef {{id:string,rect:Rect,label?:string,weight?:number}} Target */
/** @typedef {{x:number,y:number,r:number,gaze:number,context:number,p:number}} Circle */

export const DEFAULTS = {
  windowMs: 700,          // samples older than this are ignored
  halfLifeMs: 260,        // recency weighting inside the window
  sigmaMin: 96,           // px, floor of the gaze uncertainty (cloud size when the gaze is still)
  sigmaMax: 320,          // px
  rings: 2,               // honeycomb: a central circle + 2 hexagonal rings (6 + 12 circles)
  circleScale: 0.47,      // circle radius = sigma * circleScale
  gap: 1.03,              // centre distance = 2 * radius * gap: neighbours touch without overlapping
  follow: 0.18,           // per-frame follow speed of the cloud centre during a saccade (big move)
  fixationFollow: 0.012,  // ... and during a fixation (jitter inside the dead zone): almost frozen
  deadZonePx: 26,         // movements smaller than this are treated as fixation noise (tracker jitter)
  rampPx: 40,             // over the next rampPx the follow speed rises to `follow`
  saccadeMs: 130,         // if the samples of the last saccadeMs ...
  saccadePx: 90,          // ... sit more than saccadePx away from the window average, the eyes jumped:
                          //     forget the older samples
  followSigma: 0.02,      // per-frame smoothing of its size
  contextWeight: 4,       // how much a nearby clickable target boosts a circle (0 = gaze only)
  contextFloor: 0.25,     // weight of a circle far from any target (relative)
  roiMass: 0.8,           // the ROI covers the circles holding this share of the probability
  bounds: null,           // {x,y,width,height}: cells whose centre falls outside are dropped (screen edges)
  // dwell: looking at a target for a while is a stronger sign of intent than glancing at it
  dwellMinP: 0.25,        // a target accumulates dwell while its probability is above this
  dwellFullMs: 900,       // dwell needed for full intent
  dwellDecay: 2.5,        // dwell drains this many times faster than it fills
  dwellBoost: 1.5,        // full intent multiplies the target weight by (1 + dwellBoost)
  shape: "hex",           // "hex" (honeycomb, cells tile with no holes) or "circle"
  hexRound: 0.22,         // corner rounding of the hexagons, as a share of their radius
};

export const TARGET_SELECTOR =
  'button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=menuitem], [role=tab], [data-gaze-target]';

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

/** Distance from a point to a rectangle (0 inside). */
export function distToRect(x, y, r) {
  const dx = Math.max(r.x - x, 0, x - (r.x + r.width));
  const dy = Math.max(r.y - y, 0, y - (r.y + r.height));
  return Math.hypot(dx, dy);
}

/** Recency-weighted center and spread of the recent samples. */
export function estimateGaze(samples, now, opts = DEFAULTS) {
  let recent = samples.filter((s) => s && now - s.emittedAt <= opts.windowMs);
  if (!recent.length) return null;
  // saccade: the latest samples are far from the window average -> keep only them
  const last = recent.filter((s) => now - s.emittedAt <= opts.saccadeMs);
  if (last.length >= 2 && last.length < recent.length) {
    const mean = (a, k) => a.reduce((t, s) => t + s[k], 0) / a.length;
    if (Math.hypot(mean(last, "x") - mean(recent, "x"), mean(last, "y") - mean(recent, "y")) > opts.saccadePx) recent = last;
  }
  let W = 0, x = 0, y = 0;
  const ws = recent.map((s) => Math.pow(0.5, (now - s.emittedAt) / opts.halfLifeMs));
  recent.forEach((s, i) => { W += ws[i]; x += ws[i] * s.x; y += ws[i] * s.y; });
  x /= W; y /= W;
  let v = 0;
  recent.forEach((s, i) => { v += ws[i] * ((s.x - x) ** 2 + (s.y - y) ** 2); });
  const dispersion = Math.sqrt(v / W);
  return { x, y, dispersion, n: recent.length };
}

/**
 * Pure computation of the heatmap.
 * @param {{x:number,y:number}} center  estimated gaze point
 * @param {number} sigma                gaze uncertainty in px
 * @param {Target[]} targets
 */
export function computeHeatmap(center, sigma, targets, opts = DEFAULTS) {
  const r = sigma * opts.circleScale;
  /** @type {Circle[]} */
  const circles = [];
  // honeycomb: hexagonal lattice, every neighbour exactly 2 * r * gap apart
  const d = 2 * r * opts.gap;
  const dirs = [0, 1, 2, 3, 4, 5].map((i) => [Math.cos((i * Math.PI) / 3 + Math.PI / 2), Math.sin((i * Math.PI) / 3 + Math.PI / 2)]);
  const cells = [[0, 0]];
  for (let n = 1; n <= opts.rings; n++) {
    let x = dirs[4][0] * n * d, y = dirs[4][1] * n * d; // start at a corner of ring n
    for (let side = 0; side < 6; side++)
      for (let step = 0; step < n; step++) {
        cells.push([x, y]);
        x += dirs[side][0] * d;
        y += dirs[side][1] * d;
      }
  }
  const b = opts.bounds;
  for (const [ox, oy] of cells) {
    const cx = center.x + ox;
    const cy = center.y + oy;
    const central = ox === 0 && oy === 0;
    // screen edges: a cell whose centre is off screen cannot be looked at; drop it and renormalise below
    if (b && !central && (cx < b.x || cy < b.y || cx > b.x + b.width || cy > b.y + b.height)) continue;
    {
      const k = Math.hypot(ox, oy) / sigma; // distance from the gaze point, in sigmas
      const gaze = Math.exp(-(k * k) / 2); // prior from the gaze alone (gaussian)
      // context: is there something clickable under / right next to this circle?
      let context = 0;
      for (const t of targets) {
        const d = distToRect(cx, cy, t.rect);
        context = Math.max(context, (t.weight ?? 1) * Math.exp(-(d * d) / (2 * r * r)));
      }
      circles.push({ x: cx, y: cy, r, gaze, context, central, p: gaze * (opts.contextFloor + opts.contextWeight * context) });
    }
  }
  const Z = circles.reduce((s, c) => s + c.p, 0) || 1;
  circles.forEach((c) => (c.p /= Z));

  // probability per target = mass of the circles that point at it. Each circle hands out at most its own
  // mass: shared between the targets it touches (by affinity) when several do, the rest goes to "nothing".
  // So the targets' probabilities never sum above 1, even with dwell weights > 1 or overlapping targets.
  const p = targets.map(() => 0);
  for (const c of circles) {
    const aff = targets.map((t) => {
      const d = distToRect(c.x, c.y, t.rect);
      return (t.weight ?? 1) * Math.exp(-(d * d) / (2 * c.r * c.r));
    });
    const total = aff.reduce((sum, a) => sum + a, 0);
    const scale = c.p / Math.max(1, total);
    aff.forEach((a, i) => (p[i] += a * scale));
  }
  const scored = targets.map((t, i) => ({ id: t.id, label: t.label, rect: t.rect, p: p[i] }));
  const pTargets = scored.reduce((s, t) => s + t.p, 0);
  // share of the mass that falls on no target at all (reading, looking around)
  const pNone = clamp(1 - pTargets, 0, 1);
  scored.sort((a, b) => b.p - a.p);
  const best = scored[0] && scored[0].p > pNone * 0.5 ? scored[0] : null;

  // ROI: bounding box of the most probable circles (for cropping what is sent to the model)
  const sorted = [...circles].sort((a, b) => b.p - a.p);
  let mass = 0, x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const c of sorted) {
    x0 = Math.min(x0, c.x - c.r); y0 = Math.min(y0, c.y - c.r);
    x1 = Math.max(x1, c.x + c.r); y1 = Math.max(y1, c.y + c.r);
    mass += c.p;
    if (mass >= opts.roiMass) break;
  }
  const roi = { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
  return { center, sigma, spacing: d, circles, targets: scored, best, pNone, roi };
}

/**
 * One filter step (call once per frame). Fixation vs saccade: jitter inside the dead zone barely moves
 * the cloud, a real jump is followed fast. Returns the new smoothed {x, y, sigma}.
 */
export function followGaze(m, g, sigma, opts = DEFAULTS) {
  if (!m) return { x: g.x, y: g.y, sigma };
  const d = Math.hypot(g.x - m.x, g.y - m.y);
  const t = clamp((d - opts.deadZonePx) / opts.rampPx, 0, 1);
  const k = opts.fixationFollow + (opts.follow - opts.fixationFollow) * t * t * (3 - 2 * t);
  return {
    x: m.x + (g.x - m.x) * k,
    y: m.y + (g.y - m.y) * k,
    sigma: m.sigma + (sigma - m.sigma) * opts.followSigma,
  };
}

/**
 * Dwell bookkeeping (pure). `dwell` maps target id -> ms. A target fills while its probability is above
 * dwellMinP and drains otherwise. Returns {dwell, intent} where intent maps id -> 0..1.
 */
export function updateDwell(dwell, targets, dtMs, opts = DEFAULTS) {
  const next = new Map();
  const intent = new Map();
  for (const t of targets) {
    const prev = dwell.get(t.id) ?? 0;
    const v = clamp(t.p >= opts.dwellMinP ? prev + dtMs : prev - dtMs * opts.dwellDecay, 0, opts.dwellFullMs);
    next.set(t.id, v);
    intent.set(t.id, v / opts.dwellFullMs);
  }
  return { dwell: next, intent };
}

/** Collect clickable elements of a document as targets (viewport coordinates). */
export function scanTargets(root = document, selector = TARGET_SELECTOR) {
  return [...root.querySelectorAll(selector)]
    .filter((el) => !el.disabled && el.getClientRects().length)
    .map((el, i) => {
      const b = el.getBoundingClientRect();
      return {
        id: el.id || el.dataset.gazeId || `t${i}`,
        label: (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40),
        rect: { x: b.x, y: b.y, width: b.width, height: b.height },
        weight: Number(el.dataset.gazeWeight || 1),
        el,
      };
    });
}

/** Live heatmap drawn on a full-viewport canvas. */
export class GazeHeatmap {
  /**
   * @param {{canvas: HTMLCanvasElement, color?: [number,number,number], maxAlpha?: number, options?: object,
   *          onUpdate?: (state: object) => void}} cfg
   */
  constructor({ canvas, color = [227, 36, 43], maxAlpha = 0.16, options = {}, onUpdate } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.color = color;
    this.maxAlpha = maxAlpha;
    this.opts = { ...DEFAULTS, ...options };
    this.onUpdate = onUpdate;
    this.samples = [];
    this.uncertainty = 0;
    this.targets = null; // null = scan the DOM each frame
    this.state = null;
    this.display = new Map(); // smoothed alpha per circle index
    this.dwell = new Map();   // target id -> ms of dwell
    this.intent = new Map();  // target id -> 0..1
    this._last = 0;
    this._raf = 0;
    this._resize = () => this.resize();
    addEventListener("resize", this._resize);
    this.resize();
  }

  /** Feed one gaze sample (or null when tracking is lost). */
  push(sample) {
    if (!sample) { this.samples = []; return; }
    this.samples.push(sample);
    const cut = sample.emittedAt - this.opts.windowMs;
    while (this.samples.length && this.samples[0].emittedAt < cut) this.samples.shift();
  }

  /**
   * Raw point the whole honeycomb is attached to, exactly (no smoothing): the mouse in the test page.
   * Pass null to go back to the smoothed gaze estimate (what the eye tracker uses).
   */
  setPointer(x, y) { this.pointer = x === null || x === undefined ? null : { x, y }; }

  /** Calibration error of the tracker in px (TrackerStatus.calibrationErrorPx). */
  setUncertainty(px) { this.uncertainty = px || 0; }

  /** Use explicit targets instead of scanning the DOM (pass null to go back to scanning). */
  setTargets(targets) { this.targets = targets; }

  resize() {
    const dpr = Math.min(Math.max(2, (devicePixelRatio || 1) * 1.5), 3); // supersampled for smooth edges
    this.canvas.width = Math.round(innerWidth * dpr);
    this.canvas.height = Math.round(innerHeight * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  compute(now = performance.now()) {
    const g = estimateGaze(this.samples, now, this.opts);
    if (!g) { this.smooth = null; this._last = 0; return (this.state = null); }
    const sigma = clamp(Math.max(this.opts.sigmaMin, this.uncertainty, g.dispersion), this.opts.sigmaMin, this.opts.sigmaMax);
    // steady cloud: the centre and size glide towards the estimate instead of jumping with each sample
    const m = (this.smooth = followGaze(this.smooth, g, sigma, this.opts));
    // dwell raises the weight of the targets the user keeps looking at
    const targets = (this.targets ?? scanTargets()).map((t) => ({
      ...t, weight: (t.weight ?? 1) * (1 + this.opts.dwellBoost * (this.intent.get(t.id) ?? 0)),
    }));
    // the honeycomb hangs on the pointer when there is one (exact follow), else on the smoothed gaze
    const center = this.pointer ?? { x: m.x, y: m.y };
    const opts = { ...this.opts, bounds: { x: 0, y: 0, width: innerWidth, height: innerHeight } };
    this.state = computeHeatmap(center, m.sigma, targets, opts);
    const dt = this._last ? Math.min(100, now - this._last) : 16;
    this._last = now;
    ({ dwell: this.dwell, intent: this.intent } = updateDwell(this.dwell, this.state.targets, dt, this.opts));
    this.state.targets.forEach((t) => (t.intent = this.intent.get(t.id) ?? 0));
    this.state.samples = g.n;
    return this.state;
  }

  /** Path of one cell: a circle, or a flat-topped hexagon that tiles the lattice. */
  cellPath(c, spacing) {
    const { ctx } = this;
    ctx.beginPath();
    if (this.opts.shape === "hex") {
      // flat-topped hexagon with softened corners (arcTo through each vertex)
      const R = (spacing / Math.sqrt(3)) * 0.97;
      const v = [0, 1, 2, 3, 4, 5].map((i) => [c.x + R * Math.cos((i * Math.PI) / 3), c.y + R * Math.sin((i * Math.PI) / 3)]);
      const round = R * this.opts.hexRound;
      ctx.moveTo((v[5][0] + v[0][0]) / 2, (v[5][1] + v[0][1]) / 2);
      for (let i = 0; i < 6; i++) ctx.arcTo(v[i][0], v[i][1], v[(i + 1) % 6][0], v[(i + 1) % 6][1], round);
      ctx.closePath();
    } else {
      ctx.arc(c.x, c.y, c.r, 0, Math.PI * 2);
    }
  }

  draw() {
    const { ctx } = this;
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    const s = this.state;
    if (!s) return;
    const pMax = Math.max(...s.circles.map((c) => c.p)) || 1;
    const [R, G, B] = this.color;
    const rgba = (a) => `rgba(${R},${G},${B},${a.toFixed(3)})`;
    const best = s.best;
    const intent = best?.intent ?? 0;

    // halo on the winning target, stronger as the dwell fills
    if (best) {
      const { x, y, width, height } = best.rect;
      const pad = 6, rad = Math.min(height / 2 + pad, 24);
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(x - pad, y - pad, width + pad * 2, height + pad * 2, rad);
      ctx.fillStyle = rgba(0.05 + 0.12 * intent);
      ctx.fill();
      ctx.shadowColor = rgba(0.5);
      ctx.shadowBlur = 10 + 14 * intent;
      ctx.lineWidth = 1.5 + intent;
      ctx.strokeStyle = rgba(0.35 + 0.5 * intent);
      ctx.stroke();
      ctx.restore();
    }

    s.circles.forEach((c, i) => {
      // contrast: cells far from anything interesting fade out, the likely ones stand out
      const goal = this.maxAlpha * Math.pow(c.p / pMax, 1.6);
      const prev = this.display.get(i) ?? goal;
      const a = prev + (goal - prev) * 0.12;
      this.display.set(i, a);
      const onBest = best && distToRect(c.x, c.y, best.rect) < c.r;
      if (a < 0.004 && !onBest) return;
      this.cellPath(c, s.spacing);
      ctx.fillStyle = rgba(a);
      ctx.fill();
      ctx.lineWidth = onBest ? 1.8 : 1.25;
      ctx.strokeStyle = rgba(onBest ? Math.max(0.55, a * 2) : Math.min(0.5, a * 1.8 + 0.02));
      ctx.stroke();
    });
  }

  drawPointer() {
    const s = this.state;
    if (!s) return;
    const c = s.circles.find((x) => x.central);
    const { ctx } = this;
    const [R, G, B] = this.color;
    this.cellPath(c, s.spacing);
    ctx.fillStyle = `rgba(${R},${G},${B},0.10)`;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = `rgba(${R},${G},${B},0.55)`;
    ctx.stroke();
  }

  start() {
    const loop = () => {
      this.compute();
      this.draw();
      this.drawPointer();
      this.onUpdate?.(this.state);
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() {
    cancelAnimationFrame(this._raf);
    removeEventListener("resize", this._resize);
    this.ctx.clearRect(0, 0, innerWidth, innerHeight);
  }
}
