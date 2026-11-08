// H Companion desktop app — main process.
// The window is the assistant's home: live status, autonomy, voice, usage and plan, vision.
// It talks to the running agent (`hcs-agent talk`) on 127.0.0.1:8768 and to the support backend on :8766.
// No key ever lives here: the agent and the backend keep them; the renderer only sees JSON via IPC.

import { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, dialog } from "electron";
import { createMenuBar } from "./menu-bar.mjs";
import { createGazeCalibrator } from "./gaze-window.mjs";
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const AGENT = process.env.HCS_CONTROL_URL || "http://127.0.0.1:8768";
const VISION_DIR = path.resolve(here, "..", "app"); // Édouard's Vision Lab
const AGENT_PATHS = /^\/(status|sessions|usage|autonomy|stop|next|voice|voice\/test|ptt|rate|feedback|feedback\/dictate|vision)$/;
let mainWin = null;
let menuBar = null;
let quitting = false;
const agentCache = new Map();

const smoke = process.argv.includes("--smoke");
// A smoke run gets its own profile: it must not share the GPU cache with an open app, nor write the user's
// preferences (voice, key) when it clicks around.
if (smoke) app.setPath("userData", fs.mkdtempSync(path.join(os.tmpdir(), "hcs-app-smoke-")));
const ownsInstance = smoke || app.requestSingleInstanceLock();
if (!ownsInstance) app.quit();
const section = (process.argv.find((a) => a.startsWith("--section=")) || "").split("=")[1] || "home";

async function call(base, method, p, body, headers = {}) {
  try {
    const r = await fetch(base + p, {
      method,
      headers: { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(method === "GET" && p === "/usage" ? 8000 : 3000),
    });
    const data = await r.json().catch(() => null);
    return { ok: r.ok, status: r.status, data };
  } catch {
    return { ok: false, status: 0, offline: true, data: null };
  }
}

ipcMain.handle("agent", async (_e, method, p, body) => {
  if (!["GET", "POST"].includes(method) || typeof p !== "string" || !AGENT_PATHS.test(p)) {
    return { ok: false, status: 400, data: { error: "not allowed" } };
  }
  if (!smoke && method === "GET" && mainWin && !mainWin.isDestroyed()
      && (!mainWin.isVisible() || mainWin.isMinimized())) {
    // Renderer timers may keep firing while hidden. Do not send their presence heartbeat to the coach.
    return agentCache.get(p) ?? { ok: false, status: 0, hidden: true, data: null };
  }
  // Return to the software before H observes it, rather than our confirmation panel.
  const win = method === "POST" && p === "/next" ? BrowserWindow.fromWebContents(_e.sender) : null;
  if (win) {
    win.hide();
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  // Compute this after hiding the confirmation window, so its old rectangle cannot consume a click.
  const headers = { "X-HCS-App": "1" };
  if (mainWin && !mainWin.isDestroyed() && mainWin.isVisible() && !mainWin.isMinimized()) {
    const b = mainWin.getBounds();
    headers["X-HCS-App-Bounds"] = `${b.x},${b.y},${b.width},${b.height}`;
  }
  const result = await call(AGENT, method, p, method === "POST" ? body ?? {} : undefined, headers);
  if (method === "GET") agentCache.set(p, result);
  if (win && !result.ok && !win.isDestroyed()) win.show();
  return result;
});

// Vision Lab (Édouard): started as its own process from app/, stopped with this app.
// Vision: Édouard's Vision Lab on macOS when it is installed; otherwise the built-in webcam calibration
// (gaze-window.mjs: heatmap/vision.html in a full-screen window that keeps tracking, click-through, afterwards).
let vision = null;
const gaze = createGazeCalibrator({ heatmapDir: path.resolve(here, "..", "heatmap"), agentUrl: AGENT,
  preload: path.join(here, "gaze-preload.cjs"), overlayPreload: path.join(here, "gaze-overlay-preload.cjs") });
function labStatus() {
  if (process.platform !== "darwin" || process.env.HCS_VISION_BUILTIN === "1") return null; // the lab needs macOS
  if (!fs.existsSync(path.join(VISION_DIR, "package.json")) || !fs.existsSync(path.join(VISION_DIR, "node_modules"))) return null;
  return { available: true, running: Boolean(vision && vision.exitCode === null), builtin: false };
}
function visionStatus() {
  return labStatus() || gaze.status();
}
ipcMain.handle("vision:status", () => visionStatus());
ipcMain.handle("vision:start", async () => {
  const lab = labStatus();
  if (!lab) return gaze.start();
  if (lab.running) return lab;
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE; // the lab is a full Electron app of its own
  vision = spawn(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "dev"], { cwd: VISION_DIR, stdio: "ignore", env });
  vision.on("exit", () => (vision = null));
  return { ...visionStatus(), running: true };
});
ipcMain.handle("vision:stop", () => {
  if (vision && vision.exitCode === null) vision.kill();
  gaze.stop();
  return visionStatus();
});

// Window controls for the frameless window (the top bar draws them; only these three actions exist).
ipcMain.on("win", (e, action) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (!win) return;
  if (action === "minimize") win.minimize();
  else if (action === "maximize") win.isMaximized() ? win.unmaximize() : win.maximize();
  else if (action === "close") win.close();
});

function createWindow() {
  const mac = process.platform === "darwin";
  const win = new BrowserWindow({
    width: 940,
    height: 640,
    minWidth: 780,
    minHeight: 540,
    title: "H Companion",
    backgroundColor: "#f9f9fb",
    // Frameless everywhere but macOS: GNOME on Wayland gives an Electron window no title bar at all (it could not
    // be moved, minimised or closed). The black tab bar is the title bar: drag it to move the window, its buttons
    // on the right minimise / maximise / close. macOS keeps the native traffic lights.
    frame: mac,
    titleBarStyle: mac ? "hiddenInset" : undefined,
    show: !smoke,
    webPreferences: {
      preload: path.join(here, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  mainWin = win;
  win.on("close", (event) => {
    if (menuBar && !quitting && !smoke) {
      event.preventDefault();
      win.hide();
    }
  });
  win.on("closed", () => { if (mainWin === win) mainWin = null; });
  win.setMenuBarVisibility(false);
  // Like Matteo's overlay: invisible to screen capture, so H never sees (or clicks) the app and the guide's
  // screen watcher does not mistake the app's live updates for the user acting. HCS_APP_CAPTURABLE=1 to record it.
  if (process.env.HCS_APP_CAPTURABLE !== "1") win.setContentProtection(true);
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (e) => e.preventDefault());
  const sendState = () => win.webContents.send("win:state", { maximized: win.isMaximized() });
  win.on("maximize", sendState);
  win.on("unmaximize", sendState);
  win.webContents.on("did-finish-load", sendState);
  // Keyboard: Ctrl/Cmd+W closes, Ctrl/Cmd+M minimises (no menu bar to carry the usual accelerators).
  win.webContents.on("before-input-event", (e, input) => {
    if (input.type !== "keyDown" || !(input.control || input.meta) || input.alt || input.shift) return;
    const k = input.key.toLowerCase();
    if (k === "w") (e.preventDefault(), win.close());
    else if (k === "m") (e.preventDefault(), win.minimize());
  });
  win.loadFile(path.join(here, "renderer", "index.html"), { hash: section });

  if (smoke) {
    // `npm run smoke -- --section=usage`: render, capture a PNG, quit (used to check the UI without a Mac).
    win.webContents.once("did-finish-load", () => {
      setTimeout(async () => {
        try {
        if (process.env.HCS_SMOKE_JS) {
          // e.g. click a control, then capture what the app shows after the agent answered
          await win.webContents.executeJavaScript(process.env.HCS_SMOKE_JS);
          await new Promise((r) => setTimeout(r, 1800));
        }
        const img = await win.webContents.capturePage();
        const out = process.env.HCS_SMOKE_OUT || path.join(here, `smoke-${section}.png`);
        fs.writeFileSync(out, img.toPNG());
        console.log(`smoke: wrote ${out}`);
        } catch (err) {
          console.error(`smoke: failed: ${err}`);
          process.exitCode = 1;
        }
        app.quit();
      }, Number(process.env.HCS_SMOKE_WAIT_MS || 2500));
    });
  }
}

function showMainWindow() {
  const win = mainWin;
  if (!win || win.isDestroyed()) createWindow();
  else {
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
  }
}

function startDevinRuntime() {
  return new Promise((resolve) => {
    const child = spawn(process.env.HCS_PILOT_PYTHON,
      [path.resolve(here, "../scripts/start-devin-companion.py"), "--backend-only"],
      { cwd: path.resolve(here, ".."), env: process.env, stdio: ["ignore", "pipe", "pipe"] });
    let output = "";
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    const timer = setTimeout(() => {
      child.kill();
      finish({ ok: false, message: "Coach startup timed out. Open the launch shortcut to inspect its status." });
    }, 60000);
    const append = (chunk) => { output = (output + chunk.toString()).slice(-3000); };
    child.stdout.on("data", append);
    child.stderr.on("data", append);
    child.on("error", () => finish({ ok: false, message: "The configured Python launcher could not be opened." }));
    child.on("close", (code) => finish({ ok: code === 0, message: code === 0 ? "" : output.trim() || "The coach exited before it was ready." }));
  });
}

if (ownsInstance) {
  app.whenReady().then(() => {
    if (process.platform === "darwin" && !smoke) {
      if (app.dock) app.dock.setIcon(path.join(here, "assets", "companion.png"));
      try {
        const canStart = process.env.HCS_PILOT_KIND === "devin-native"
          && path.isAbsolute(process.env.HCS_PILOT_PYTHON || "")
          && fs.existsSync(process.env.HCS_PILOT_PYTHON);
        menuBar = createMenuBar({ Tray, Menu, nativeImage, dialog,
          iconPath: path.join(here, "assets", "companionTemplate.png"), showWindow: showMainWindow,
          stopTask: () => call(AGENT, "POST", "/stop", {}, { "X-HCS-App": "1" }),
          startRuntime: canStart ? startDevinRuntime : null, quit: () => app.quit() });
      } catch (error) {
        console.error("Could not create H Companion menu bar:", error.message);
      }
    }
    createWindow();
  });
  app.on("activate", showMainWindow);
  app.on("second-instance", () => app.whenReady().then(showMainWindow));
}
app.on("window-all-closed", () => { if (!menuBar || smoke) app.quit(); });
app.on("before-quit", () => {
  quitting = true;
  if (menuBar) { menuBar.destroy(); menuBar = null; }
  if (vision && vision.exitCode === null) vision.kill();
  gaze.dispose();
});
