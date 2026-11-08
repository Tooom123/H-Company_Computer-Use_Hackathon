// H Companion app — renderer. Polls the agent once a second (that poll is also the app's heartbeat:
// while it lasts, the on-screen Magnet stays hidden and the setting lives here).
import { drawMagnet } from "./magnet.js";
import { STATUS_LABEL, duration, headline, isBusy, keyLabel, procedureName, when } from "./view.js";

const $ = (id) => document.getElementById(id);
const api = window.hcs;
const LABELS = ["Show me", "Help if I'm stuck", "Do it, I watch"];
const HINTS = [
  "I point at each control and explain. You click; I never take the controls.",
  "I guide you. If you are stuck twice on a step, or ask me, I finish it myself and narrate.",
  "I do the task in front of you and annotate every action. Stop at any time.",
];
const VOICES = [
  { id: "EXAVITQu4vr4xnSDxMaL", name: "Sarah", note: "warm, reassuring" },
  { id: "cgSgspJ2msm6clMCkdW9", name: "Jessica", note: "bright, playful" },
  { id: "hpp4J3VqNfWAUOO0d1Us", name: "Bella", note: "professional, warm" },
  { id: "XrExE9yKIg1WjnnlVkGX", name: "Matilda", note: "upbeat, knowledgeable" },
];
const KEYS = [
  { key: "cmd+h", label: "⌘H" },
  { key: "cmd+j", label: "⌘J" },
  { key: "alt_r", label: "Right ⌥" },
  { key: "f9", label: "F9" },
];

let status = null; // last /status, null = agent not running
let lastSessionKey = "";
let view = "home";
let pendingAutonomy = null; // optimistic value while the POST is in flight
let drawnLevel; // what the Magnet shows now (redraw only on change, with the pencil animation)

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

// Preferences the user chose in the app; pushed again to the assistant when it (re)starts.
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
    if (voice && voice !== sp.voice) want.voice = voice;
    if (speed && Number(speed) !== sp.speed) want.speed = Number(speed);
    if (enabled !== null && (enabled === "true") !== sp.enabled) want.enabled = enabled === "true";
    if (Object.keys(want).length) await api.agent("POST", "/voice", want);
  }
  const key = pref("ptt");
  if (key && status.voice && status.voice.ptt_key && key !== status.voice.ptt_key) {
    await api.agent("POST", "/ptt", { key });
  }
}

// navigation ------------------------------------------------------------------------------------
function go(name) {
  view = name;
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b.dataset.go === name));
  if (name === "activity") loadSessions();
  if (name === "voice") renderVoice();
  if (name === "vision") loadVision();
}
document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));

// home: autonomy (the Magnet) ----------------------------------------------------------------------
function buildMagnetHits() {
  const hit = $("magnetHit");
  LABELS.forEach((label, i) => {
    const b = el("button", "hit");
    b.setAttribute("role", "radio");
    b.setAttribute("aria-label", label);
    b.addEventListener("click", () => setAutonomy(i));
    hit.append(b);
  });
}

async function setAutonomy(level) {
  if (!status) return;
  pendingAutonomy = level;
  renderAutonomy();
  const r = await api.agent("POST", "/autonomy", { level });
  pendingAutonomy = null;
  if (r.ok && r.data) status = r.data;
  renderAutonomy();
}

function renderAutonomy() {
  const level = pendingAutonomy ?? (status ? status.autonomy : null);
  if (level !== drawnLevel) {
    const xs = drawMagnet($("magnetSvg"), level, LABELS, { animate: drawnLevel !== undefined });
    drawnLevel = level;
    $("magnetHit").querySelectorAll(".hit").forEach((b, i) => {
      b.style.left = `${xs[i] * 100}%`;
      b.setAttribute("aria-checked", String(i === level));
    });
  }
  $("magnetHit").querySelectorAll(".hit").forEach((b) => (b.disabled = !status));
  $("magnet").classList.toggle("off", !status);
  $("autHint").textContent = level === null ? "Start the assistant to choose." : HINTS[level];
}

// home: status, task, numbers ----------------------------------------------------------------------
function renderHome() {
  const h = headline(status);
  $("pill").className = `pill ${h.tone}${h.pulse ? " pulse" : ""}`;
  $("pillText").textContent = h.text;
  $("pillSub").textContent = h.sub;
  $("offline").hidden = Boolean(status);

  const busy = isBusy(status);
  $("now").hidden = !busy;
  if (busy) {
    const c = status.current;
    $("nowProc").textContent = `${procedureName(c.procedure_id)} · ${c.takeover || c.mode === "act" ? "I'm doing it" : "guiding you"}`;
    $("nowGoal").textContent = c.goal || "";
    $("stopBtn").disabled = c.state === "stopping";
    const steps = $("nowSteps");
    steps.replaceChildren();
    const total = c.step && c.step.total;
    if (total) {
      for (let i = 1; i <= total; i++) steps.append(el("span", i < c.step.index ? "done" : i === c.step.index ? "cur" : ""));
    }
  }
  renderAutonomy();
  const said = status && status.voice && status.voice.last_text;
  $("said").textContent = said ? `Last request: “${said}”` : "";
}

$("stopBtn").addEventListener("click", async () => {
  $("stopBtn").disabled = true;
  await api.agent("POST", "/stop");
  poll();
});
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

// activity --------------------------------------------------------------------------------------
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
    const mid = el("div");
    const goal = el("div", "goal", s.goal || procedureName(s.procedure_id));
    if (s.simulated) goal.append(el("span", "sim", "SIM"));
    mid.append(goal);
    const bits = [when(s.started_at), s.mode === "guide" ? "you did it, guided" : "I did it", duration(s.duration_s)];
    if (s.blocked_on) bits.push(`blocked: ${s.blocked_on}`);
    mid.append(el("div", "meta", bits.filter(Boolean).join(" · ")));
    row.append(mid);
    box.append(row);
  }
}

// voice -----------------------------------------------------------------------------------------
let speedTouched = 0;
let pttMsg = null; // feedback after a key change, kept for a few seconds

function renderVoice() {
  const sp = (status && status.speech) || null;
  const usable = Boolean(sp && sp.available);
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
        pref("voice", v.id);
        await api.agent("POST", "/voice", { voice: v.id });
        poll();
      });
      box.append(b);
    }
  }
  box.querySelectorAll(".voice").forEach((b) => {
    b.classList.toggle("on", Boolean(sp && sp.voice === b.dataset.id));
    b.disabled = !usable;
  });
  if (sp && Date.now() - speedTouched > 2000) $("speed").value = String(sp.speed ?? 1);
  $("speed").disabled = !usable;
  $("speedVal").textContent = `${Number($("speed").value).toFixed(2)}×`;
  $("testVoice").disabled = !usable || !(sp && sp.enabled);
  $("ttsNote").textContent = !status
    ? "Start the assistant to set the voice."
    : usable
      ? "Voices by ElevenLabs. Sentences are prepared ahead, so the voice starts with the drawing."
      : "Voice unavailable: add the ElevenLabs key (ELEVEN in backend/.env), then restart the assistant.";

  const keys = $("pttKeys");
  if (!keys.children.length) {
    for (const k of (status && status.ptt_keys) || KEYS) {
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
  $("visionState").textContent = v.running ? "Lab open" : v.available ? "Not running" : "Not installed";
  $("visionState").className = `badge${v.running ? " on" : ""}`;
  $("visionBtn").textContent = v.running ? "Close the lab" : "Recalibrate";
  $("visionBtn").disabled = !v.available;
  $("visionNote").textContent =
    v.reason || (v.running ? "Follow the targets on screen; the lab closes with this app." : "Opens Édouard's Vision Lab on the calibration screen.");
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

buildMagnetHits();
go(["home", "activity", "voice", "vision"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "home");
poll();
setInterval(poll, 1000);
