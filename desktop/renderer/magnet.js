// The Magnet, drawn the way Matteo's overlay draws it (agent/src/hcs_agent/overlay.py, _MagnetView):
// a scrap of white paper (rough edges, slight tilt, soft shadow), a red-pencil rail with three notches,
// the active one a filled dot wrapped in two scribbled circles, and a handwritten "Magnet: ..." label.
// Every stroke is two overlapping passes with a small jitter (_wobble_path), so it reads as pencil.

const NS = "http://www.w3.org/2000/svg";
const INK = "rgba(219, 43, 31, 0.92)"; // GRAPHITE in overlay.py
const PAPER = "rgba(255, 255, 251, 0.96)";

/** Seeded random, like random.Random(seed) in the overlay: the same Magnet looks the same every time. */
export function rng(seed) {
  let s = seed % 2147483647 || 1;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const uniform = (r, a, b) => a + (b - a) * r();

/** Two displaced passes over the same points (overlay._wobble_path). Returns two `d` strings. */
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

/** overlay._draw_paper: rough-cut edges, tilt of ±0.03 rad around the centre. */
export function paperPoints(x, y, w, h, r) {
  const tilt = uniform(r, -0.03, 0.03) * 0.4; // a wide scrap: less tilt than a small note, or it looks crooked
  const cx = x + w / 2;
  const cy = y + h / 2;
  const rot = (px, py) => {
    const dx = px - cx;
    const dy = py - cy;
    return [cx + dx * Math.cos(tilt) - dy * Math.sin(tilt), cy + dx * Math.sin(tilt) + dy * Math.cos(tilt)];
  };
  const pts = [];
  const edges = [
    [[x, y], [x + w, y], 9],
    [[x + w, y], [x + w, y + h], 3],
    [[x + w, y + h], [x, y + h], 9],
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

function el(name, attrs) {
  const e = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

function stroke(svg, points, r, width, jitter, cls = "") {
  for (const d of wobble(points, r, jitter)) {
    svg.append(el("path", { d, fill: "none", stroke: INK, "stroke-width": width, "stroke-linecap": "round", "stroke-linejoin": "round", class: cls }));
  }
}

/**
 * Draw the Magnet into `host` (an <svg>), `level` 0..2 active (null = unknown, no knob).
 * Returns the x of each notch so the caller can place click targets.
 */
export function drawMagnet(svg, level, labels, { width = 640, height = 132, animate = false } = {}) {
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const r = rng(7);
  const defs = el("defs", {});
  const f = el("filter", { id: "paper-shadow", x: "-5%", y: "-10%", width: "110%", height: "130%" });
  f.append(el("feDropShadow", { dx: 2, dy: 3, stdDeviation: 3, "flood-color": "#000", "flood-opacity": 0.22 }));
  defs.append(f);
  svg.append(defs);

  const paper = paperPoints(8, 8, width - 16, height - 16, r);
  svg.append(el("polygon", { points: paper.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "), fill: PAPER, filter: "url(#paper-shadow)" }));

  const label = el("text", { x: 30, y: 40, class: "magnet-label" });
  label.textContent = `Magnet: ${level === null ? "…" : labels[level]}`;
  svg.append(label);

  const y = 74;
  const left = 104; // room for the handwritten labels under the end notches
  const right = width - 104;
  stroke(svg, [[left, y], [(left + right) / 2, y + 0.6], [right, y]], r, 1.8, 1.0);
  const xs = [0, 1, 2].map((i) => left + ((right - left) * i) / 2);
  xs.forEach((cx, i) => {
    stroke(svg, [[cx, y - 8], [cx, y + 8]], r, 1.6, 0.8);
    const t = el("text", { x: cx, y: y + 36, "text-anchor": "middle", class: `notch-label${i === level ? " on" : ""}` });
    t.textContent = labels[i];
    svg.append(t);
  });
  if (level !== null) {
    const cx = xs[level];
    svg.append(el("circle", { cx, cy: y, r: 7.5, fill: INK }));
    // Two loose loops around the knob (overlay: _circle(11 - k*2)), scaled to this bigger Magnet.
    for (let k = 0; k < 2; k++) {
      stroke(svg, circlePoints(cx, y, 19 - k * 4, 16 - k * 4), r, 1.5, 1.3, animate ? "draw" : "");
    }
  }
  return xs.map((x) => x / width);
}
