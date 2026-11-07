// node --test heatmap/
import { test } from "node:test";
import assert from "node:assert/strict";
import { computeHeatmap, estimateGaze, distToRect, followGaze, updateDwell, DEFAULTS } from "./gaze-heatmap.js";

const button = (id, x, y) => ({ id, label: id, rect: { x, y, width: 90, height: 40 } });

test("distToRect is 0 inside and euclidean outside", () => {
  const r = { x: 0, y: 0, width: 10, height: 10 };
  assert.equal(distToRect(5, 5, r), 0);
  assert.equal(distToRect(13, 14, r), 5);
});

test("estimateGaze weights recent samples and drops old ones", () => {
  const now = 1000;
  const g = estimateGaze([{ x: 0, y: 0, emittedAt: 0 }, { x: 100, y: 100, emittedAt: 990 }], now);
  assert.equal(g.n, 1);
  assert.equal(g.x, 100);
  assert.equal(estimateGaze([], now), null);
});

test("without targets the cloud is a gaussian: the central circle is the most probable", () => {
  const s = computeHeatmap({ x: 500, y: 500 }, 50, []);
  const n = 1 + 3 * DEFAULTS.rings * (DEFAULTS.rings + 1); // hexagonal numbers: 1, 7, 19...
  assert.equal(s.circles.length, n);
  assert.ok(Math.abs(s.circles.reduce((a, c) => a + c.p, 0) - 1) < 1e-9);
  const max = s.circles.reduce((a, c) => (c.p > a.p ? c : a));
  assert.equal(max.x, 500);
  assert.equal(s.best, null);
});

test("a button next to the gaze raises the circles over it and becomes the best target", () => {
  const near = button("save", 560, 480);   // to the right of the gaze point
  const far = button("delete", 1400, 900);
  const s = computeHeatmap({ x: 500, y: 500 }, 50, [near, far]);
  const max = s.circles.reduce((a, c) => (c.p > a.p ? c : a));
  assert.ok(max.x > 500, "most probable circle shifted towards the button");
  assert.equal(s.best.id, "save");
  assert.ok(s.targets.find((t) => t.id === "save").p > 10 * s.targets.find((t) => t.id === "delete").p);
});

test("contextWeight 0 ignores the page (gaze only)", () => {
  const s = computeHeatmap({ x: 500, y: 500 }, 50, [button("save", 560, 480)], { ...DEFAULTS, contextWeight: 0 });
  const max = s.circles.reduce((a, c) => (c.p > a.p ? c : a));
  assert.equal(max.x, 500);
});

test("the ROI contains the gaze point and the likely target", () => {
  const s = computeHeatmap({ x: 500, y: 500 }, 50, [button("save", 560, 480)]);
  const r = s.roi;
  assert.ok(r.x <= 500 && r.x + r.width >= 600 && r.y <= 480 && r.y + r.height >= 520);
});

// simulate a still mouse with webcam-like noise (σ 28 px at 30 Hz) rendered at 60 fps for 10 s
function simulate(opts, jumpAt = null) {
  let seed = 42;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const gauss = () => Math.sqrt(-2 * Math.log(1 - rnd())) * Math.cos(2 * Math.PI * rnd());
  const samples = [];
  let m = null;
  const xs = [];
  for (let f = 0; f < 600; f++) {
    const now = f * 16.7;
    const target = jumpAt !== null && f >= jumpAt ? 800 : 500;
    if (f % 2 === 0) samples.push({ x: target + gauss() * 28, y: 500 + gauss() * 28, emittedAt: now });
    const g = estimateGaze(samples, now, opts);
    m = followGaze(m, g, Math.max(opts.sigmaMin, g.dispersion), opts);
    xs.push(m.x);
  }
  return xs;
}

test("still gaze with tracker noise: the cloud stays put (fixation)", () => {
  const xs = simulate(DEFAULTS).slice(120); // after settling
  const range = Math.max(...xs) - Math.min(...xs);
  const naive = simulate({ ...DEFAULTS, fixationFollow: 0.18 }).slice(120);
  const naiveRange = Math.max(...naive) - Math.min(...naive);
  assert.ok(range < 8, `cloud wanders ${range.toFixed(1)} px`);
  assert.ok(range < naiveRange / 2, `fixation filter ${range.toFixed(1)} px vs fixed-speed ${naiveRange.toFixed(1)} px`);
});

test("a real jump (saccade) is followed quickly", () => {
  const xs = simulate(DEFAULTS, 300);
  const after = xs[300 + 30]; // 0.5 s after the jump
  assert.ok(after > 760, `centre only reached ${after.toFixed(0)} px`);
});

test("honeycomb: circles touch their neighbours but never overlap", () => {
  const { circles } = computeHeatmap({ x: 500, y: 500 }, 96, []);
  for (let i = 0; i < circles.length; i++)
    for (let j = i + 1; j < circles.length; j++) {
      const d = Math.hypot(circles[i].x - circles[j].x, circles[i].y - circles[j].y);
      assert.ok(d > circles[i].r + circles[j].r, `circles ${i} and ${j} overlap`);
    }
  // every circle has at least 2 neighbours at the lattice distance (they are packed, not scattered)
  const lattice = 2 * circles[0].r * DEFAULTS.gap;
  for (const c of circles) {
    const near = circles.filter((o) => o !== c && Math.abs(Math.hypot(o.x - c.x, o.y - c.y) - lattice) < 0.5).length;
    assert.ok(near >= 2, "circle without packed neighbours");
  }
});

test("screen edges: off-screen cells are dropped and the probability renormalised", () => {
  const bounds = { x: 0, y: 0, width: 1000, height: 800 };
  const full = computeHeatmap({ x: 500, y: 400 }, 96, [], { ...DEFAULTS, bounds });
  const edge = computeHeatmap({ x: 30, y: 30 }, 96, [], { ...DEFAULTS, bounds });
  assert.ok(edge.circles.length < full.circles.length);
  assert.ok(edge.circles.every((c) => c.central || (c.x >= 0 && c.y >= 0)));
  assert.ok(Math.abs(edge.circles.reduce((a, c) => a + c.p, 0) - 1) < 1e-9);
});

test("dwell fills while a target is looked at, drains faster when the gaze leaves", () => {
  let d = new Map();
  let r;
  for (let i = 0; i < 30; i++) r = updateDwell(d, [{ id: "save", p: 0.6 }, { id: "x", p: 0.01 }], 16, DEFAULTS), (d = r.dwell);
  const filled = r.intent.get("save");
  assert.ok(filled > 0.5 && filled <= 1);
  assert.equal(r.intent.get("x"), 0);
  for (let i = 0; i < 6; i++) r = updateDwell(d, [{ id: "save", p: 0.01 }], 16, DEFAULTS), (d = r.dwell);
  assert.ok(r.intent.get("save") < filled - 0.2, "drains faster than it fills");
});

test("dwell boost: the same gaze gives more weight to a target with intent", () => {
  const base = computeHeatmap({ x: 500, y: 500 }, 96, [button("save", 600, 480)]);
  const boosted = computeHeatmap({ x: 500, y: 500 }, 96, [{ ...button("save", 600, 480), weight: 1 + DEFAULTS.dwellBoost }]);
  assert.ok(boosted.targets[0].p > base.targets[0].p);
});
