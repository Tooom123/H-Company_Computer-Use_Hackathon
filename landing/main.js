// H Companion landing — the 3D "H" keycap on a blue (clicky) switch.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const canvas = document.getElementById("key");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new THREE.Scene();
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.55;

const camera = new THREE.PerspectiveCamera(24, 1, 0.1, 50);
const target = new THREE.Vector3(0, 0.2, 0);
camera.position.set(0, 4.3, 3.0);
camera.lookAt(target);

// lights: neutral key + cool rim + blue glow from the switch
const key = new THREE.DirectionalLight(0xffffff, 2.2);
key.position.set(2.5, 4, 3);
scene.add(key);
const rim = new THREE.PointLight(0xdfe6ff, 10, 8);
rim.position.set(-2.2, 1.6, -1.6);
scene.add(rim);
const glow = new THREE.PointLight(0x2f7bff, 2.5, 3);
glow.position.set(0, 0.1, 0.6);
scene.add(glow);

// ------------------------------------------------------------------------------------------------
// geometry helpers
function roundedRect(w, d, r) {
  const s = new THREE.Shape();
  const x = -w / 2, y = -d / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + d - r); s.quadraticCurveTo(x + w, y + d, x + w - r, y + d);
  s.lineTo(x + r, y + d); s.quadraticCurveTo(x, y + d, x, y + d - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/** Tapered keycap with rounded top edges. Returns {geo, top, topWidth}. */
function keycapGeometry() {
  const base = 0.92, height = 0.3, taper = 0.18;
  const geo = new THREE.ExtrudeGeometry(roundedRect(base - 0.1, base - 0.1, 0.12), {
    depth: height - 0.08, bevelEnabled: true, bevelThickness: 0.08, bevelSize: 0.05,
    bevelSegments: 8, curveSegments: 14,
  });
  geo.rotateX(-Math.PI / 2);
  geo.computeBoundingBox();
  const { min, max } = geo.boundingBox;
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const t = (pos.getY(i) - min.y) / (max.y - min.y);
    const k = 1 - taper * t;
    pos.setX(i, pos.getX(i) * k);
    pos.setZ(i, pos.getZ(i) * k);
  }
  geo.translate(0, -min.y, 0);
  return { geo, top: max.y - min.y, topWidth: (base - 0.1) * (1 - taper) };
}

function legendTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const g = c.getContext("2d");
  g.fillStyle = "#0d0d12";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = '800 340px "Plus Jakarta Sans", system-ui, sans-serif';
  g.fillText("H", 256, 276);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

class Helix extends THREE.Curve {
  constructor(r, h, turns) { super(); this.r = r; this.h = h; this.turns = turns; }
  getPoint(t, out = new THREE.Vector3()) {
    const a = t * Math.PI * 2 * this.turns;
    return out.set(Math.cos(a) * this.r, t * this.h, Math.sin(a) * this.r);
  }
}

// ------------------------------------------------------------------------------------------------
// materials
const mat = {
  cap: new THREE.MeshPhysicalMaterial({ color: 0xf2f2f5, roughness: 0.42, clearcoat: 0.25, clearcoatRoughness: 0.5 }),
  housingDark: new THREE.MeshPhysicalMaterial({ color: 0x16161d, roughness: 0.55 }),
  housingClear: new THREE.MeshPhysicalMaterial({
    color: 0xffffff, roughness: 0.08, transmission: 0.92, thickness: 0.25, ior: 1.45,
    transparent: true, opacity: 1, side: THREE.DoubleSide,
  }),
  stem: new THREE.MeshPhysicalMaterial({
    color: 0x2f7bff, roughness: 0.28, clearcoat: 0.6, emissive: 0x0b2a7a, emissiveIntensity: 0.35,
  }),
  metal: new THREE.MeshStandardMaterial({ color: 0xd8d8e2, metalness: 1, roughness: 0.28 }),
  copper: new THREE.MeshStandardMaterial({ color: 0xd99a5b, metalness: 1, roughness: 0.3 }),
};

// ------------------------------------------------------------------------------------------------
// model
const model = new THREE.Group();
scene.add(model);

// switch (Cherry-MX-like proportions, 1 unit ≈ 1u key)
const sw = new THREE.Group();
model.add(sw);
const bottom = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.26, 0.8), mat.housingDark);
bottom.position.y = -0.13;
const post = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.16, 24), mat.housingDark);
post.position.y = -0.34;
const pins = [[-0.2, 0.12], [0.18, -0.18]].map(([x, z]) => {
  const p = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.2, 12), mat.copper);
  p.position.set(x, -0.36, z);
  return p;
});
const topGeo = new THREE.CylinderGeometry(0.62 / Math.SQRT2, 0.8 / Math.SQRT2, 0.3, 4, 1, true);
topGeo.rotateY(Math.PI / 4);
const topHousing = new THREE.Mesh(topGeo, mat.housingClear);
topHousing.position.y = 0.15;
const topLid = new THREE.Mesh(new THREE.RingGeometry(0.2, 0.44, 4, 1), mat.housingClear);
topLid.geometry.rotateZ(Math.PI / 4);
topLid.rotation.x = -Math.PI / 2;
topLid.position.y = 0.3;
sw.add(bottom, post, ...pins, topHousing, topLid);

const springGroup = new THREE.Group();
springGroup.position.y = -0.02;
const spring = new THREE.Mesh(new THREE.TubeGeometry(new Helix(0.16, 0.3, 7), 360, 0.012, 8), mat.metal);
springGroup.add(spring);
sw.add(springGroup);

const stem = new THREE.Group();
const column = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.4, 0.26), mat.stem);
column.position.y = 0.2;
const armA = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.2, 0.07), mat.stem);
const armB = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.2, 0.22), mat.stem);
armA.position.y = armB.position.y = 0.5;
const slider = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.08, 0.12), mat.stem); // the tactile "click" slider
slider.position.set(0, 0.1, 0.16);
stem.add(column, armA, armB, slider);
sw.add(stem);

// keycap
const cap = new THREE.Group();
const { geo: capGeo, top: capTop, topWidth } = keycapGeometry();
const capMesh = new THREE.Mesh(capGeo, mat.cap);
cap.add(capMesh);
const legendMat = new THREE.MeshStandardMaterial({
  transparent: true, roughness: 0.5, polygonOffset: true, polygonOffsetFactor: -2,
});
const legend = new THREE.Mesh(new THREE.PlaneGeometry(topWidth * 0.98, topWidth * 0.98), legendMat);
legend.rotation.x = -Math.PI / 2;
legend.position.y = capTop + 0.002;
cap.add(legend);
model.add(cap);



model.rotation.set(0, -0.18, 0);

// ------------------------------------------------------------------------------------------------
// animation: exploded idle -> seat -> press (click) -> release -> explode
const SEAT_Y = 0.34, LIFT = 0.17, TRAVEL = 0.2;
let pressT = -1; // seconds since press started, -1 = idle
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const seg = (t, a, b) => Math.min(1, Math.max(0, (t - a) / (b - a)));
let clicked = false, released = false;

let everPressed = false;
let lastTease = 0;
function pressKey() {
  everPressed = true;
  if (pressT >= 0 && pressT < 0.75) return;
  pressT = 0; clicked = false; released = false;
  audio.resume();
}

function pose(t, time) {
  let assemble = 0, press = 0;
  if (pressT >= 0) {
    const p = pressT;
    assemble = ease(seg(p, 0, 0.32)) * (1 - ease(seg(p, 1.25, 1.85)));
    press = ease(seg(p, 0.32, 0.44)) * (1 - ease(seg(p, 0.6, 0.78)));
    if (!clicked && p > 0.4) { clicked = true; audio.click(1); }
    if (!released && p > 0.66) { released = true; audio.click(0.55); }
    if (p > 1.9) pressT = -1;
  }
  const bob = reduceMotion ? 0 : Math.sin(time * 1.6) * 0.035;
  // tease: a small double dip every 3.5 s until the key has been pressed once
  let tease = 0;
  if (!everPressed && !reduceMotion) {
    const ph = time % 3.5;
    if (ph < 0.7) tease = Math.pow(Math.sin((ph / 0.35) * Math.PI), 2) * (ph < 0.35 ? 1 : 0.6);
  }
  cap.position.y = SEAT_Y + (1 - assemble) * (LIFT + bob) - press * TRAVEL - tease * 0.09;
  lastTease = tease;
  cap.rotation.z = (1 - assemble) * (reduceMotion ? 0 : Math.sin(time * 0.9) * 0.03);
  stem.position.y = -press * TRAVEL;
  springGroup.scale.y = 1 - press * 0.55;
  mat.stem.emissiveIntensity = 0.35 + press * 1.2;
  glow.intensity = 2.5 + press * 6;
}

// ------------------------------------------------------------------------------------------------
// clicky blue-switch sound (synthesised, no asset)
const audio = {
  ctx: null,
  resume() {
    this.ctx ??= new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") this.ctx.resume();
  },
  click(gain) {
    if (!this.ctx) return;
    const ctx = this.ctx, now = ctx.currentTime, len = 0.03;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * len), ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / d.length, 6);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const hp = ctx.createBiquadFilter(); hp.type = "bandpass"; hp.frequency.value = 3200; hp.Q.value = 0.9;
    const g = ctx.createGain(); g.gain.value = 0.9 * gain;
    src.connect(hp).connect(g).connect(ctx.destination);
    src.start(now);
  },
};

// ------------------------------------------------------------------------------------------------
// interaction: drag to rotate, click to press, pointer parallax, keyboard "h e l p"
let dragging = false, moved = 0, lastX = 0, lastY = 0, userYaw = 0, userPitch = 0;
let px = 0, py = 0;
canvas.addEventListener("pointerdown", (e) => {
  dragging = true; moved = 0; lastX = e.clientX; lastY = e.clientY;
  canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener("pointermove", (e) => {
  if (!dragging) return;
  const dx = e.clientX - lastX, dy = e.clientY - lastY;
  moved += Math.abs(dx) + Math.abs(dy);
  userYaw += dx * 0.01;
  userPitch = Math.max(-0.5, Math.min(0.35, userPitch + dy * 0.006));
  lastX = e.clientX; lastY = e.clientY;
});
canvas.addEventListener("pointerup", () => {
  dragging = false;
  if (moved < 6) trigger();
});
addEventListener("pointermove", (e) => {
  px = (e.clientX / innerWidth) * 2 - 1;
  py = (e.clientY / innerHeight) * 2 - 1;
});

const word = document.getElementById("word");
const title = document.querySelector(".title");
const ion = word.querySelector(".ion");
const grade = document.getElementById("grade");
const slogan = document.getElementById("slogan");
const hero = document.getElementById("hero");
const taps = document.getElementById("taps");
let companion = false;
const timers = [];
function later(ms, fn) { timers.push(setTimeout(fn, ms)); }
// Company -> Companion, corrected in red pen: strike the y, write "ion", grade it, underline Help
const STEPS = [
  [380, () => title.classList.add("corrected")],
  [420, () => word.classList.add("struck")],
  [900, () => ion.classList.add("on")],
  [1550, () => grade.classList.add("on")],
  [1900, () => slogan.classList.add("show")],
  [2400, () => slogan.classList.add("underlined")],
  [2700, () => hero.classList.add("peek")],
  [2700, () => title.setAttribute("aria-label", "H Companion")],
];
function correct(instant = false) {
  for (const [ms, fn] of STEPS) instant ? fn() : later(ms, fn);
}
// one-way: once corrected in red pen, the hero stays corrected (the key still clicks)
function toggleName() {
  if (companion) return;
  companion = true;
  correct();
}
function trigger() {
  if (pressT >= 0 && pressT < 0.75) return;
  pressKey();
  toggleName();
}
addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
  if (e.key.toLowerCase() === "h") trigger();
});

// tap marks: pinned to the keycap's top-left corner on screen, strokes push outward on each dip
const corner = new THREE.Vector3();
const tapPaths = [...taps.querySelectorAll("path")];
const tapDirs = [[0, -1], [-0.707, -0.707], [-1, 0]];
function placeTaps() {
  if (everPressed) { taps.style.opacity = 0; return; }
  cap.updateMatrixWorld();
  corner.set(-topWidth / 2 - 0.02, capTop, -topWidth / 2 - 0.02);
  cap.localToWorld(corner).project(camera);
  const x = canvas.offsetLeft + ((corner.x + 1) / 2) * canvas.clientWidth;
  const y = canvas.offsetTop + ((1 - corner.y) / 2) * canvas.clientHeight;
  taps.style.left = `${x}px`;
  taps.style.top = `${y}px`;
  taps.style.opacity = (0.22 + lastTease * 0.7).toFixed(3);
  const push = lastTease * 6;
  tapPaths.forEach((p, i) => p.setAttribute("transform", `translate(${tapDirs[i][0] * push} ${tapDirs[i][1] * push})`));
}

// halftone dot fields on the sides of the hero (as on hcompany.ai)
const dots = document.getElementById("dots");
function drawDots() {
  const r = dots.getBoundingClientRect();
  const dpr = Math.min(devicePixelRatio, 2);
  dots.width = Math.round(r.width * dpr);
  dots.height = Math.round(r.height * dpr);
  const g = dots.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, r.width, r.height);
  const W = r.width, H = r.height, step = 7;
  const blobs = [
    { x: 0, y: 0, r: Math.max(W * 0.42, 300), tint: 0.5 },   // top-left corner
    { x: W, y: H, r: Math.max(W * 0.34, 240), tint: 0.15 },  // bottom-right corner
  ];
  for (let y = step / 2; y < H; y += step) {
    for (let x = step / 2; x < W; x += step) {
      let k = 0, tint = 0;
      for (const b of blobs) {
        const t = 1 - Math.hypot(x - b.x, y - b.y) / b.r;
        if (t > k) { k = t; tint = b.tint * Math.min(1, Math.hypot(x - b.x, y - b.y) / (b.r * 0.6)); }
      }
      if (k <= 0) continue;
      const e = Math.pow(k, 1.4);
      const red = Math.round(255 - 61 * tint), green = Math.round(255 - 95 * tint), blue = Math.round(255 - 17 * tint);
      g.fillStyle = `rgba(${red},${green},${blue},${(0.06 + 0.26 * e).toFixed(3)})`;
      g.beginPath();
      g.arc(x, y, 0.35 + 0.8 * e, 0, Math.PI * 2);
      g.fill();
    }
  }
}
new ResizeObserver(drawDots).observe(dots);

// ------------------------------------------------------------------------------------------------
// render loop
function resize() {
  const { clientWidth: w, clientHeight: h } = canvas;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvas);

let visible = true;
new IntersectionObserver(([e]) => (visible = e.isIntersecting)).observe(canvas);

const clock = new THREE.Clock();
let yaw = -0.18, pitch = 0;
function frame() {
  requestAnimationFrame(frame);
  const dt = Math.min(clock.getDelta(), 0.05);
  if (!visible) return;
  const time = clock.elapsedTime;
  if (pressT >= 0) pressT += dt;
  if (!dragging) userYaw *= 0.97, userPitch *= 0.97;
  const idle = reduceMotion ? 0 : Math.sin(time * 0.45) * 0.12;
  yaw += (-0.18 + idle + px * 0.25 + userYaw - yaw) * 0.08;
  pitch += (py * 0.08 + userPitch - pitch) * 0.08;
  model.rotation.y = yaw;
  model.rotation.x = pitch;
  pose(dt, time);
  placeTaps();
  renderer.render(scene, camera);
}

document.fonts.load('800 340px "Plus Jakarta Sans"').finally(() => {
  legendMat.map = legendTexture();
  legendMat.needsUpdate = true;
  resize();
  frame();
});

// ?companion in the URL plays the transformation on load (demo / screenshots)
const qp = new URLSearchParams(location.search).get("companion");
if (qp === "static") {
  companion = true;
  everPressed = true;
  document.documentElement.classList.add("no-anim");
  correct(true);
} else if (qp !== null) setTimeout(trigger, 600);
