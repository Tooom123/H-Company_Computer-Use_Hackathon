// H Companion app — renderer. Polls the assistant once a second (that poll is also the app's heartbeat:
// while it lasts, the on-screen autonomy slider stays hidden and the setting lives here).
import { drawAutonomy, paintBadge, paintRing } from "./sketch.js";
import { STATUS_LABEL, duration, isBusy, keyLabel, procedureName, readyBadge, safePttPreference, taskLine, when } from "./view.js";

const $ = (id) => document.getElementById(id);
const api = window.hcs;
const LABELS = ["Show me", "Help if I'm stuck", "Do it, I watch"];
const VOICES = [
  { id: "EXAVITQu4vr4xnSDxMaL", name: "Sarah", note: "warm, reassuring" },
  { id: "cgSgspJ2msm6clMCkdW9", name: "Jessica", note: "bright, playful" },
  { id: "hpp4J3VqNfWAUOO0d1Us", name: "Bella", note: "professional, warm" },
  { id: "XrExE9yKIg1WjnnlVkGX", name: "Matilda", note: "upbeat, knowledgeable" },
];
const KEYS = [
  { key: "ctrl+shift+h", label: "⌃⇧H" },
  { key: "cmd+j", label: "⌘J" },
  { key: "alt_r", label: "Right ⌥" },
  { key: "f9", label: "F9" },
];

let status = null; // last /status, null = agent not running
let stepReplyPending = false;
let stopPending = false;
let stopNotice = null;
let lastSessionKey = "";
let view = "home";
let pendingAutonomy = null; // optimistic value while the POST is in flight

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

/** Repaint a paper badge's background to its current size (after layout, and on resize). */
function paint(btn, opts) {
  const svg = btn.querySelector("svg");
  const w = btn.offsetWidth;
  const h = btn.offsetHeight;
  if (!w || !h) return;
  const key = `${w}x${h}:${opts.dot}:${opts.seed}`;
  if (svg.dataset.key === key) return;
  svg.dataset.key = key;
  paintBadge(svg, w, h, opts);
}

// Preferences chosen in the app; pushed again when the assistant (re)starts.
function pref(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(`hcs.${key}`);
    localStorage.setItem(`hcs.${key}`, String(value));
  } catch {
    return null;
  }
  return value;
}

async function syncPrefs() {
  const sp = status && status.speech;
  const want = {};
  const voice = pref("voice");
  const speed = pref("speed");
  const enabled = pref("tts");
  if (sp && sp.available) {
    // A configured/custom voice (e.g. the demo narrator) wins over a stale preset preference.
    if (sp.provider !== "macos" && VOICES.some((v) => v.id === sp.voice)
      && VOICES.some((v) => v.id === voice) && voice !== sp.voice) want.voice = voice;
    if (speed && Number(speed) !== sp.speed) want.speed = Number(speed);
    if (enabled !== null && (enabled === "true") !== sp.enabled) want.enabled = enabled === "true";
    if (Object.keys(want).length) await api.agent("POST", "/voice", want);
  }
  const key = safePttPreference(pref("ptt"));
  if (key && status.voice && status.voice.ptt_key && key !== status.voice.ptt_key) {
    await api.agent("POST", "/ptt", { key });
  }
}

// tabs ------------------------------------------------------------------------------------------
function go(name) {
  view = name;
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("on", b.dataset.go === name);
    b.setAttribute("aria-selected", String(b.dataset.go === name));
  });
  if (name === "home") requestAnimationFrame(renderHome);
  if (name === "activity") loadSessions();
  if (name === "voice") renderVoice();
  if (name === "vision") loadVision();
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
if (api.platform === "darwin") document.body.classList.add("mac");

// window controls (frameless window; macOS keeps its traffic lights and hides these) -------------
$("wcMin").addEventListener("click", () => api.window.minimize());
$("wcMax").addEventListener("click", () => api.window.maximize());
$("wcClose").addEventListener("click", () => api.window.close());
api.window.onState(({ maximized }) => {
  document.body.classList.toggle("maximized", maximized);
  $("wcMax").title = maximized ? "Restore" : "Maximise";
  $("wcMax").setAttribute("aria-label", $("wcMax").title);
});

// home: autonomy, a pencil slider with the three levels written out -------------------------------
// Drag the red dot along the rail, click anywhere on the scrap (it goes to the nearest level), or use the
// arrow keys (1/2/3 too). It snaps on release and applies at once, to the running task as well.
let drawnKey; // what the slider shows (redrawn only on change, the knob loops drawn in like a pencil)
let notchX = [0.17, 0.5, 0.83]; // x (0..1) of each notch, from the last drawing
let drag = null; // {pos} while the dot is held, pos 0..1 along the rail
let autMsgTimer = 0;
const STOPS = LABELS.length;

function buildAutonomy() {
  const box = $("magnet");
  const posAt = (x) => {
    const r = box.getBoundingClientRect();
    const a = r.left + r.width * notchX[0];
    const b = r.left + r.width * notchX[STOPS - 1];
    return Math.max(0, Math.min(1, (x - a) / (b - a)));
  };
  box.addEventListener("pointerdown", (e) => {
    if (!status || status.agent?.observe_only || e.button !== 0) return;
    try {
      box.setPointerCapture(e.pointerId); // keep following the pointer outside the scrap
    } catch {}
    box.focus();
    drag = { pos: posAt(e.clientX) };
    renderAutonomy();
  });
  box.addEventListener("pointermove", (e) => {
    if (!drag) return;
    drag.pos = posAt(e.clientX);
    renderAutonomy();
  });
  box.addEventListener("pointerup", () => {
    if (!drag) return;
    const level = Math.round(drag.pos * (STOPS - 1));
    drag = null;
    setAutonomy(level);
  });
  box.addEventListener("pointercancel", () => ((drag = null), renderAutonomy()));
  box.addEventListener("keydown", (e) => {
    if (!status) return;
    const cur = pendingAutonomy ?? status.autonomy ?? 0;
    const next = { ArrowLeft: cur - 1, ArrowDown: cur - 1, ArrowRight: cur + 1, ArrowUp: cur + 1, Home: 0, End: STOPS - 1, 1: 0, 2: 1, 3: 2 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    setAutonomy(Math.max(0, Math.min(STOPS - 1, next)));
  });
}

function sayAutonomy(text) {
  $("autMsg").textContent = text;
  clearTimeout(autMsgTimer);
  if (text) autMsgTimer = setTimeout(() => ($("autMsg").textContent = ""), 4000);
}

async function setAutonomy(level) {
  if (!status) return;
  if (status.agent?.observe_only) {
    sayAutonomy("Show me only for this session. You keep control.");
    return renderAutonomy();
  }
  if (level === status.autonomy && pendingAutonomy === null) return renderAutonomy();
  const busy = isBusy(status);
  const guiding = busy && status.current.mode !== "act" && !status.current.takeover;
  pendingAutonomy = level;
  renderAutonomy();
  const r = await api.agent("POST", "/autonomy", { level });
  pendingAutonomy = null;
  if (r.ok && r.data) {
    status = r.data;
    sayAutonomy(guiding && level === STOPS - 1 ? "I'm taking over this task now." : busy ? "Applied to the task in progress." : "");
  } else {
    sayAutonomy("The assistant did not answer: the setting is unchanged.");
  }
  renderAutonomy();
}

function renderAutonomy() {
  const readOnly = Boolean(status?.agent?.observe_only);
  if (readOnly) drag = null;
  const level = readOnly ? 0 : pendingAutonomy ?? (status && Number.isInteger(status.autonomy) ? status.autonomy : null);
  const shown = drag ? Math.round(drag.pos * (STOPS - 1)) : level; // the level the dot would land on
  const key = drag ? `d${drag.pos.toFixed(3)}` : String(level);
  if (key !== drawnKey) {
    const settled = !drag && drawnKey !== undefined;
    notchX = drawAutonomy($("magnetSvg"), shown, LABELS, { animate: settled, pos: drag ? drag.pos : null });
    drawnKey = key;
  }
  const box = $("magnet");
  box.classList.toggle("off", !status);
  box.classList.toggle("dragging", Boolean(drag));
  box.setAttribute("aria-disabled", String(!status || readOnly));
  if (readOnly) $("autMsg").textContent = "Show me only for this session. You keep control.";
  if (shown !== null) {
    box.setAttribute("aria-valuenow", String(shown));
    box.setAttribute("aria-valuetext", LABELS[shown]);
  }
}

// home: ready badge, running task, numbers -------------------------------------------------------
function renderHome() {
  renderStopControls();
  if (view !== "home") return;
  const busy = isBusy(status);
  $("offline").hidden = Boolean(status);
  $("hero").hidden = !status || busy;
  const b = readyBadge(status);
  $("voiceStatus").hidden = !status || !b.sub;
  $("voiceStatus").textContent = b.sub ? `${b.text} ${b.sub}` : "";
  if (status && !busy) {
    $("readyText").textContent = b.text;
    $("readyBadge").classList.toggle("pulse", b.pulse);
    paint($("readyBadge"), { seed: 11, dot: "on" });
  }
  $("now").hidden = !busy;
  $("stepReply").hidden = !busy || status.current.state !== "awaiting_user" || !status.current.step;
  $("stepDone").disabled = stepReplyPending;
  $("stepStuck").disabled = stepReplyPending;
  if (busy) {
    const c = status.current;
    $("nowProc").textContent = `${procedureName(c.procedure_id) || "Task"} · ${c.takeover || c.mode === "act" ? "I'm doing it" : "you do it, I guide"}`;
    $("nowGoal").textContent = c.goal || "";
    $("nowStep").textContent = taskLine(c);
    const steps = $("nowSteps");
    steps.replaceChildren();
    const total = c.step && c.step.total;
    if (total) {
      for (let i = 1; i <= total; i++) steps.append(el("span", i < c.step.index ? "done" : i === c.step.index ? "cur" : ""));
    }
  }
  renderAutonomy();
}

function renderStopControls() {
  const current = status?.current;
  const busy = isBusy(status);
  if (stopNotice && current && current.session_id !== stopNotice.session) stopNotice = null;
  const stopping = stopPending || (busy && current.state === "stopping");
  $("globalStopBar").hidden = !busy && !stopPending && !stopNotice;
  for (const id of ["stopBtn", "globalStopBtn"]) {
    $(id).disabled = !busy || stopping;
    $(id).textContent = stopping ? "Stopping…" : id === "stopBtn" ? "Stop" : "Stop task";
  }
  let message = stopNotice?.message || "Available from every tab. You remain in control.";
  if (busy && current.state === "stopping") message = "Stop requested. Waiting for the task to finish.";
  else if (stopNotice && current?.terminal && stopNotice.accepted) {
    message = current.state === "stopped" || current.status === "abandoned"
      ? "Task stopped." : "Task finished. Check its result in Activity.";
  }
  $("stopMessage").textContent = message;
}

async function stopTask() {
  if (stopPending || !isBusy(status) || status.current.state === "stopping") return;
  stopPending = true;
  const session = status.current.session_id;
  stopNotice = { session, message: "Sending Stop…", accepted: false };
  renderStopControls();
  try {
    const r = await api.agent("POST", "/stop");
    const accepted = r.ok && r.data?.stopped === true;
    stopNotice = { session, accepted, message: accepted
      ? "Stop requested. Waiting for the task to finish."
      : r.ok ? "No active task accepted Stop. Check the current status."
      : "Stop was not accepted. Check the connection and try again." };
  } catch {
    stopNotice = { session, accepted: false, message: "Stop could not be sent. Check the connection and try again." };
  } finally {
    stopPending = false;
    renderStopControls();
    await poll();
  }
}
$("stopBtn").addEventListener("click", stopTask);
$("globalStopBtn").addEventListener("click", stopTask);
async function reportStep(done) {
  const c = status?.current;
  if (stepReplyPending || !c || c.terminal || c.state !== "awaiting_user" || !c.step) return;
  const body = { session_id: c.session_id, step_index: c.step.index, done };
  stepReplyPending = true;
  $("stepReplyMessage").textContent = "";
  renderHome();
  try {
    const r = await api.agent("POST", "/next", body);
    if (!r.ok) $("stepReplyMessage").textContent = r.status === 409
      ? "L’étape a changé. Vérifie la consigne actuelle."
      : "Réponse non transmise. Réessaie dans un instant.";
  } finally {
    stepReplyPending = false;
    await poll();
  }
}
$("stepDone").addEventListener("click", () => reportStep(true));
$("stepStuck").addEventListener("click", () => reportStep(false));
$("copyCmd").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("cmdText").textContent);
    $("copyCmd").textContent = "Copied";
  } catch {
    $("copyCmd").textContent = "Select it";
  }
  setTimeout(() => ($("copyCmd").textContent = "Copy"), 1500);
});

async function loadStats() {
  const r = status ? await api.agent("GET", "/usage") : null;
  const m = r && r.ok && r.data ? r.data.month : null;
  $("stSessions").textContent = m ? String(m.sessions) : "—";
  $("stVerified").textContent = m ? (m.sessions ? `${m.verified} of ${m.sessions}` : "0") : "—";
  $("stTime").textContent = m ? duration(m.median_duration_s) : "—";
}

// activity: tasks + the user's ✓ / ✗ -------------------------------------------------------------
async function rate(s, value, row) {
  const next = s.useful === value ? null : value; // clicking the same mark again clears it
  const r = await api.agent("POST", "/rate", { id: s.id, useful: next });
  if (r.ok) {
    s.useful = next;
    paintRating(row, s);
  }
}

// The chosen mark gets circled in red pencil, like a teacher grading a paper.
function paintRating(row, s) {
  for (const [cls, value] of [["yes", true], ["no", false]]) {
    const b = row.querySelector(`.${cls}`);
    const on = s.useful === value;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", String(on));
  }
}

async function loadSessions() {
  const box = $("sessions");
  const r = status ? await api.agent("GET", "/sessions") : null;
  box.replaceChildren();
  const list = (r && r.ok && r.data && r.data.sessions) || [];
  if (!status) return box.append(el("div", "empty", "Start the assistant to see your tasks."));
  if (!list.length) return box.append(el("div", "empty", `No task yet. Hold ${keyLabel(status.voice && status.voice.ptt_key)} and ask for something.`));
  for (const s of list) {
    const row = el("div", "item");
    row.append(el("span", `chip ${s.status || ""}`, s.status === "resolved" && !s.verified ? "Done" : STATUS_LABEL[s.status] || s.status || "—"));
    const mid = el("div", "mid");
    const goal = el("div", "goal", s.goal || procedureName(s.procedure_id));
    if (s.simulated) goal.append(el("span", "sim", "SIM"));
    mid.append(goal);
    const bits = [when(s.started_at), s.mode === "guide" ? "you did it, guided" : "I did it", duration(s.duration_s)];
    if (s.blocked_on) bits.push(`blocked: ${s.blocked_on}`);
    mid.append(el("div", "meta", bits.filter(Boolean).join(" · ")));
    row.append(mid);
    const marks = el("div", "rating");
    const yes = el("button", "mark yes", "✓");
    const no = el("button", "mark no", "✗");
    for (const [b, seed] of [[yes, 3], [no, 9]]) {
      const ring = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      ring.setAttribute("class", "ring");
      paintRing(ring, 40, seed);
      b.append(ring);
    }
    yes.title = "It helped";
    no.title = "It did not help";
    yes.addEventListener("click", () => rate(s, true, row));
    no.addEventListener("click", () => rate(s, false, row));
    marks.append(yes, no);
    row.append(marks);
    paintRating(row, s);
    box.append(row);
  }
}
// voice -----------------------------------------------------------------------------------------
let speedTouched = 0;
let pttMsg = null; // feedback after a key change, kept for a few seconds

function renderVoice() {
  const sp = (status && status.speech) || null;
  const usable = Boolean(sp && sp.available);
  const localVoice = sp?.provider === "macos";
  const sw = $("ttsSwitch");
  sw.setAttribute("aria-checked", String(Boolean(sp && sp.enabled)));
  sw.disabled = !usable;
  const box = $("voices");
  if (!box.children.length) {
    for (const v of (status && status.voices) || VOICES) {
      const b = el("button", "voice");
      b.dataset.id = v.id;
      b.append(el("b", null, v.name), el("span", null, v.note));
      b.addEventListener("click", async () => {
        if (status?.speech?.provider === "macos") return;
        const r = await api.agent("POST", "/voice", { voice: v.id });
        if (r.ok) pref("voice", v.id);
        poll();
      });
      box.append(b);
    }
  }
  const configured = box.querySelector(".configured-voice");
  if (configured && configured.dataset.id !== sp?.voice) configured.remove();
  if (usable && !localVoice && sp.voice && !Array.from(box.querySelectorAll(".voice")).some((b) => b.dataset.id === sp.voice)) {
    const b = el("button", "voice configured-voice");
    b.dataset.id = sp.voice;
    b.append(el("b", null, "Configured voice"), el("span", null, "Current session"));
    // Informational: this voice is selected by the launcher, not a preset to overwrite.
    b.disabled = true;
    box.append(b);
  }
  box.querySelectorAll(".voice").forEach((b) => {
    b.classList.toggle("on", Boolean(sp && sp.voice === b.dataset.id));
    b.disabled = !usable || localVoice || b.classList.contains("configured-voice");
    b.title = localVoice ? "Ces voix ElevenLabs sont indisponibles en mode voix locale." : "";
  });
  if (sp && Date.now() - speedTouched > 2000) $("speed").value = String(sp.speed ?? 1);
  $("speed").disabled = !usable;
  $("speedVal").textContent = `${Number($("speed").value).toFixed(2)}×`;
  $("testVoice").disabled = !usable || !(sp && sp.enabled);
  $("ttsNote").textContent = !status
    ? "Start the assistant to set the voice."
    : usable
      ? localVoice
        ? `Voix locale macOS : ${sp.voice || "voix système"}. Le son, la vitesse et le test restent disponibles ; les voix ElevenLabs sont désactivées.`
        : "Voices by ElevenLabs. Sentences are prepared ahead, so the voice starts with the drawing."
      : "Voix indisponible. Vérifie la sortie audio et la configuration du moteur vocal.";

  const keys = $("pttKeys");
  if (!keys.children.length) {
    for (const k of ((status && status.ptt_keys) || KEYS).filter((k) => safePttPreference(k.key))) {
      const b = el("button", "keycap", k.label);
      b.dataset.key = k.key;
      b.setAttribute("role", "radio");
      b.addEventListener("click", async () => {
        const r = await api.agent("POST", "/ptt", { key: k.key });
        if (r.ok) pref("ptt", k.key);
        pttMsg = { text: r.ok ? `Now: hold ${k.label} and speak.` : (r.data && r.data.error) || "Could not change the key.", at: Date.now() };
        poll();
      });
      keys.append(b);
    }
  }
  const current = status && status.voice && status.voice.ptt_key;
  keys.querySelectorAll(".keycap").forEach((b) => {
    b.classList.toggle("on", b.dataset.key === current);
    b.setAttribute("aria-checked", String(b.dataset.key === current));
    b.disabled = !current;
  });
  $("pttNote").textContent =
    pttMsg && Date.now() - pttMsg.at < 4000
      ? pttMsg.text
      : !status
        ? "Start the assistant to change the key."
        : current
          ? "Applies right away. The badge on screen shows the new key."
          : "Push to talk runs with `hcs-agent talk`.";
}
$("ttsSwitch").addEventListener("click", async () => {
  const on = $("ttsSwitch").getAttribute("aria-checked") !== "true";
  $("ttsSwitch").setAttribute("aria-checked", String(on));
  pref("tts", on);
  await api.agent("POST", "/voice", { enabled: on });
  poll();
});
$("speed").addEventListener("input", () => {
  speedTouched = Date.now();
  $("speedVal").textContent = `${Number($("speed").value).toFixed(2)}×`;
});
$("speed").addEventListener("change", async () => {
  speedTouched = Date.now();
  pref("speed", $("speed").value);
  await api.agent("POST", "/voice", { speed: Number($("speed").value) });
});
$("testVoice").addEventListener("click", () => api.agent("POST", "/voice/test"));

// vision ----------------------------------------------------------------------------------------
async function loadVision(s) {
  const v = s || (await api.vision.status());
  $("visionState").textContent = v.running ? "Calibrating" : v.available ? "Ready" : "Not installed";
  $("visionState").className = `badge${v.running ? " on" : ""}`;
  $("visionBtn").textContent = v.running ? "Close" : "Recalibrate";
  $("visionBtn").disabled = !v.available;
  $("visionNote").textContent =
    v.reason || (v.running ? "Follow the targets on screen; it closes with this app." : "Opens the calibration screen.");
  $("visionBtn").onclick = async () => loadVision(v.running ? await api.vision.stop() : await api.vision.start());
}

// polling ---------------------------------------------------------------------------------------
async function poll() {
  const r = await api.agent("GET", "/status");
  const was = status;
  status = r.ok ? r.data : null;
  if (status && !was) await syncPrefs();
  renderHome();
  if (view === "voice") renderVoice();
  // A task just ended (or the assistant came up): refresh the numbers and the list.
  const key = status && status.current ? `${status.current.session_id}:${status.current.terminal}` : String(Boolean(status));
  if (key !== lastSessionKey || Boolean(was) !== Boolean(status)) {
    lastSessionKey = key;
    loadStats();
    if (view === "activity") loadSessions();
  }
}

buildAutonomy();
window.addEventListener("resize", () => renderHome());
go(["home", "activity", "voice", "vision"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "home");
poll();
setInterval(poll, 1000);
