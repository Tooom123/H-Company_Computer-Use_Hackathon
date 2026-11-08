import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { readFile } from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";
import test from "node:test";
import { createMenuBar } from "../menu-bar.mjs";

const settled = () => new Promise((r) => setImmediate(r));
class TrayDouble extends EventEmitter {
  constructor(icon) { super(); this.icon = icon; this.destroyed = false; }
  setToolTip(text) { this.tooltip = text; }
  setContextMenu(items) { this.items = items; }
  destroy() { this.destroyed = true; }
  isDestroyed() { return this.destroyed; }
  item(label) { return this.items.find((item) => item.label === label); }
}
function trayHarness({ stopTask = async () => ({ ok: true, data: { stopped: true } }), startRuntime } = {}) {
  const calls = [];
  const icon = { isEmpty: () => false, setTemplateImage: (value) => calls.push(["template", value]) };
  const tray = createMenuBar({ Tray: TrayDouble, Menu: { buildFromTemplate: (items) => items },
    nativeImage: { createFromPath: () => icon }, iconPath: "/test/icon.png",
    dialog: { showMessageBox: async (options) => calls.push(["dialog", options]) },
    showWindow: () => calls.push(["show"]), stopTask, startRuntime, quit: () => calls.push(["quit"]) });
  return { tray, calls };
}

test("menu is passive until clicked; open, stop and quit remain available without polling", async () => {
  let stops = 0;
  const h = trayHarness({ stopTask: async () => { stops++; return { ok: true, data: { stopped: true } }; } });
  assert.equal(stops, 0);
  assert.equal(h.tray.item("Start Devin coach"), undefined);
  assert.deepEqual(h.calls, [["template", true]]);
  h.tray.item("Open H Companion").click();
  assert.equal(h.calls.at(-1)[0], "show");
  await h.tray.item("Stop task").click();
  assert.equal(stops, 1);
  assert.equal(h.tray.items[0].label, "Stop requested — check Activity");
  h.tray.item("Quit H Companion").click();
  assert.equal(h.calls.at(-1)[0], "quit");
});

test("menu stop failure stays explicit and can be retried; accepted is not claimed as stopped", async () => {
  let calls = 0;
  const h = trayHarness({ stopTask: async () => ++calls === 1
    ? { ok: false, offline: true } : { ok: true, data: { stopped: false } } });
  await h.tray.item("Stop task").click();
  assert.equal(h.tray.items[0].label, "Stop was not confirmed");
  assert.match(h.calls.at(-1)[1].detail, /not responding/);
  assert.equal(h.tray.item("Stop task").enabled, true);
  await h.tray.item("Stop task").click();
  assert.equal(h.tray.items[0].label, "No active task to stop");
});

test("startup waits for readiness, rejects duplicate clicks and surfaces errors", async () => {
  let resolveStart;
  let starts = 0;
  const h = trayHarness({ startRuntime: () => { starts++; return new Promise((resolve) => { resolveStart = resolve; }); } });
  const started = h.tray.item("Start Devin coach").click();
  assert.equal(h.tray.item("Start Devin coach").enabled, false);
  await h.tray.item("Start Devin coach").click();
  assert.equal(starts, 1);
  assert.ok(!h.calls.some(([name]) => name === "show"));
  resolveStart({ ok: false, message: "Different pilot already uses the port." });
  await started;
  assert.equal(h.tray.items[0].label, "Coach could not start");
  assert.equal(h.calls.at(-1)[1].detail, "Different pilot already uses the port.");
  const again = h.tray.item("Start Devin coach").click();
  resolveStart({ ok: true });
  await again;
  assert.equal(h.tray.items[0].label, "Devin coach ready");
  assert.equal(h.calls.at(-1)[0], "show");
});

async function mainHarness({ platform = "darwin", lock = true, smoke = false } = {}) {
  const app = new EventEmitter();
  const calls = [];
  app.requestSingleInstanceLock = () => { calls.push("lock"); return lock; };
  app.whenReady = () => Promise.resolve();
  app.quit = () => { calls.push("quit"); app.emit("before-quit"); };
  app.setPath = () => {};
  const handlers = new Map();
  class WindowDouble extends EventEmitter {
    constructor() {
      super(); this.visible = true; this.destroyed = false; this.minimized = false;
      this.webContents = new EventEmitter(); this.webContents.send = () => {};
      this.webContents.setWindowOpenHandler = () => {};
      windows.push(this);
    }
    isDestroyed() { return this.destroyed; }
    isVisible() { return this.visible; }
    isMinimized() { return this.minimized; }
    hide() { this.visible = false; }
    show() { this.visible = true; calls.push("show"); }
    restore() { this.minimized = false; calls.push("restore"); }
    focus() { calls.push("focus"); }
    setMenuBarVisibility() {}
    setContentProtection() {}
    loadFile() {}
    getBounds() { return { x: 1, y: 2, width: 940, height: 640 }; }
    close() {
      let prevented = false;
      this.emit("close", { preventDefault: () => { prevented = true; } });
      if (!prevented) { this.destroyed = true; this.emit("closed"); app.emit("window-all-closed"); }
    }
  }
  const windows = [];
  WindowDouble.fromWebContents = () => windows[0];
  const tray = new TrayDouble({});
  let trayOptions;
  const context = vm.createContext({ process: { env: {}, argv: smoke ? ["--smoke"] : [], platform },
    app, BrowserWindow: WindowDouble, ipcMain: { handle: (name, fn) => handlers.set(name, fn), on() {} },
    Tray: TrayDouble, Menu: {}, nativeImage: {}, dialog: {},
    createMenuBar: (options) => { trayOptions = options; return tray; },
    path, fs: { mkdtempSync: () => "/tmp/profile" }, os: { tmpdir: () => "/tmp" },
    console, setTimeout, clearTimeout, AbortSignal,
    fetch: async (_url, options) => { calls.push({ request: options }); return { ok: true, status: 200, json: async () => ({ current: null }) }; } });
  const code = (await readFile(new URL("../main.mjs", import.meta.url), "utf8"))
    .replace(/^import .*;\n/gm, "")
    .replace('const here = path.dirname(fileURLToPath(import.meta.url));', 'const here = "/test";');
  vm.runInContext(code, context);
  await settled();
  return { app, windows, calls, handlers, tray, trayOptions };
}

test("macOS close hides without losing the window; reopen and second launch focus the same window", async () => {
  const h = await mainHarness();
  const win = h.windows[0];
  win.close();
  assert.equal(win.destroyed, false);
  assert.equal(win.visible, false);
  assert.ok(!h.calls.includes("quit"));
  h.trayOptions.showWindow();
  assert.equal(win.visible, true);
  win.minimized = true;
  h.app.emit("second-instance");
  await settled();
  assert.equal(h.windows.length, 1);
  assert.equal(win.minimized, false);
  assert.ok(h.calls.includes("focus"));
  h.app.quit();
  win.close();
  assert.equal(win.destroyed, true, "explicit quit must not be intercepted as hide");
  assert.equal(h.tray.destroyed, true);
});

test("a hidden or minimized window sends no heartbeat; reopening resumes and /next omits stale bounds", async () => {
  const h = await mainHarness();
  const win = h.windows[0];
  const agent = h.handlers.get("agent");
  await agent({}, "GET", "/status");
  const requests = () => h.calls.filter((call) => typeof call === "object");
  assert.equal(requests().length, 1);
  assert.equal(requests()[0].request.headers["X-HCS-App-Bounds"], "1,2,940,640");
  win.hide();
  const cached = await agent({}, "GET", "/status");
  assert.equal(cached.ok, true);
  await agent({}, "GET", "/feedback");
  assert.equal(requests().length, 1);
  win.show(); win.minimized = true;
  await agent({}, "GET", "/status");
  assert.equal(requests().length, 1);
  win.restore();
  await agent({ sender: {} }, "POST", "/next", {});
  assert.equal(requests().length, 2);
  assert.equal(requests().at(-1).request.headers["X-HCS-App-Bounds"], undefined);
  assert.equal(requests().at(-1).request.headers["X-HCS-App"], "1");
});

test("Linux keeps close-to-quit; smoke is isolated; a second normal instance creates no window", async () => {
  const linux = await mainHarness({ platform: "linux" });
  assert.equal(linux.trayOptions, undefined);
  linux.windows[0].close();
  assert.equal(linux.windows[0].destroyed, true);
  assert.ok(linux.calls.includes("quit"));
  const smoke = await mainHarness({ smoke: true });
  assert.equal(smoke.trayOptions, undefined);
  assert.ok(!smoke.calls.includes("lock"));
  const duplicate = await mainHarness({ lock: false });
  assert.equal(duplicate.windows.length, 0);
  assert.equal(duplicate.trayOptions, undefined);
  assert.ok(duplicate.calls.includes("quit"));
});
