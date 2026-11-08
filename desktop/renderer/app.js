// H Companion app — renderer. Polls the agent once a second (that poll is also the app's heartbeat:
// while it lasts, the on-screen Magnet stays hidden and the setting lives here).
import { PLANS, STATUS_LABEL, duration, headline, isBusy, keyLabel, money, planMeter, procedureName, ratio, when } from "./view.js";

const $ = (id) => document.getElementById(id);
const api = window.hcs;
const LABELS = ["Show me", "Help if I'm stuck", "Do it, I watch"];
const HINTS = [
  "I point at each control and explain. You click; I never take the controls.",
  "I guide you. If you are stuck twice on a step, or ask me, I finish it myself and narrate.",
  "I do the task in front of you and annotate every action. Stop at any time.",
];

let status = null; // last /status, null = agent not running
let lastSessionKey = "";
let view = "home";
let pendingAutonomy = null; // optimistic value while the POST is in flight
let feedback = null;
let feedbackBusy = false;
let feedbackCommentDirty = false;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch {
    return null;
  }
  return value;
}

// navigation ------------------------------------------------------------------------------------
function go(name) {
  view = name;
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b.dataset.go === name));
  if (name === "activity") loadSessions();
  if (name === "usage") loadUsage();
  if (name === "vision") loadVision();
  if (name === "feedback") loadFeedback();
}
document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));

// home ------------------------------------------------------------------------------------------
const ROUGH = [
  "M17 4 C 7 3, 2 10, 4 18 C 6 26, 16 30, 25 27 C 33 24, 35 14, 30 8 C 27 4, 22 3, 15 5",
  "M16 3 C 6 4, 1 12, 5 20 C 9 28, 20 30, 28 25 C 34 20, 34 10, 27 5 C 23 2, 18 2, 13 4",
  "M18 5 C 8 2, 1 9, 3 17 C 5 25, 14 30, 24 28 C 33 26, 36 16, 31 9 C 28 5, 23 3, 16 4",
];
function buildRail() {
  const rail = $("rail");
  LABELS.forEach((label, i) => {
    const b = el("button", "notch");
    b.setAttribute("role", "radio");
    b.dataset.level = String(i);
    b.append(el("b", null, label));
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 34 32");
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", ROUGH[i]);
    svg.append(p);
    b.append(svg);
    b.addEventListener("click", () => setAutonomy(i));
    rail.append(b);
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
  document.querySelectorAll(".notch").forEach((b) => {
    const on = Number(b.dataset.level) === level;
    b.classList.toggle("on", on);
    b.setAttribute("aria-checked", String(on));
    b.querySelector("svg").style.visibility = on ? "visible" : "hidden";
    b.disabled = !status || Boolean(status.agent?.observe_only && Number(b.dataset.level) > 0);
  });
  $("autHint").textContent = level === null ? "Start the agent to choose." : HINTS[level];
}

function renderHome() {
  const h = headline(status);
  const pill = $("pill");
  pill.className = `pill ${h.tone}${h.pulse ? " pulse" : ""}`;
  $("pillText").textContent = h.text;
  $("pillSub").textContent = h.sub;
  $("offline").hidden = Boolean(status);

  const busy = isBusy(status);
  $("now").hidden = !busy;
  if (busy) {
    const c = status.current;
    $("nowProc").textContent = `${procedureName(c.procedure_id)} · ${c.takeover ? "agent acting" : c.mode === "act" ? "agent acting" : "guiding you"}`;
    $("nowGoal").textContent = c.goal || "";
    $("stopBtn").disabled = c.state === "stopping";
    const steps = $("nowSteps");
    steps.replaceChildren();
    const total = c.step && c.step.total;
    if (total) {
      for (let i = 1; i <= total; i++) {
        steps.append(el("span", i < c.step.index ? "done" : i === c.step.index ? "cur" : ""));
      }
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

// sidebar agent line ----------------------------------------------------------------------------
function renderAgentLine() {
  $("agentDot").className = status ? "on" : "";
  if (!status) {
    $("agentLine").textContent = "Agent offline";
    return;
  }
  const a = status.agent || {};
  $("agentLine").textContent = `Agent ${a.command || "running"}${a.simulated ? " · simulated" : ""}`;
}

// activity --------------------------------------------------------------------------------------
async function loadSessions() {
  const box = $("sessions");
  const r = status ? await api.agent("GET", "/sessions") : null;
  box.replaceChildren();
  const list = (r && r.ok && r.data && r.data.sessions) || [];
  if (!status) return box.append(el("div", "empty", "Start the agent to see your sessions."));
  if (!list.length) return box.append(el("div", "empty", "No session yet. Hold ⌘H and ask for something."));
  for (const s of list) {
    const row = el("div", "item");
    row.append(el("span", `chip ${s.status || ""}`, s.status === "resolved" && !s.verified ? "Done" : STATUS_LABEL[s.status] || s.status || "—"));
    const mid = el("div");
    const goal = el("div", "goal", s.goal || procedureName(s.procedure_id));
    if (s.simulated) goal.append(el("span", "sim", "SIM"));
    mid.append(goal);
    const bits = [when(s.started_at), s.mode === "guide" ? "guided" : "agent acted", duration(s.duration_s)];
    if (!s.simulated) bits.push(money(s.cost_usd));
    if (s.blocked_on) bits.push(`blocked: ${s.blocked_on}`);
    mid.append(el("div", "meta", bits.filter(Boolean).join(" · ")));
    row.append(mid);
    if (s.case_id) {
      const open = el("button", "link", "Case ↗");
      open.addEventListener("click", () => api.openCase(s.case_id));
      row.append(open);
    } else row.append(el("span"));
    box.append(row);
  }
}
$("openDash").addEventListener("click", () => api.openDashboard());

// Human feedback: dictation is explicitly armed, never routed as a task.
function renderFeedback() {
  const usable = Boolean(feedback?.available && !feedback?.saved);
  const locked = !usable || feedbackBusy;
  $("feedbackHome").hidden = !usable;
  $("feedbackSession").textContent = feedback?.session_id
    ? `Essai ${feedback.session_id}${feedback.saved ? " · retour enregistré" : ""}`
    : "Termine un essai pour donner ton retour.";
  $("feedbackHint").textContent = feedback?.dictation_armed
    ? `Maintiens ${keyLabel(status?.voice?.ptt_key)}, dicte ton retour, puis relâche. Cette dictée ne lance pas une nouvelle tâche.`
    : "Tu peux dicter ou écrire ton retour. Relis-le avant de l’enregistrer.";
  $("feedbackDictate").disabled = locked || Boolean(feedback?.dictation_armed);
  $("feedbackComment").disabled = locked || Boolean(feedback?.dictation_armed);
  $("feedbackSuccess").disabled = locked;
  $("feedbackUseful").disabled = locked;
  $("feedbackSave").disabled = locked || Boolean(feedback?.dictation_armed)
    || !$("feedbackSuccess").value || !$("feedbackUseful").value;
}

async function loadFeedback() {
  if (!status || feedbackBusy) return;
  const r = await api.agent("GET", "/feedback");
  if (!r.ok || !r.data) { feedback = null; renderFeedback(); return; }
  const previous = feedback;
  feedback = r.data;
  if (previous?.session_id !== feedback.session_id) {
    feedbackCommentDirty = false;
    $("feedbackSuccess").value = "";
    $("feedbackUseful").value = "";
    $("feedbackMessage").textContent = "";
  }
  const dictated = previous?.dictation_armed && !feedback.dictation_armed;
  if (!feedbackCommentDirty || dictated) {
    $("feedbackComment").value = feedback.comment || "";
    feedbackCommentDirty = false;
  }
  renderFeedback();
}

$("feedbackHome").addEventListener("click", () => go("feedback"));
$("feedbackComment").addEventListener("input", () => { feedbackCommentDirty = true; });
for (const id of ["feedbackSuccess", "feedbackUseful"]) $(id).addEventListener("change", renderFeedback);
$("feedbackDictate").addEventListener("click", async () => {
  if (!feedback?.session_id || feedbackBusy) return;
  feedbackBusy = true; renderFeedback();
  try {
    const r = await api.agent("POST", "/feedback/dictate", { session_id: feedback.session_id });
    if (r.ok && r.data) feedback = r.data;
    $("feedbackMessage").textContent = r.ok ? "Dictée prête." : (r.data?.error || "Impossible de préparer la dictée.");
  } finally { feedbackBusy = false; renderFeedback(); }
});
$("feedbackSave").addEventListener("click", async () => {
  if (!feedback?.session_id || feedbackBusy || $("feedbackSave").disabled) return;
  feedbackBusy = true; renderFeedback();
  try {
    const r = await api.agent("POST", "/feedback", {
      session_id: feedback.session_id, success: $("feedbackSuccess").value,
      useful: $("feedbackUseful").value, comment: $("feedbackComment").value,
      confirmed_by_human: true, allow_screenshots_to_support: false, training_consent: false,
    });
    if (r.ok) {
      feedback = { ...feedback, saved: true };
      $("feedbackMessage").textContent = "Retour enregistré pour cet essai. Tu peux poser ta prochaine question.";
    } else $("feedbackMessage").textContent = r.data?.error || "Le retour n’a pas été enregistré. Réessaie.";
  } finally { feedbackBusy = false; renderFeedback(); }
});

// usage & plan ----------------------------------------------------------------------------------
let usage = null;
let plan = store("plan") || "starter";

function renderPlan() {
  const seg = $("planSeg");
  seg.replaceChildren();
  for (const [id, p] of Object.entries(PLANS)) {
    const b = el("button", id === plan ? "on" : "", p.name);
    b.addEventListener("click", () => {
      plan = store("plan", id) || id;
      renderPlan();
    });
    seg.append(b);
  }
  const m = planMeter(plan, usage && usage.month);
  $("planUsed").textContent = m.limit ? `${m.used} / ${m.limit}` : String(m.used);
  $("planUnit").textContent = m.limit ? m.unit : `sessions this month · ${m.unit}`;
  $("planBar").style.width = `${Math.round((m.ratio ?? 0) * 100)}%`;
  $("planBar").parentElement.classList.toggle("high", (m.ratio ?? 0) >= 0.8);

  const plans = $("plans");
  plans.replaceChildren();
  for (const [id, p] of Object.entries(PLANS)) {
    const card = el("div", `plan${id === plan ? " cur" : ""}`);
    card.append(el("b", null, p.name));
    const price = el("div", "price");
    price.append(el("b", null, p.price), el("span", null, p.per));
    card.append(price, el("span", "muted small", p.unit));
    if (id !== "starter" && id !== plan) {
      const b = el("button", "btn", id === "pro" ? "Upgrade" : "Buy");
      b.addEventListener("click", async () => {
        b.disabled = true;
        $("planMsg").textContent = "Opening Stripe…";
        const r = await api.checkout(id);
        $("planMsg").textContent = r.ok ? "Finish in your browser (Stripe test mode, no real charge)." : r.error;
        b.disabled = false;
      });
      card.append(b);
    } else if (id === plan) card.append(el("span", "hand small", "your plan ✓"));
    plans.append(card);
  }
}

function provider(name, tag, big, line, meterRatio) {
  const c = el("div", "card prov");
  const h = el("h2", null, name);
  h.append(el("span", null, tag));
  c.append(h, el("div", "big", big));
  if (meterRatio !== null && meterRatio !== undefined) {
    const m = el("div", `meter${meterRatio >= 0.8 ? " high" : ""}`);
    const bar = el("span");
    bar.style.width = `${Math.round(meterRatio * 100)}%`;
    m.append(bar);
    c.append(m);
  }
  c.append(el("p", "muted small", line));
  return c;
}

function renderProviders() {
  const box = $("providers");
  box.replaceChildren();
  if (!usage) {
    box.append(el("div", "card muted", status ? "Loading…" : "Start the agent to see usage and costs."));
    return;
  }
  const m = usage.month;
  const q = usage.h_quota;
  box.append(
    provider("H Company", "computer use", money(m.h_spend_usd),
      `${m.h_cost_per_session_usd !== null ? `${money(m.h_cost_per_session_usd)} per session` : "No paid session yet"}` +
        (q ? ` · ${q.active ?? "?"} of ${q.limit ?? "?"} live sessions in use` : " · quota unknown"),
      null),
  );
  const e = usage.elevenlabs;
  box.append(
    status?.speech?.provider === "macos"
      ? provider("Voix macOS", "voix locale", status.speech.voice || "Système",
          "La voix est produite sur ce Mac, sans appel ElevenLabs.", null)
      : e
      ? provider("ElevenLabs", "voice", `${(e.characters_used ?? 0).toLocaleString()} chars`,
          `of ${(e.characters_limit ?? 0).toLocaleString()} on ${e.tier || "your"} plan` +
            (e.resets_at ? ` · resets ${new Date(e.resets_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}` : ""),
          ratio(e.characters_used ?? 0, e.characters_limit))
      : provider("ElevenLabs", "voice", "—", "No key or offline: the notes stay silent.", null),
  );
  const conf = usage.configured || {};
  box.append(
    provider("Gladia", "speech to text", conf.gladia ? "Connected" : "No key",
      "Usage is not reported to the app yet: see app.gladia.io.", null),
    provider("Linkup", "web lookups", conf.linkup ? "Connected" : "Off",
      conf.linkup ? "Usage is not reported to the app yet: see app.linkup.so." : "Optional: documents blockers from the vendor's docs.", null),
  );
}

async function loadUsage() {
  if (status) {
    const r = await api.agent("GET", "/usage");
    usage = r.ok ? r.data : usage;
  } else usage = null;
  $("usageMonth").textContent = usage ? new Date(`${usage.month.month}-01T12:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : "";
  $("simNote").textContent = usage && usage.month.simulated
    ? `${usage.month.simulated} simulated session(s) this month are not counted.`
    : "Only real sessions count; simulated ones never do.";
  renderPlan();
  renderProviders();
  renderStats();
}

function renderStats() {
  const m = usage && usage.month;
  $("stSessions").textContent = m ? String(m.sessions) : "—";
  $("stVerified").textContent = m ? (m.sessions ? `${m.verified} / ${m.sessions}` : "0") : "—";
  $("stSpend").textContent = m ? money(m.h_spend_usd) : "—";
}

// voice -----------------------------------------------------------------------------------------
const VOICES = [
  { id: "EXAVITQu4vr4xnSDxMaL", name: "Sarah", note: "warm, reassuring" },
  { id: "cgSgspJ2msm6clMCkdW9", name: "Jessica", note: "bright, playful" },
  { id: "pFZP5JQG7iQjIQuC4Bku", name: "Lily", note: "velvety, British" },
  { id: "Xb7hH8MSUJpSbSDYk0k2", name: "Alice", note: "clear, British" },
];
let speedTouched = 0;

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
        await api.agent("POST", "/voice", { voice: v.id });
        poll();
      });
      box.append(b);
    }
  }
  box.querySelectorAll(".voice").forEach((b) => {
    b.classList.toggle("on", Boolean(sp && sp.voice === b.dataset.id));
    b.disabled = !usable || localVoice;
    b.title = localVoice ? "Ces voix ElevenLabs sont indisponibles en mode voix locale." : "";
  });
  if (sp && Date.now() - speedTouched > 2000) $("speed").value = String(sp.speed ?? 1);
  $("speed").disabled = !usable;
  $("speedVal").textContent = `${Number($("speed").value).toFixed(2)}×`;
  $("testVoice").disabled = !usable || !(sp && sp.enabled);
  $("ttsNote").textContent = !status
    ? "Start the agent to set the voice."
    : usable
      ? localVoice
        ? `Voix locale macOS : ${sp.voice || "voix système"}. Le son, la vitesse et le test restent disponibles ; les voix ElevenLabs sont désactivées.`
        : "Voices by ElevenLabs. Sentences are prepared ahead, so the voice starts with the drawing."
      : "Voix indisponible. Vérifie la sortie audio et la configuration du moteur vocal.";
  $("pttKey").textContent = keyLabel(status && status.voice && status.voice.ptt_key);
}
$("ttsSwitch").addEventListener("click", async () => {
  const on = $("ttsSwitch").getAttribute("aria-checked") !== "true";
  $("ttsSwitch").setAttribute("aria-checked", String(on));
  await api.agent("POST", "/voice", { enabled: on });
  poll();
});
$("speed").addEventListener("input", () => {
  speedTouched = Date.now();
  $("speedVal").textContent = `${Number($("speed").value).toFixed(2)}×`;
});
$("speed").addEventListener("change", async () => {
  speedTouched = Date.now();
  await api.agent("POST", "/voice", { speed: Number($("speed").value) });
});
$("testVoice").addEventListener("click", () => api.agent("POST", "/voice/test"));

// vision ----------------------------------------------------------------------------------------
async function loadVision(s) {
  const v = s || (await api.vision.status());
  $("visionState").textContent = v.running ? "Running" : v.available ? "Not running" : "Not installed";
  $("visionState").className = `badge${v.running ? " on" : ""}`;
  $("visionBtn").textContent = v.running ? "Close the Vision Lab" : "Open the Vision Lab";
  $("visionBtn").disabled = !v.available;
  $("visionNote").textContent = v.reason || (v.running ? "The lab opens in its own windows (calibration first)." : "Starts Édouard's lab from app/ (first start builds the capture helper).");
  $("visionBtn").onclick = async () => loadVision(v.running ? await api.vision.stop() : await api.vision.start());
}

// polling ---------------------------------------------------------------------------------------
async function poll() {
  const r = await api.agent("GET", "/status");
  const was = status;
  status = r.ok ? r.data : null;
  renderAgentLine();
  renderHome();
  await loadFeedback();
  if (view === "voice") renderVoice();
  if (view === "usage" && was?.speech?.provider !== status?.speech?.provider) renderProviders();
  // A task just ended (or the agent came up): refresh the numbers and the list.
  const key = status && status.current ? `${status.current.session_id}:${status.current.terminal}` : String(Boolean(status));
  if (key !== lastSessionKey || Boolean(was) !== Boolean(status)) {
    lastSessionKey = key;
    loadUsage();
    if (view === "activity") loadSessions();
  }
}

buildRail();
go(["home", "activity", "feedback", "usage", "voice", "vision"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "home");
document.querySelector('nav button[data-go="voice"]').addEventListener("click", renderVoice);
poll();
setInterval(poll, 1000);
setInterval(() => status && loadUsage(), 30000);
