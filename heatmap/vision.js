// Vision page: the same honeycomb heatmap as index.html, but driven by the webcam (WebGazer, Édouard's
// setup) instead of the mouse. Calibrate (9 dots) → validate (4 other dots, error measured) → buttons.
import { GazeHeatmap, scanTargets } from "./gaze-heatmap.js";
import { CALIBRATION, CLICKS_PER_TARGET, VALIDATION, accuracyLabel, rate, toPixels, validationError } from "./gaze-calibration.js";
import { WebGazerTracker, cameraErrorMessage } from "./webgazer-tracker.js";

const $ = (id) => document.getElementById(id);
const stage = $("stage");
const params = new URLSearchParams(location.search);
// Embedded in the desktop app (gaze-window.mjs): gaze points and accuracy go to the agent through the bridge.
// Opened by the desktop app in the browser (Linux): the same calls, posted to the app's local server.
let feedLast = 0;
const browserFeed = params.has("feed") ? {
  sample: (x, y) => {
    const now = performance.now();
    if (now - feedLast < 66) return;
    feedLast = now;
    fetch("/gaze", { method: "POST", body: JSON.stringify({ x, y }) }).catch(() => {});
  },
  accuracy: (px) => fetch("/accuracy", { method: "POST", body: JSON.stringify({ px }) }).catch(() => {}),
  track: () => {},
  close: () => window.close(),
} : null;
const bridge = params.has("embedded") ? window.hcsGaze : browserFeed;
if (bridge) document.body.classList.add("embedded");

let mode = "intro"; // intro | calibrate | validate | result | test
let source = "eyes"; // eyes | mouse
let tracker = null;
let accuracy = null; // {medianPx, worstPx, ...}
const stamps = []; // sample times, for the Hz readout
let onGaze = null; // the current phase's listener for raw samples

// --- heatmap (as on the mouse page) -----------------------------------------------------------------
let lastBest = null;
const heat = new GazeHeatmap({ canvas: $("heat"), onUpdate: show });
heat.start();

// --- buttons at random, non-overlapping places ---------------------------------------------------------
let seed = Number(params.get("seed")) || 0;
const rand = () => (seed ? ((seed = (seed * 16807) % 2147483647) / 2147483647) : Math.random());
function shuffle() {
  const placed = [];
  for (const b of stage.querySelectorAll("button")) {
    const w = b.offsetWidth;
    const h = b.offsetHeight;
    for (let tries = 0; tries < 300; tries++) {
      const x = 60 + rand() * (innerWidth - w - 120);
      const y = 60 + rand() * (innerHeight - h - 120);
      const clear = placed.every((p) => Math.hypot(p.x - x, p.y - y) > 300);
      const offHud = !(x < 320 && y > innerHeight - 300) && !(x > innerWidth - 360 && y > innerHeight - 300);
      if ((clear && offHud) || tries === 299) {
        b.style.left = `${x}px`;
        b.style.top = `${y}px`;
        placed.push({ x, y });
        break;
      }
    }
  }
  heat.setTargets(scanTargets(stage));
}
addEventListener("resize", () => heat.setTargets(scanTargets(stage)));

// --- the gaze signal -------------------------------------------------------------------------------------
function onSample(sample) {
  if (source !== "eyes") return;
  if (sample) stamps.push(sample.emittedAt);
  if (bridge && sample && mode === "tracking") bridge.sample(sample.x, sample.y);
  while (stamps.length && performance.now() - stamps[0] > 2000) stamps.shift();
  if (onGaze) onGaze(sample);
  if (mode === "test") heat.push(sample);
}

async function startCamera() {
  if (browserFeed && !document.fullscreenElement) {
    document.documentElement.requestFullscreen?.().catch(() => {}); // the gaze maps to the screen only in full screen
  }
  $("introErr").textContent = "";
  $("startBtn").disabled = true;
  $("startBtn").textContent = "Starting the camera…";
  try {
    tracker = new WebGazerTracker(onSample);
    await tracker.start();
    calibrate();
  } catch (e) {
    $("introErr").textContent = cameraErrorMessage(e);
    $("startBtn").disabled = false;
    $("startBtn").textContent = "Start the camera";
    tracker?.dispose();
    tracker = null;
  }
}

// --- 1. calibration: look at each dot and click it 5 times (only clicks with a face count) ---------------
function calibrate() {
  mode = "calibrate";
  accuracy = null;
  heat.setUncertainty(0);
  $("intro").hidden = true;
  $("result").hidden = true;
  $("hud").hidden = true;
  stage.hidden = true;
  $("calib").hidden = false;
  tracker.showPreview(true);
  const layer = $("calib");
  layer.querySelectorAll(".dot").forEach((d) => d.remove());
  const targets = toPixels(CALIBRATION, innerWidth, innerHeight);
  let i = 0;
  let clicks = 0;
  const dot = document.createElement("button");
  dot.className = "dot";
  layer.append(dot);
  const place = () => {
    const t = targets[i];
    cameraAwayFrom(t);
    dot.style.left = `${t.x}px`;
    dot.style.top = `${t.y}px`;
    dot.style.transform = `scale(${1 - clicks * 0.12})`;
    $("banner").textContent = `Look at the red dot and click it ${CLICKS_PER_TARGET - clicks}× · point ${i + 1} of ${targets.length}`;
  };
  dot.onclick = () => {
    const t = targets[i];
    if (!tracker.recordCalibrationPoint(t.x, t.y)) {
      dot.classList.remove("miss");
      void dot.offsetWidth;
      dot.classList.add("miss");
      $("banner").textContent = "Face not found: look at the dot, face the camera, then click again";
      return;
    }
    clicks += 1;
    if (clicks >= CLICKS_PER_TARGET) {
      clicks = 0;
      i += 1;
      if (i >= targets.length) {
        dot.remove();
        return validate();
      }
    }
    place();
  };
  place();
}

/** Put the camera preview in the corner opposite the dot, so it never hides the dot to look at. */
function cameraAwayFrom(t) {
  const corner = `cam-${t.y < innerHeight / 2 ? "b" : "t"}${t.x < innerWidth / 2 ? "r" : "l"}`;
  document.body.classList.remove("cam-tl", "cam-tr", "cam-bl", "cam-br");
  document.body.classList.add(corner);
}

// --- 2. validation: 4 other dots, just look; the error is measured, never learnt -----------------------
function validate() {
  mode = "validate";
  tracker.showPreview(false);
  const layer = $("calib");
  const targets = toPixels(VALIDATION, innerWidth, innerHeight);
  const runs = targets.map((target) => ({ target, samples: [] }));
  const dot = document.createElement("div");
  dot.className = "dot look";
  layer.append(dot);
  let i = 0;
  const next = () => {
    if (i >= runs.length) {
      onGaze = null;
      dot.remove();
      return finish(validationError(runs));
    }
    const run = runs[i];
    dot.style.left = `${run.target.x}px`;
    dot.style.top = `${run.target.y}px`;
    $("banner").textContent = `Now just look at the dot, don't click · ${i + 1} of ${runs.length}`;
    onGaze = null;
    setTimeout(() => { // let the eyes land, then listen for 1.5 s
      onGaze = (s) => s && run.samples.push(s);
      setTimeout(() => {
        i += 1;
        next();
      }, 1500);
    }, 700);
  };
  next();
}

function finish(err) {
  mode = "result";
  accuracy = err;
  $("calib").hidden = true;
  $("result").hidden = false;
  if (!err) {
    $("resTitle").textContent = "No gaze during the check";
    $("resText").textContent = "The camera lost your face. Face it, light it from the front, and recalibrate.";
    $("goBtn").hidden = true;
    return;
  }
  $("goBtn").hidden = false;
  heat.setUncertainty(err.medianPx); // the honeycomb is as wide as the measured error
  bridge?.accuracy(err.medianPx);
  $("resTitle").textContent = `Accuracy: ~${err.medianPx} px (${accuracyLabel(err.medianPx)})`;
  $("resText").textContent = `Typical distance between where you looked and where the camera thinks you looked, on 4 points it never learnt (worst ${err.worstPx} px${err.missing ? `, ${err.missing} point(s) without face` : ""}). The honeycomb is sized to it.`;
}

// --- 3. test: the buttons -----------------------------------------------------------------------------------
function test() {
  mode = "test";
  $("result").hidden = true;
  $("intro").hidden = true;
  stage.hidden = false;
  $("hud").hidden = false;
  document.body.classList.remove("cam-tl", "cam-tr", "cam-bl", "cam-br"); // bottom-right, clear of the buttons
  tracker?.showPreview($("preview").checked);
  requestAnimationFrame(shuffle);
}

// Looking at a button long enough "picks" it: what a gaze click would be, shown, never clicked.
const cooldown = new Map();
let picks = 0;
function show(s) {
  stage.querySelectorAll("button").forEach((b) => b.classList.toggle("best", s?.best?.id === b.id));
  if (!s) {
    $("out").textContent = mode === "test" ? "no gaze: face not found" : "";
    lastBest = null;
    return;
  }
  lastBest = s.best?.id ?? null;
  const now = performance.now();
  for (const t of s.targets) {
    if (t.intent >= 0.999 && s.best?.id === t.id && now - (cooldown.get(t.id) || 0) > 2000) {
      cooldown.set(t.id, now);
      picks += 1;
      $("picks").textContent = String(picks);
      const b = $(t.id);
      b?.classList.add("picked");
      setTimeout(() => b?.classList.remove("picked"), 700);
    }
  }
  $("out").innerHTML = `σ <b>${s.sigma.toFixed(0)}px</b> · nothing <b>${(s.pNone * 100).toFixed(0)}%</b>` +
    s.targets.map((t) => `<div>${t.label.padEnd(7)} <b>${(t.p * 100).toFixed(0).padStart(3)}%</b> · dwell ${(t.intent * 100).toFixed(0)}%</div><div class="bar"><i style="width:${(t.p * 100).toFixed(1)}%"></i></div>`).join("");
}

setInterval(() => {
  if (mode !== "test") return;
  $("signal").textContent = source === "eyes" ? `webcam · WebGazer @ ${rate(stamps, performance.now())} Hz` : "mouse (comparison)";
  $("acc").textContent = source === "mouse" ? "—" : accuracy ? `~${accuracy.medianPx} px (${accuracyLabel(accuracy.medianPx)})` : "not measured";
}, 500);

// --- mouse, for comparison (same 30 Hz + no noise) ------------------------------------------------------------
let mx = null;
let my = null;
addEventListener("pointermove", (e) => {
  mx = e.clientX;
  my = e.clientY;
});
setInterval(() => {
  if (mode !== "test" || source !== "mouse") return;
  heat.push(mx === null ? null : { x: mx, y: my, emittedAt: performance.now() });
}, 33);
function useMouse(on) {
  source = on ? "mouse" : "eyes";
  heat.setUncertainty(on ? 0 : accuracy?.medianPx || 0);
  heat.push(null);
}

// --- did the gaze predict the click? --------------------------------------------------------------------------
let hits = 0;
let total = 0;
stage.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  total += 1;
  if (lastBest === b.id) hits += 1;
  $("score").textContent = `${hits}/${total}`;
});

// --- controls -------------------------------------------------------------------------------------------------
$("startBtn").onclick = startCamera;
if (bridge) { // desktop app: the mouse comparison makes no sense; the result button starts tracking
  $("mouseBtn").hidden = true;
  $("closeBtn").hidden = false;
  $("closeBtn").onclick = () => bridge.close();
  $("goBtn").textContent = "Start tracking";
}
$("mouseBtn").onclick = () => {
  useMouse(true);
  test();
};
$("goBtn").onclick = bridge ? startTracking : test;

/** Desktop app: calibration done, the window becomes invisible and click-through and keeps sending the gaze. */
function startTracking() {
  mode = "tracking";
  $("result").hidden = true;
  stage.hidden = true;
  $("hud").hidden = true;
  heat.stop();
  tracker?.showPreview(false);
  document.body.classList.add("tracking");
  if (browserFeed) $("trackingNote").hidden = false; // a browser tab cannot become click-through: say what to do
  bridge.track();
}
$("redoBtn").onclick = async () => {
  await tracker?.recalibrate();
  calibrate();
};
$("preview").onchange = () => tracker?.showPreview($("preview").checked);
$("ctx").oninput = () => {
  heat.opts.contextWeight = Number($("ctx").value);
  $("ctxV").textContent = $("ctx").value;
};
$("ctxV").textContent = $("ctx").value;
addEventListener("keydown", async (e) => {
  if (mode !== "test") return;
  const k = e.key.toLowerCase();
  if (k === "r") shuffle();
  if (k === "m" && tracker) useMouse(source === "eyes"); // no camera started: the mouse is all there is
  if (k === "c" && tracker) {
    useMouse(false);
    await tracker.recalibrate();
    calibrate();
  }
});
addEventListener("beforeunload", () => tracker?.dispose());
