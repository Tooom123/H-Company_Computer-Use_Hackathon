// The "In action" screen: H Companion's overlay drawn the way the app draws it (agent/src/hcs_agent/overlay.py),
// ported to SVG. Red pencil strokes in two jittered passes, notes on paper scraps, the main control framed from
// its real bounds (like the agent does with the accessibility box), and the
// status badge at the bottom (live words while the user speaks).
// Coordinates are the 1440x900 screen of the stage; the stage is scaled to the page with CSS.

const W = 1440;
const H = 900;
const NS = "http://www.w3.org/2000/svg";
const TEXT_SCALE = 1.5; // overlay.py draws all handwriting 1.5x the base sizes
const PAPER = "rgba(255,255,251,.93)";
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

const stage = document.getElementById("stage");
const svg = document.getElementById("pencil");
const demo = document.getElementById("demo");
const target = document.getElementById("target");

// --- fit the 1440x900 screen to the page (whole screen; on phones, the part around the button) ---------------
function fit() {
  const w = demo.querySelector(".screen").clientWidth;
  const narrow = w < 640;
  const view = narrow ? { x: 660, y: 40, w: 780, h: 470 } : { x: 0, y: 0, w: W, h: H };
  const k = w / view.w;
  demo.style.setProperty("--k", k);
  demo.style.setProperty("--ox", `${view.x * k}px`);
  demo.style.setProperty("--oy", `${view.y * k}px`);
  demo.querySelector(".screen").style.height = `${view.h * k}px`;
}
fit();
new ResizeObserver(fit).observe(demo); // the width settles after fonts and layout: refit each time it changes

// --- seeded randomness: same drawing on every load, like overlay.py's random.Random(seed) ----------------
function rng(seed) {
  let a = seed >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return { uniform: (lo, hi) => lo + (hi - lo) * next(), choice: (arr) => arr[Math.floor(next() * arr.length)] };
}

const el = (tag, attrs, parent) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  (parent || svg).appendChild(n);
  return n;
};

// strokes are revealed one after the other, like the overlay's progressive drawing
let strokes = [];
function stroke(points, rnd, width = 1.5, jitter = 1.4, parent) {
  const group = [];
  for (let pass = 0; pass < 2; pass++) {
    const d = points.map(([x, y], i) => `${i ? "L" : "M"}${(x + rnd.uniform(-jitter, jitter)).toFixed(1)} ${(y + rnd.uniform(-jitter, jitter)).toFixed(1)}`).join("");
    group.push(el("path", { d, class: "ink", "stroke-width": width, pathLength: 1 }, parent));
  }
  strokes.push(group);
}

function circle(cx, cy, rnd, rx = 42, ry = 34, parent) {
  const pts = [];
  for (let i = 0; i < 40; i++) {
    const a = -0.35 + (i / 39) * (2 * Math.PI + 0.55);
    pts.push([cx + rx * Math.cos(a), cy + ry * Math.sin(a)]);
  }
  stroke(pts, rnd, 1.6, 1.8, parent);
}

function roundedBox(cx, cy, w, h, rnd) {
  const r = 10;
  const pts = [];
  // screen coordinates (y down): the same corners as overlay.py, mirrored
  for (const [a0, [ox, oy]] of [[Math.PI, [cx - w / 2 + r, cy - h / 2 + r]], [Math.PI / 2, [cx + w / 2 - r, cy - h / 2 + r]],
    [0, [cx + w / 2 - r, cy + h / 2 - r]], [-Math.PI / 2, [cx - w / 2 + r, cy + h / 2 - r]]]) {
    for (let k = 0; k < 5; k++) {
      const a = a0 - (k / 4) * (Math.PI / 2);
      pts.push([ox + r * Math.cos(a), oy - r * Math.sin(a)]);
    }
  }
  pts.push(pts[0], [pts[0][0] + 6, pts[0][1] + 3]);
  stroke(pts, rnd, 1.6, 1.6);
}

/** A scrap of white paper: roughly cut edges, slight tilt, soft shadow. */
function paper(x, y, w, h, rnd, color = PAPER, parent) {
  const tilt = rnd.uniform(-0.03, 0.03);
  const cx = x + w / 2;
  const cy = y + h / 2;
  const rot = (px, py) => [cx + (px - cx) * Math.cos(tilt) - (py - cy) * Math.sin(tilt), cy + (px - cx) * Math.sin(tilt) + (py - cy) * Math.cos(tilt)];
  const pts = [];
  for (const [[ax, ay], [bx, by], n] of [[[x, y], [x + w, y], 5], [[x + w, y], [x + w, y + h], 3], [[x + w, y + h], [x, y + h], 5], [[x, y + h], [x, y], 3]]) {
    for (let i = 0; i < n; i++) {
      const t = i / n;
      pts.push(rot(ax + (bx - ax) * t + rnd.uniform(-3, 3), ay + (by - ay) * t + rnd.uniform(-3, 3)));
    }
  }
  return el("polygon", { points: pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "), fill: color, class: "scrap" }, parent);
}

function measure(text, size) {
  const t = el("text", { x: -9999, y: -9999, "font-size": size * TEXT_SCALE });
  t.textContent = text;
  const w = t.getComputedTextLength();
  t.remove();
  return [w + 4, size * TEXT_SCALE * 1.15 + 6];
}

/** Handwritten text on a paper scrap; (px, py) = paper top-left. Returns the paper rect. */
function note(px, py, text, rnd, { size = 19, color = PAPER, underline = true, parent } = {}) {
  const [tw, th] = measure(text, size);
  const pw = tw + 20;
  const ph = th + 18;
  const g = el("g", { class: "note" }, parent);
  paper(px, py, pw, ph, rnd, color, g);
  const t = el("text", { x: px + 10, y: py + 9 + th * 0.78, "font-size": size * TEXT_SCALE }, g);
  t.textContent = text;
  if (underline) {
    const y = py + 9 + th + 1;
    stroke(Array.from({ length: 7 }, (_, i) => [px + 10 + i * (tw / 6), y + (i % 2 ? -2 : 2)]), rnd, 1.0, 1.0, g);
  }
  return { x: px, y: py, w: pw, h: ph, g };
}

// --- status badge (bottom centre) ------------------------------------------------------------------------
const badgeLayer = el("g", {});
function badge(text, pulsing) {
  badgeLayer.replaceChildren();
  if (!text) return;
  const rnd = rng(11);
  const [tw, th] = measure(text, 15);
  const w = tw + 44;
  const h = th + 14;
  const x = W / 2 - w / 2;
  const y = H - 114 - h;
  paper(x, y, w, h, rnd, PAPER, badgeLayer);
  el("circle", { cx: x + 19, cy: y + h / 2, r: 5, class: `dot${pulsing ? " pulse" : ""}` }, badgeLayer);
  const saved = strokes;
  strokes = [];
  circle(x + 19, y + h / 2, rnd, 8, 7, badgeLayer); // a loose pencil ring around the dot
  strokes = saved;
  const t = el("text", { x: x + 36, y: y + h / 2 + th * 0.3, "font-size": 15 * TEXT_SCALE }, badgeLayer);
  t.textContent = text;
}

// --- the scene: step 2 of hcompany_platform_create_api_key ---------------------------------------------------
const STEP = { step: 1, text: "Click Create an API key" };
const sceneLayer = el("g", {});

/** The button's bounds in screen coordinates, read from the page itself (the agent gets them from a11y). */
function targetBox() {
  // layout coordinates (offset*), not getBoundingClientRect: the cutout is rotated and the stage scaled, which
  // would skew a bounding box; offsets stay in the 1440x900 screen's own pixels.
  let x = 0;
  let y = 0;
  for (let n = target; n && n !== stage; n = n.offsetParent) { x += n.offsetLeft; y += n.offsetTop; }
  return [x, y, target.offsetWidth, target.offsetHeight];
}

function drawScene() {
  sceneLayer.replaceChildren();
  strokes = [];
  const seed = 4; // style = seed % 4 = 0: a wide control gets the loose rounded box
  const rnd = rng(seed);
  const [bx, by, bw, bh] = targetBox();
  const tx = bx + bw / 2;
  const ty = by + bh / 2;
  const label = `${STEP.step}. ${STEP.text}`;
  const [lw, lh] = measure(label, 19);
  const pw = lw + 20;
  const ph = lh + 18;
  const halfW = bw / 2 + 14;
  const halfH = bh / 2 + 14;
  const right = tx + halfW + pw + 30 < W;
  const px = right ? tx + halfW + 10 : tx - halfW - 10 - pw;
  const py = ty - halfH - ph; // above the control
  note(px, py, label, rnd, { parent: sceneLayer });
  // frame hugging the control (overlay.py _frame with the element box: w = bw + 18, h = bh + 16)
  const fw = bw + 18;
  const fh = bh + 16;
  svg.appendChild(sceneLayer);
  const parentBackup = svg;
  roundedBox(tx, ty, fw, fh, rnd);
  // strokes drawn outside sceneLayer (the frame) move into it so the scene shows and hides as one
  for (const g of strokes) for (const p of g) if (p.parentNode === parentBackup) sceneLayer.appendChild(p);
}

function reveal(ms) {
  const all = strokes.flat();
  sceneLayer.querySelectorAll(".note").forEach((n) => (n.style.opacity = 0));
  all.forEach((p) => { p.style.strokeDasharray = 1; p.style.strokeDashoffset = 1; });
  sceneLayer.style.visibility = "visible";
  if (reduce || !ms) {
    sceneLayer.querySelectorAll(".note").forEach((n) => (n.style.opacity = 1));
    all.forEach((p) => (p.style.strokeDashoffset = 0));
    return;
  }
  sceneLayer.querySelectorAll(".note").forEach((n, i) => {
    n.style.transition = `opacity .25s ${i * 0.25}s`;
    requestAnimationFrame(() => (n.style.opacity = 1));
  });
  const per = ms / Math.max(1, strokes.length);
  strokes.forEach((g, i) => g.forEach((p) => {
    p.style.transition = `stroke-dashoffset ${per * 1.6}ms ease-out ${300 + i * per}ms`;
    requestAnimationFrame(() => requestAnimationFrame(() => (p.style.strokeDashoffset = 0)));
  }));
}

// --- the sequence: the request heard live, then the guidance -------------------------------------------------
const SAID = "show me how to create an API key";
const IDLE = "⌃⇧H: new request";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function play() {
  sceneLayer.style.visibility = "hidden";
  badge("Listening…", true);
  await wait(700);
  const words = SAID.split(" ");
  for (let i = 1; i <= words.length; i++) {
    badge(words.slice(0, i).join(" "), true); // live words while speaking
    await wait(230);
  }
  await wait(450);
  badge("Transcribing…", false);
  await wait(600);
  badge("Holo is preparing guidance…", true);
  await wait(1300);
  badge(null);
  drawScene();
  reveal(1400);
  await wait(2200);
  badge(IDLE, false);
}

await document.fonts.ready;
if (reduce) {
  drawScene();
  reveal(0);
  badge(IDLE, false);
} else {
  sceneLayer.style.visibility = "hidden";
  badge(IDLE, false);
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { io.disconnect(); play(); }
  }, { threshold: 0.45 });
  io.observe(demo);
}
addEventListener("resize", () => { if (sceneLayer.style.visibility === "visible") { drawScene(); reveal(0); } });
