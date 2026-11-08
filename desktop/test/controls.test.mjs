import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";
import * as formatting from "../renderer/view.js";

// A small DOM double executes the real renderer without Electron, network, or a running agent.
class Element {
  constructor(tag = "div") { this.tag = tag; this.children = []; this.dataset = {}; this.events = {}; this.attrs = {}; this.value = ""; this.className = ""; this.offsetWidth = 0; this.offsetHeight = 0; this.style = {}; }
  get classList() { return { add: (c) => this.className += ` ${c}`, contains: (c) => this.className.split(" ").includes(c), toggle: (c, on) => { this.className = this.className.split(" ").filter((x) => x !== c).concat(on ? [c] : []).join(" "); } }; }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  append(...els) { for (const e of els) { e.parent = this; this.children.push(e); } }
  replaceChildren(...els) { this.children = []; this.append(...els); }
  remove() { this.parent.children = this.parent.children.filter((e) => e !== this); }
  addEventListener(k, f) { this.events[k] = f; }
  querySelectorAll(q) { return this.children.flatMap((e) => [(q.startsWith(".") ? e.classList.contains(q.slice(1)) : e.tag === q) ? e : null, ...e.querySelectorAll(q)]).filter(Boolean); }
  querySelector(q) { return this.querySelectorAll(q)[0] || null; }
  getBoundingClientRect() { return { left: 0, width: 500 }; }
  focus() {}
  setPointerCapture() {}
}
const settled = () => new Promise((r) => setImmediate(r));
async function renderer({ current = null, observeOnly = true, preferences = {}, voice = "configured-custom-voice", stopResponse, voiceAvailable = true, voiceRejected = false } = {}) {
  const html = await readFile(new URL("../renderer/index.html", import.meta.url), "utf8");
  const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map((m) => [m[1], new Element()]));
  for (const [id, e] of ids) e.id = id;
  const tabs = [...html.matchAll(/class="tab" data-go="([^"]+)"/g)].map((m) => { const e = new Element("button"); e.dataset.go = m[1]; return e; });
  const calls = [];
  const status = { current, autonomy: 0, agent: { observe_only: observeOnly }, voice: { ptt_key: "ctrl+shift+h" }, speech: { available: voiceAvailable, enabled: voiceAvailable, response_mode: voiceAvailable ? "both" : "text", provider: "elevenlabs", voice, speed: 1 } };
  const feedback = { available: true, saved: false, session_id: "episode-7", comment: "", dictation_armed: false };
  const agent = async (method, path, body) => {
    calls.push({ method, path, body });
    if (path === "/autonomy" && !observeOnly) {
      status.autonomy = body.level;
      return { ok: true, status: 200, data: status };
    }
    if (path === "/stop" && stopResponse) return await stopResponse(status);
    if (path === "/voice" && method === "POST") {
      if (voiceRejected) return { ok: false, status: 503, data: { error: "Assistant unavailable" } };
      if (body.response_mode) {
        status.speech.response_mode = body.response_mode;
        status.speech.enabled = body.response_mode !== "text";
      }
      return { ok: true, status: 200, data: { ...status.speech } };
    }
    const data = path === "/status" ? status : path === "/feedback" ? feedback : path === "/sessions" ? { sessions: [] } : {};
    return { ok: true, status: 200, data };
  };
  const context = vm.createContext({
    ...formatting, drawAutonomy: () => [0.17, 0.5, 0.83], paintBadge() {}, paintRing() {},
    window: { hcs: { agent, platform: "darwin", window: { onState() {} }, vision: { status: async () => ({ available: false }) } }, addEventListener() {} },
    document: { body: new Element(), getElementById: (id) => ids.get(id) || null, createElement: (tag) => new Element(tag), createElementNS: (_ns, tag) => new Element(tag), querySelectorAll: (q) => q === ".tab" ? tabs : q === ".view" ? [...ids.values()].filter((e) => e.id.startsWith("view-")) : [] },
    localStorage: { getItem: (key) => preferences[key] ?? null, setItem: (key, value) => { preferences[key] = value; } },
    location: { hash: "#home" }, navigator: {}, requestAnimationFrame: (f) => f(), setInterval() {}, setTimeout() {}, clearTimeout() {},
  });
  const code = (await readFile(new URL("../renderer/app.js", import.meta.url), "utf8")).replace(/^import .*;\n/gm, "");
  vm.runInContext(code, context);
  await settled();
  return { ids, calls, context, status, feedback, preferences };
}

test("new desktop preserves configured voice and ignores stale Cmd-H preference", async () => {
  const r = await renderer({ preferences: { "hcs.voice": "EXAVITQu4vr4xnSDxMaL", "hcs.ptt": "cmd+h" } });
  assert.ok(!r.calls.some((c) => c.method === "POST"));
  vm.runInContext('go("voice")', r.context);
  assert.equal(r.ids.get("voices").querySelector(".configured-voice").children[0].textContent, "Configured voice");
  assert.ok(r.ids.get("pttKeys").children.some((b) => b.dataset.key === "ctrl+shift+h"));
  assert.ok(!r.ids.get("pttKeys").children.some((b) => b.dataset.key === "cmd+h"));
});

test("response selector applies and remembers Text, Voice and Both without changing autonomy", async () => {
  const r = await renderer();
  vm.runInContext('go("voice")', r.context);
  const buttons = r.ids.get("responseModes").children;
  for (const mode of ["text", "voice", "both"]) {
    await buttons.find(b => b.dataset.mode === mode).events.click();
    assert.equal(r.status.speech.response_mode, mode);
    assert.equal(r.preferences["hcs.responseMode"], mode);
    assert.equal(buttons.filter(b => b.attrs["aria-pressed"] === "true").length, 1);
    assert.equal(buttons.find(b => b.dataset.mode === mode).attrs["aria-pressed"], "true");
  }
  assert.ok(!r.calls.some(c => c.path === "/autonomy"));
  const restarted = await renderer({ preferences: { "hcs.responseMode": "voice", "hcs.tts": "false" } });
  assert.equal(restarted.status.speech.response_mode, "voice"); // new choice wins over legacy mute
  const legacy = await renderer({ preferences: { "hcs.tts": "false" } });
  assert.equal(legacy.status.speech.response_mode, "text");
});

test("response selector preserves the previous choice on failure and retains text without audio", async () => {
  const r = await renderer({ voiceRejected: true });
  vm.runInContext('go("voice")', r.context);
  await r.ids.get("responseModes").children[0].events.click();
  assert.equal(r.preferences["hcs.responseMode"], undefined);
  assert.equal(r.status.speech.response_mode, "both");
  assert.equal(r.ids.get("responseModeNote").textContent, "Assistant unavailable");
  const silent = await renderer({ voiceAvailable: false, preferences: { "hcs.responseMode": "voice" } });
  vm.runInContext('go("voice")', silent.context);
  assert.equal(silent.status.speech.response_mode, "text");
  assert.ok(!silent.calls.some(c => c.method === "POST"));
  assert.deepEqual(silent.ids.get("responseModes").children.map(b => b.disabled), [false, true, true]);
});

test("observe-only refuses slider keyboard and direct selection without posting autonomy", async () => {
  const r = await renderer();
  r.ids.get("magnet").events.keydown({ key: "End", preventDefault() {} });
  await vm.runInContext("setAutonomy(2)", r.context);
  assert.ok(!r.calls.some((c) => c.path === "/autonomy"));
  assert.equal(r.ids.get("magnet").attrs["aria-valuenow"], "0");
  assert.equal(r.ids.get("magnet").attrs["aria-disabled"], "true");
});

test("demo slider accepts drag and keyboard, while automatic context stays visible", async () => {
  const r = await renderer({ observeOnly: false });
  const magnet = r.ids.get("magnet");
  assert.equal(magnet.attrs["aria-disabled"], "false");
  magnet.events.pointerdown({ button: 0, pointerId: 1, clientX: 420 });
  magnet.events.pointerup();
  await settled();
  assert.equal(r.status.autonomy, 2);
  magnet.events.keydown({ key: "Home", preventDefault() {} });
  await settled();
  assert.equal(r.status.autonomy, 0);
  assert.deepEqual(r.calls.filter(c => c.path === "/autonomy").map(c => c.body.level), [2, 0]);
  r.status.context = { mode: "automatic", software: "odoo", label: "Odoo", sources: 3 };
  vm.runInContext("renderHome()", r.context);
  assert.equal(r.ids.get("contextStatus").hidden, false);
  assert.match(r.ids.get("contextStatus").textContent, /Odoo.*3 documentation excerpts/);
});

test("step fallback sends the exact displayed session, step and human answer", async () => {
  const current = { session_id: "live-123", terminal: false, state: "awaiting_user", mode: "guide", step: { index: 4, instruction: "Read the result" } };
  const r = await renderer({ current });
  assert.equal(r.ids.get("stepReply").hidden, false);
  await r.ids.get("stepStuck").events.click();
  const sent = r.calls.find((c) => c.path === "/next");
  assert.deepEqual(JSON.parse(JSON.stringify(sent.body)), { session_id: "live-123", step_index: 4, done: false });
  r.status.current = { ...current, state: "running" };
  const before = r.calls.length;
  await r.ids.get("stepDone").events.click();
  assert.equal(r.calls.length, before, "a stale confirmation does not start another request");
});

test("lowering the slider during ACT explains cancellation and a new guided request", async () => {
  const current = { session_id: "actor-1", terminal: false, state: "running", mode: "act", takeover: true };
  const r = await renderer({ observeOnly: false, current });
  r.status.autonomy = 2;
  await vm.runInContext("setAutonomy(0)", r.context);
  assert.equal(r.status.autonomy, 0);
  assert.match(r.ids.get("autMsg").textContent, /Stopping the automatic task.*Ask again/);
});

test("feedback requires two explicit labels and preserves separate consent flags", async () => {
  const r = await renderer();
  assert.equal(r.ids.get("feedbackSave").disabled, true);
  r.ids.get("feedbackSuccess").value = "partial";
  r.ids.get("feedbackUseful").value = "yes";
  r.ids.get("feedbackComment").value = "Helpful but I checked the result myself.";
  r.ids.get("feedbackUseful").events.change();
  assert.equal(r.ids.get("feedbackSave").disabled, false);
  await r.ids.get("feedbackSave").events.click();
  const sent = r.calls.find((c) => c.method === "POST" && c.path === "/feedback");
  assert.deepEqual(JSON.parse(JSON.stringify(sent.body)), { session_id: "episode-7", success: "partial", useful: "yes", comment: "Helpful but I checked the result myself.", confirmed_by_human: true, allow_screenshots_to_support: false, training_consent: false });
});

test("main process hides confirmation before next and restores it on backend rejection", async () => {
  const handlers = new Map();
  const order = [];
  let ok = true;
  const win = { hide: () => order.push("hide"), show: () => order.push("show"), isDestroyed: () => false, isVisible: () => true, isMinimized: () => false, getBounds: () => ({ x: 2, y: 3, width: 400, height: 300 }) };
  const context = vm.createContext({
    process: { env: {}, argv: [], platform: "darwin" },
    app: { requestSingleInstanceLock: () => true, whenReady: () => ({ then() {} }), on() {} }, BrowserWindow: { fromWebContents: () => win }, ipcMain: { handle: (name, fn) => handlers.set(name, fn), on() {} },
    path: { resolve: (...parts) => parts.join("/"), join: (...parts) => parts.join("/") }, fs: {}, os: {}, AbortSignal,
    setTimeout: (fn, delay) => { order.push(`wait:${delay}`); fn(); },
    fetch: async (_url, args) => { order.push("fetch"); assert.equal(args.headers["X-HCS-App"], "1"); return { ok, status: ok ? 200 : 409, json: async () => ({}) }; },
  });
  const code = (await readFile(new URL("../main.mjs", import.meta.url), "utf8")).replace(/^import .*;\n/gm, "").replace('const here = path.dirname(fileURLToPath(import.meta.url));', 'const here = "/test";');
  vm.runInContext(code, context);
  const handler = handlers.get("agent");
  await handler({ sender: {} }, "POST", "/next", { session_id: "episode", step_index: 2, done: true });
  assert.deepEqual(order, ["hide", "wait:150", "fetch"]);
  order.length = 0; ok = false;
  await handler({ sender: {} }, "POST", "/next", {});
  assert.deepEqual(order, ["hide", "wait:150", "fetch", "show"]);
  for (const route of ["/feedback", "/feedback/dictate", "/ptt", "/rate"]) {
    order.length = 0;
    await handler({ sender: {} }, "POST", route, {});
    assert.deepEqual(order, ["fetch"], route);
  }
  const denied = await handler({ sender: {} }, "POST", "/unexpected", {});
  assert.equal(denied.status, 400);
});


test("Stop is available on Voice and Feedback, shows stopping then actual terminal state", async () => {
  const current = { session_id: "stop-test", terminal: false, state: "running", mode: "guide" };
  let reply;
  const r = await renderer({ current, stopResponse: () => new Promise((resolve) => { reply = resolve; }) });
  for (const tab of ["voice", "feedback"]) {
    vm.runInContext(`go("${tab}")`, r.context);
    assert.equal(r.ids.get("globalStopBar").hidden, false);
    assert.equal(r.ids.get("globalStopBtn").disabled, false);
  }
  const sent = r.ids.get("globalStopBtn").events.click();
  assert.equal(r.ids.get("globalStopBtn").textContent, "Stopping…");
  assert.equal(r.ids.get("stopBtn").disabled, true);
  await r.ids.get("globalStopBtn").events.click();
  assert.equal(r.calls.filter((c) => c.path === "/stop").length, 1);
  r.status.current.state = "stopping";
  reply({ ok: true, status: 200, data: { stopped: true } });
  await sent;
  assert.match(r.ids.get("stopMessage").textContent, /Waiting/);
  assert.equal(r.ids.get("globalStopBtn").disabled, true);
  Object.assign(r.status.current, { state: "stopped", terminal: true });
  await vm.runInContext("poll()", r.context);
  assert.equal(r.ids.get("stopMessage").textContent, "Task stopped.");
});

test("Stop rejection is visible and retryable without claiming the task stopped", async () => {
  const current = { session_id: "reject-test", terminal: false, state: "running", mode: "guide" };
  const r = await renderer({ current, stopResponse: async () => ({ ok: false, status: 503, data: {} }) });
  vm.runInContext('go("voice")', r.context);
  await r.ids.get("globalStopBtn").events.click();
  assert.match(r.ids.get("stopMessage").textContent, /not accepted/);
  assert.equal(r.ids.get("globalStopBtn").disabled, false);
  assert.equal(r.status.current.state, "running");
});
