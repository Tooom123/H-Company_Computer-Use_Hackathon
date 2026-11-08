// Matteo's overlay drawing, ported to SVG (agent/src/hcs_agent/overlay.py). Used for the paper badges:
// the same design as the on-screen "⌘H: new request" badge, i.e. a small scrap of white paper (rough-cut
// edges, slight tilt, soft shadow), handwritten red text, and a red pencil dot wrapped in a loose ring.

const NS = "http://www.w3.org/2000/svg";
export const INK = "rgba(219, 43, 31, 0.92)"; // GRAPHITE in overlay.py
const PAPER = "rgba(255, 255, 251, 0.97)";

/** Seeded random, like random.Random(seed) in the overlay: a badge looks the same every time. */
export function rng(seed) {
  let s = seed % 2147483647 || 1;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const uniform = (r, a, b) => a + (b - a) * r();

/** overlay._wobble_path: two displaced passes over the same points. Returns two `d` strings. */
export function wobble(points, r, jitter) {
  return [0, 1].map(() =>
    points
      .map(([x, y], i) => `${i ? "L" : "M"}${(x + uniform(r, -jitter, jitter)).toFixed(1)} ${(y + uniform(r, -jitter, jitter)).toFixed(1)}`)
      .join(" "),
  );
}

/** overlay._circle: 40 points from -0.35 rad round past the start (+0.55), so the loop overshoots. */
export function circlePoints(cx, cy, rx, ry) {
  const pts = [];
  for (let i = 0; i < 40; i++) {
    const a = -0.35 + (i / 39) * (2 * Math.PI + 0.55);
    pts.push([cx + rx * Math.cos(a), cy + ry * Math.sin(a)]);
  }
  return pts;
}

/** overlay._draw_paper: rough-cut edges (±3 px), tilt of ±0.03 rad around the centre. */
export function paperPoints(x, y, w, h, r) {
  const tilt = uniform(r, -0.03, 0.03);
  const cx = x + w / 2;
  const cy = y + h / 2;
  const rot = (px, py) => {
    const dx = px - cx;
    const dy = py - cy;
    return [cx + dx * Math.cos(tilt) - dy * Math.sin(tilt), cy + dx * Math.sin(tilt) + dy * Math.cos(tilt)];
  };
  const pts = [];
  const edges = [
    [[x, y], [x + w, y], 5],
    [[x + w, y], [x + w, y + h], 3],
    [[x + w, y + h], [x, y + h], 5],
    [[x, y + h], [x, y], 3],
  ];
  for (const [[ax, ay], [bx, by], n] of edges) {
    for (let i = 0; i < n; i++) {
      const t = i / n;
      pts.push(rot(ax + (bx - ax) * t + uniform(r, -3, 3), ay + (by - ay) * t + uniform(r, -3, 3)));
    }
  }
  return pts;
}

function node(name, attrs) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

/**
 * Paint the badge background into `svg`, sized `w`×`h` px: paper scrap + (optional) dot and pencil ring
 * centred at (dotX, h/2). `dot`: "on" (filled red), "off" (ring only, faint), "none".
 */
export function paintBadge(svg, w, h, { seed = 11, dot = "on", dotX = 19 } = {}) {
  svg.replaceChildren();
  svg.setAttribute("viewBox", `-6 -6 ${w + 12} ${h + 12}`);
  svg.setAttribute("width", w + 12);
  svg.setAttribute("height", h + 12);
  const r = rng(seed);
  const paper = paperPoints(0, 0, w, h, r);
  svg.append(node("polygon", { points: paper.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "), fill: PAPER, class: "paper" }));
  if (dot === "none") return;
  const cy = h / 2;
  if (dot === "on") svg.append(node("circle", { cx: dotX, cy, r: 5, fill: INK, class: "dot" }));
  const ring = circlePoints(dotX, cy, 8, 7);
  for (const d of wobble(ring, r, 1.8)) {
    svg.append(node("path", { d, fill: "none", stroke: INK, "stroke-width": 1.6, "stroke-linecap": "round", class: dot === "on" ? "ring" : "ring faint" }));
  }
}

/**
 * The autonomy slider, wide, in the overlay's style (overlay.py, _MagnetView): a paper scrap, a red-pencil rail
 * from left to right with three notches, each level written under its notch, the chosen one a filled dot in two
 * scribbled loops (same strokes and sizes as on screen). Returns the x (0..1) of each notch, for the click zones.
 */
export function drawAutonomy(svg, level, labels, { animate = false } = {}) {
  const W = 640;
  const H = 104;
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const r = rng(7);
  const paper = paperPoints(6, 6, W - 12, H - 12, r);
  svg.append(node("polygon", { points: paper.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "), fill: PAPER, class: "paper" }));
  const line = (pts, width, jitter, cls = "") => {
    for (const d of wobble(pts, r, jitter)) {
      svg.append(node("path", { d, fill: "none", stroke: INK, "stroke-width": width, "stroke-linecap": "round", "stroke-linejoin": "round", class: cls, pathLength: 1 }));
    }
  };
  const y = 40; // rail
  const left = 110; // room for the handwritten labels under the end notches
  const right = W - 110;
  line([[left - 40, y], [(left + right) / 2, y + 0.5], [right + 40, y]], 1.6, 1.0);
  const xs = [];
  for (let i = 0; i < 3; i++) {
    const cx = left + ((right - left) * i) / 2;
    xs.push(cx / W);
    line([[cx, y - 6], [cx, y + 6]], 1.4, 0.8);
    const t = node("text", { x: cx, y: y + 42, "text-anchor": "middle", class: `level-label${i === level ? " on" : ""}` });
    t.textContent = labels[i];
    svg.append(t);
    if (i === level) {
      svg.append(node("circle", { cx, cy: y, r: 7, fill: INK }));
      for (let k = 0; k < 2; k++) line(circlePoints(cx, y, 11 - k * 2, 10 - k * 2), 1.6, 1.8, animate ? "draw" : "");
    }
  }
  return xs;
}

/** A loose red-pencil ring around a mark (the teacher's circle), two passes like every overlay stroke. */
export function paintRing(svg, size, seed = 3) {
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  const r = rng(seed);
  const c = size / 2;
  for (const d of wobble(circlePoints(c, c, c - 3, c - 4), r, 1.4)) {
    svg.append(node("path", { d, fill: "none", stroke: INK, "stroke-width": 1.8, "stroke-linecap": "round", pathLength: 1 }));
  }
}
