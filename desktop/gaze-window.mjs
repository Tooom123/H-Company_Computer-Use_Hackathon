// Built-in gaze calibration and tracking (Tom), for any computer where Édouard's Vision Lab cannot run (it needs
// macOS for its native capture helper). It opens the webcam vision page (heatmap/vision.html: WebGazer + MediaPipe,
// local copies, Édouard's calibration grid) in a full-screen window. After calibration the window turns transparent,
// lets every click through, stays invisible to screen capture, and keeps tracking: each gaze point (screen points,
// no image) goes to the agent's control point (POST /gaze), so the agent can crop its screenshots around it.

import { BrowserWindow, ipcMain, screen, session, shell } from "electron";
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".wasm": "application/wasm", ".data": "application/octet-stream",
  ".binarypb": "application/octet-stream", ".tflite": "application/octet-stream", ".png": "image/png", ".svg": "image/svg+xml" };

/** Static files of heatmap/ on 127.0.0.1 (a secure context for the camera; file:// cannot fetch the models). */
function serve(root, onFeed) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      if (req.method === "POST" && (req.url === "/gaze" || req.url === "/accuracy")) { // browser mode: same origin
        let body = "";
        req.on("data", (c) => { body += c; if (body.length > 2000) req.destroy(); });
        req.on("end", () => {
          let data = null;
          try { data = JSON.parse(body); } catch {}
          res.writeHead(data ? 204 : 400).end();
          if (data) onFeed(req.url, data);
        });
        return;
      }
      const rel = decodeURIComponent((req.url || "/").split("?")[0]).replace(/^\/+/, "") || "vision.html";
      const file = path.resolve(root, rel);
      if (!file.startsWith(path.resolve(root) + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404).end();
        return;
      }
      res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-store" });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

const TRACKER = "http://127.0.0.1:8769"; // tracker/gaze_tracker.py

async function trackerCall(method, p, body) {
  try {
    const r = await fetch(TRACKER + p, { method, headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(method === "GET" ? 800 : 6000) });
    return await r.json();
  } catch {
    return null;
  }
}

export function createGazeCalibrator({ heatmapDir, agentUrl, preload, overlayPreload, trackerScript, trackerPython }) {
  let win = null;
  let overlay = null; // the red honeycomb over the whole screen while the gaze is tracked
  let overlayIdle = null;
  let server = null;
  let tracking = false;
  let errorPx = null;
  let lastSent = 0;
  let inFlight = false;
  let pausedUntil = 0;
  let samples = 0;
  let lastFeed = 0;
  let opened = 0;
  // Electron 45 crashes when WebGazer starts on Linux (checked on Wayland, every GPU/sandbox switch): there the
  // calibration opens in the user's browser instead, full screen, and the page posts its gaze to this server.
  // Preferred: the background tracker (tracker/gaze_tracker.py: camera + MediaPipe in a plain process), which keeps
  // tracking whatever app is in front; the overlay window only draws (calibration dots, then the honeycomb).
  const pythonOk = Boolean(trackerPython && fs.existsSync(trackerPython) && trackerScript && fs.existsSync(trackerScript));
  const forced = process.env.HCS_VISION_WINDOW; // "native" | "browser" | "electron"
  const mode = forced || (pythonOk ? "native" : process.platform === "linux" ? "browser" : "electron");
  let proc = null; // the tracker process
  let poll = null; // gaze polling while tracking
  let trackerState = null;
  const onFeed = (url, d) => {
    if (url === "/accuracy" && Number.isFinite(d.px) && d.px > 0) {
      errorPx = Math.round(d.px);
      if (overlay && !overlay.isDestroyed()) overlay.webContents.send("overlay:accuracy", errorPx);
    }
    if (url === "/gaze" && opened && Number.isFinite(d.x) && Number.isFinite(d.y)) {
      lastFeed = Date.now();
      samples += 1;
      forward(d.x, d.y); // full screen in the browser: page coordinates are screen coordinates
    }
  };

  const ready = () => fs.existsSync(path.join(heatmapDir, "vision.html")) && fs.existsSync(path.join(heatmapDir, "vendor", "webgazer.js"));

  function status() {
    if (mode === "native") {
      if (!pythonOk) return { available: false, running: false, builtin: true, reason: "Install the gaze tracker once: see desktop/tracker/README.md." };
      const alive = Boolean(proc && proc.exitCode === null);
      const live = Date.now() - lastFeed < 2000;
      const reason = trackerState && trackerState.state === "no_camera" ? trackerState.message : undefined;
      return { available: true, running: alive, tracking: alive && live, builtin: true, native: true, errorPx, samples, reason,
        face: trackerState ? trackerState.face : undefined };
    }
    if (!ready()) return { available: false, running: false, builtin: true, reason: "Run `npm install && npm run assets` in heatmap/ once (local WebGazer)." };
    if (mode === "browser") {
      const live = Date.now() - lastFeed < 3000;
      return { available: true, running: live || Date.now() - opened < 120000, tracking: live, builtin: true, browser: true, errorPx, samples };
    }
    return { available: true, running: Boolean(win && !win.isDestroyed()), tracking, builtin: true, errorPx, samples };
  }

  /** Screen point -> the overlay (full screen, click-through, never captured): the user sees what is tracked. */
  async function showGaze(x, y) {
    if (!server) return;
    await ensureOverlay(false);
    if (!overlay || overlay.isDestroyed()) return;
    const b = overlay.getBounds();
    overlay.webContents.send("overlay:gaze", { x: x - b.x, y: y - b.y });
    clearTimeout(overlayIdle);
    overlayIdle = setTimeout(() => overlay && !overlay.isDestroyed() && overlay.webContents.send("overlay:gaze", null), 1500);
  }

  let overlayLoading = null;
  /** The full-screen transparent window. interactive = calibration (takes clicks); else click-through. */
  async function ensureOverlay(interactive) {
    if (overlayLoading) await overlayLoading;
    if (!overlay || overlay.isDestroyed()) {
      overlayLoading = createOverlay();
      await overlayLoading;
      overlayLoading = null;
    }
    if (!overlay || overlay.isDestroyed()) return;
    overlay.setIgnoreMouseEvents(!interactive);
    overlay.setFocusable(interactive);
    if (interactive) overlay.focus();
  }

  async function createOverlay() {
    {
      const { bounds } = screen.getPrimaryDisplay();
      overlay = new BrowserWindow({
        ...bounds, frame: false, transparent: true, resizable: false, movable: false, focusable: false,
        alwaysOnTop: true, skipTaskbar: true, hasShadow: false, backgroundColor: "#00000000", show: false,
        webPreferences: { preload: overlayPreload, contextIsolation: true, sandbox: true, backgroundThrottling: false },
      });
      overlay.setIgnoreMouseEvents(true);
      overlay.setAlwaysOnTop(true, "screen-saver");
      overlay.setVisibleOnAllWorkspaces?.(true, { visibleOnFullScreen: true });
      overlay.setContentProtection(true); // never in a screenshot: Holo must not see the honeycomb
      overlay.on("closed", () => { overlay = null; });
      await overlay.loadURL(`http://127.0.0.1:${server.address().port}/overlay.html`);
      overlay.showInactive();
      if (Number.isFinite(errorPx)) overlay.webContents.send("overlay:accuracy", errorPx);
    }
  }

  // --- native mode: calibration driven by the overlay page, gaze from the background tracker -------------------
  const fromOverlay = (e) => overlay && !overlay.isDestroyed() && e.sender === overlay.webContents;
  const toScreen = (p) => { const b = overlay.getBounds(); return { x: b.x + p.x, y: b.y + p.y }; };
  ipcMain.handle("overlay:calib-point", (e, p) => (fromOverlay(e) ? trackerCall("POST", "/calibrate/point", toScreen(p)) : null));
  ipcMain.handle("overlay:fit", (e) => (fromOverlay(e) ? trackerCall("POST", "/calibrate/fit", {}) : null));
  ipcMain.handle("overlay:validate", (e, p) => (fromOverlay(e) ? trackerCall("POST", "/validate/point", toScreen(p)) : null));
  ipcMain.on("overlay:done", async (e, px) => {
    if (!fromOverlay(e)) return;
    if (Number.isFinite(px) && px > 0) {
      errorPx = Math.round(px);
      overlay.webContents.send("overlay:accuracy", errorPx);
      await trackerCall("POST", "/accuracy", { px: errorPx });
    }
    await ensureOverlay(false); // tracking: click-through from now on
    startPolling();
  });

  function startPolling() {
    clearInterval(poll);
    poll = setInterval(async () => {
      const g = await trackerCall("GET", "/gaze");
      if (g && Number.isFinite(g.x) && Number.isFinite(g.y)) {
        lastFeed = Date.now();
        samples += 1;
        forward(g.x, g.y);
      }
    }, 50);
  }

  async function startNative() {
    if (!proc || proc.exitCode !== null) {
      proc = spawn(trackerPython, [trackerScript], { stdio: "ignore" });
      proc.on("exit", () => { proc = null; clearInterval(poll); });
    }
    for (let i = 0; i < 120; i++) { // first start downloads the face model (3.6 MB)
      trackerState = await trackerCall("GET", "/status");
      if (trackerState && trackerState.state !== "starting") break;
      await new Promise((r) => setTimeout(r, 250));
    }
    if (!trackerState || trackerState.state === "no_camera") { // camera busy or missing: say it, retry next time
      const st = status();
      trackerCall("POST", "/quit", {});
      return { ...st, running: false, reason: trackerState ? trackerState.message : "The gaze tracker did not start." };
    }
    await trackerCall("POST", "/calibrate/start", {});
    clearInterval(poll);
    lastFeed = 0;
    await ensureOverlay(true);
    overlay.webContents.send("overlay:mode", "calibrate");
    return status();
  }

  function forward(x, y) {
    showGaze(x, y).catch(() => {});
    const now = Date.now();
    if (inFlight || now < pausedUntil || now - lastSent < 66) return; // ~15 points a second is plenty
    lastSent = now;
    inFlight = true;
    const body = { x, y };
    if (Number.isFinite(errorPx)) body.error_px = errorPx;
    fetch(`${agentUrl}/gaze`, { method: "POST", headers: { "Content-Type": "application/json", "X-HCS-Gaze": "1" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(500) })
      .then((r) => r.json().catch(() => ({})))
      .then((r) => { if (r && r.accepted === false) pausedUntil = Date.now() + 3000; }) // Vision is off in the app
      .catch(() => { pausedUntil = Date.now() + 3000; }) // the agent is not running
      .finally(() => { inFlight = false; });
  }

  const fromWindow = (e) => win && !win.isDestroyed() && e.sender === win.webContents;
  ipcMain.on("gaze:sample", (e, p) => {
    if (!fromWindow(e) || !p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) return;
    const b = win.getContentBounds(); // page coordinates -> screen points
    samples += 1;
    forward(b.x + p.x, b.y + p.y);
  });
  ipcMain.on("gaze:accuracy", (e, px) => {
    if (fromWindow(e) && Number.isFinite(px) && px > 0) errorPx = Math.round(px);
  });
  ipcMain.on("gaze:track", (e) => { // calibration done: invisible, click-through, keeps tracking
    if (!fromWindow(e)) return;
    tracking = true;
    win.setIgnoreMouseEvents(true, { forward: true });
    win.setFocusable(false);
    win.blur();
  });
  ipcMain.on("gaze:close", (e) => { if (fromWindow(e)) stop(); });

  async function start() {
    if (mode === "native") {
      if (!pythonOk) return status();
      if (!server) server = await serve(heatmapDir, onFeed); // overlay page + its scripts
      return startNative();
    }
    if (!ready()) return status();
    if (win && !win.isDestroyed()) {
      win.show();
      return status();
    }
    if (!server) server = await serve(heatmapDir, onFeed);
    const origin = `http://127.0.0.1:${server.address().port}`;
    if (mode === "browser") {
      opened = Date.now();
      await shell.openExternal(`${origin}/vision.html?feed=1`);
      return status();
    }
    const ses = session.fromPartition("gaze-calibration");
    ses.setPermissionRequestHandler((wc, permission, cb) => cb(permission === "media" && wc.getURL().startsWith(origin)));
    ses.setPermissionCheckHandler((wc, permission) => permission === "media" && (wc?.getURL() || "").startsWith(origin));
    const { bounds } = screen.getPrimaryDisplay();
    tracking = false;
    win = new BrowserWindow({
      ...bounds, frame: false, transparent: true, resizable: false, movable: false, fullscreenable: false,
      alwaysOnTop: true, skipTaskbar: true, hasShadow: false, backgroundColor: "#00000000",
      webPreferences: { preload, partition: "gaze-calibration", contextIsolation: true, sandbox: true, backgroundThrottling: false },
    });
    win.setAlwaysOnTop(true, "screen-saver");
    win.setContentProtection(true); // like the overlay: never in a screenshot, so never seen by H
    win.on("closed", () => { win = null; tracking = false; });
    await win.loadURL(`${origin}/vision.html?embedded=1`);
    return status();
  }

  function stop() {
    clearInterval(poll);
    poll = null;
    if (proc && proc.exitCode === null) {
      trackerCall("POST", "/quit", {});
      const p = proc;
      setTimeout(() => { if (p.exitCode === null) p.kill(); }, 1500); // the camera is released with the process
    }
    proc = null;
    opened = 0;
    lastFeed = 0; // browser mode: the tab keeps running until the user closes it; the feed is ignored from now
    if (win && !win.isDestroyed()) win.destroy(); // the page's unload stops the camera
    if (overlay && !overlay.isDestroyed()) overlay.destroy();
    overlay = null;
    win = null;
    tracking = false;
    return status();
  }

  function dispose() {
    stop();
    if (server) server.close();
    server = null;
  }

  return { status, start, stop, dispose };
}
