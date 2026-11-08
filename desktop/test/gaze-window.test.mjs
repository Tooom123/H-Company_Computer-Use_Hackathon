import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import path from "node:path";

const source = (await readFile(new URL("../gaze-window.mjs", import.meta.url), "utf8"))
  .replace(/^import .*;\n/gm, "").replace("export function createGazeCalibrator", "function createGazeCalibrator");
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

function fixture({ permission = "granted", allowed = true, mode = "native", load = null,
                    state = { state: "ready", fps: 30 }, statusReply = null, accuracyReply = null } = {}) {
  const windows = [], children = [], requests = [], ipc = new EventEmitter(), intervals = new Map();
  let stopped = 0, permissionRequests = 0, timerId = 0;
  ipc.handle = (name, fn) => ipc.on(name, fn);
  class Window extends EventEmitter {
    constructor(options) {
      super(); this.options = options; this.bounds = options; this.destroyed = false;
      this.calls = []; this.webContents = new EventEmitter(); this.webContents.send = (...a) => this.calls.push(["send", ...a]);
      windows.push(this);
    }
    isDestroyed() { return this.destroyed; }
    getBounds() { return this.bounds; }
    getContentBounds() { return this.bounds; }
    async loadURL() { if (load) await load.promise; }
    destroy() { this.destroyed = true; this.emit("closed"); }
    setBounds(bounds) { this.bounds = bounds; this.calls.push(["bounds", bounds]); }
  }
  for (const name of ["setIgnoreMouseEvents", "setAlwaysOnTop", "setVisibleOnAllWorkspaces", "setSkipTaskbar",
    "setFocusable", "setContentProtection", "show", "showInactive", "hide", "focus", "blur"])
    Window.prototype[name] = function (...args) { this.calls.push([name, ...args]); };
  const context = vm.createContext({
    BrowserWindow: Window, ipcMain: ipc, screen: { getPrimaryDisplay: () => ({
      bounds: { x: 0, y: 0, width: 1470, height: 956 }, workArea: { x: 0, y: 25, width: 1470, height: 860 },
    }) },
    systemPreferences: { getMediaAccessStatus: () => permission,
      askForMediaAccess: async () => { permissionRequests++; return await allowed; } },
    process: { platform: "darwin", env: { HCS_VISION_WINDOW: mode } },
    session: { fromPartition: () => ({ setPermissionRequestHandler() {}, setPermissionCheckHandler() {} }) },
    shell: { async openExternal() {} }, path, fs: { existsSync: () => true },
    http: { createServer: () => ({ listen(_p, _h, cb) { cb(); }, address: () => ({ port: 12345 }), close() {} }) },
    spawn: () => { const child = new EventEmitter(); child.exitCode = null;
      child.kill = () => { child.killed = true; child.exitCode = 0; child.emit("exit"); }; children.push(child); return child; },
    fetch: async (url, options) => {
      requests.push([url, options]);
      const payload = url.endsWith("/status") ? (statusReply ? await statusReply : state)
        : url.endsWith("/accuracy") && accuracyReply ? await accuracyReply : { ok: true };
      return { json: async () => payload };
    }, AbortSignal,
    setTimeout: fn => { queueMicrotask(fn); return 1; }, clearTimeout() {},
    setInterval: fn => { const id = ++timerId; intervals.set(id, fn); return id; }, clearInterval: id => intervals.delete(id),
  });
  vm.runInContext(source + "\nthis.create = createGazeCalibrator;", context);
  const gaze = context.create({ heatmapDir: "/heatmap", agentUrl: "http://agent", preload: "/preload",
    overlayPreload: "/overlay-preload", trackerScript: "/tracker.py", trackerPython: "/python", onStopped: () => stopped++ });
  return { gaze, windows, children, requests, ipc, intervals, stopped: () => stopped, permissionRequests: () => permissionRequests };
}

test("camera permission completes before any tracker or calibration window exists", async () => {
  const permission = deferred(), f = fixture({ permission: "not-determined", allowed: permission.promise });
  const start = f.gaze.start(); await settle();
  assert.equal(f.permissionRequests(), 1); assert.equal(f.children.length, 0); assert.equal(f.windows.length, 0);
  assert.equal(f.gaze.status().starting, true);
  permission.resolve(true); await start;
  assert.equal(f.children.length, 1); assert.equal(f.windows.length, 1);
  assert.equal(f.gaze.status().starting, false);
});

test("denied camera access leaves the panel accessible with a retry explanation", async () => {
  const f = fixture({ permission: "denied" });
  const status = await f.gaze.start();
  assert.equal(status.running, false); assert.match(status.reason, /System Settings/);
  assert.equal(f.windows.length, 0); assert.equal(f.children.length, 0);
});

test("Stop during a permission prompt cannot open calibration after a late Allow", async () => {
  const permission = deferred(), f = fixture({ permission: "not-determined", allowed: permission.promise });
  const start = f.gaze.start(); await settle(); f.gaze.stop(); permission.resolve(true); await start;
  assert.equal(f.windows.length, 0); assert.equal(f.children.length, 0); assert.equal(f.gaze.status().running, false);
});

test("starting tracker or ready-without-frames times out without covering the desktop", async () => {
  for (const state of [{ state: "starting", fps: 0 }, { state: "ready", fps: 0 }]) {
    const f = fixture({ state }); const status = await f.gaze.start();
    assert.equal(f.windows.length, 0); assert.equal(f.children[0].killed, true);
    assert.equal(status.running, false); assert.match(status.reason, /camera is not ready/);
    assert.ok(!f.requests.some(([url]) => url.endsWith("/calibrate/start")));
  }
});

test("calibration stays below OS dialogs and leaves the menu bar and Dock reachable", async () => {
  const f = fixture(); await f.gaze.start(); const w = f.windows[0];
  assert.equal(w.options.alwaysOnTop, false); assert.equal(w.options.fullscreenable, false);
  assert.deepEqual(JSON.parse(JSON.stringify(w.bounds)), { x: 0, y: 25, width: 1470, height: 860 });
  assert.ok(!w.calls.some(([name, on]) => name === "setAlwaysOnTop" && on));
  assert.ok(w.calls.some(([name, ignored]) => name === "setIgnoreMouseEvents" && ignored === false));
});

test("Esc and Cmd-W stop from the main process even if the page is unresponsive", async () => {
  for (const input of [{ type: "keyDown", key: "Escape" }, { type: "keyDown", key: "w", meta: true }]) {
    const f = fixture(); await f.gaze.start(); const w = f.windows[0]; let prevented = false;
    w.webContents.emit("before-input-event", { preventDefault() { prevented = true; } }, input);
    assert.ok(prevented && w.destroyed && f.children[0].killed);
    assert.equal(f.gaze.status().running, false); assert.equal(f.stopped(), 1);
  }
});

test("Cancel button accepts only the calibration renderer and releases its camera", async () => {
  const f = fixture(); await f.gaze.start(); const w = f.windows[0];
  f.ipc.emit("overlay:close", { sender: {} }); assert.equal(w.destroyed, false);
  f.ipc.emit("overlay:close", { sender: w.webContents });
  assert.ok(w.destroyed && f.children[0].killed); assert.equal(f.stopped(), 1);
});

test("Stop during native startup discards the pending status response", async () => {
  const reply = deferred(), f = fixture({ statusReply: reply.promise });
  const start = f.gaze.start(); await settle(); f.gaze.stop(); reply.resolve({ state: "ready", fps: 30 }); await start;
  assert.equal(f.windows.length, 0); assert.ok(f.children[0].killed);
});

test("Stop during page loading cannot reshow the destroyed calibration window", async () => {
  const load = deferred(), f = fixture({ load }); const start = f.gaze.start(); await settle();
  const w = f.windows[0]; assert.ok(w); f.gaze.stop(); load.resolve(); await start;
  assert.ok(w.destroyed); assert.ok(!w.calls.some(([name]) => name === "show" || name === "showInactive"));
});

test("a late validation callback after Stop cannot recreate an overlay or restart polling", async () => {
  const reply = deferred(), f = fixture({ accuracyReply: reply.promise }); await f.gaze.start();
  const w = f.windows[0]; f.ipc.emit("overlay:done", { sender: w.webContents }, 120);
  f.gaze.stop(); reply.resolve({ ok: true }); await settle();
  assert.ok(w.destroyed); assert.equal(f.windows.length, 1); assert.equal(f.intervals.size, 0);
});

test("only the completed tracking overlay floats, and it never consumes clicks", async () => {
  const f = fixture(); await f.gaze.start(); const w = f.windows[0];
  f.ipc.emit("overlay:done", { sender: w.webContents }, 120); await settle();
  assert.ok(w.calls.some(([name, on, level]) => name === "setAlwaysOnTop" && on && level === "floating"));
  assert.deepEqual(w.calls.filter(([name]) => name === "setIgnoreMouseEvents").at(-1), ["setIgnoreMouseEvents", true]);
  assert.ok(!w.calls.flat().includes("screen-saver"));
});

test("embedded WebGazer also waits for permission and has a main-process escape", async () => {
  const permission = deferred(), f = fixture({ mode: "electron", permission: "not-determined", allowed: permission.promise });
  const start = f.gaze.start(); await settle(); assert.equal(f.windows.length, 0);
  permission.resolve(true); await start; const w = f.windows[0];
  assert.equal(w.options.alwaysOnTop, false);
  w.webContents.emit("before-input-event", { preventDefault() {} }, { type: "keyDown", key: "Escape" });
  assert.ok(w.destroyed); assert.equal(f.gaze.status().running, false);
});
