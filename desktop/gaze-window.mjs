// Built-in gaze calibration and tracking (Tom), for any computer where Édouard's Vision Lab cannot run (it needs
// macOS for its native capture helper). It opens the webcam vision page (heatmap/vision.html: WebGazer + MediaPipe,
// local copies, Édouard's calibration grid) in an escapable desktop window. After calibration the window turns transparent,
// lets every click through, stays invisible to screen capture, and keeps tracking: each gaze point (screen points,
// no image) goes to the agent's control point (POST /gaze), so the agent can crop its screenshots around it.

import { BrowserWindow, ipcMain, screen, session, shell, systemPreferences } from "electron";
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

export function createGazeCalibrator({ heatmapDir, agentUrl, preload, overlayPreload, trackerScript, trackerPython, onStopped = () => {} }) {
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
  let generation = 0;
  let starting = null;
  let disposed = false;
  let lastReason = null;
  let overlayInteractive = null;
  let checkingCamera = false;
  let preview = null;
  let cameraIndex = 0;
  const current = (epoch) => !disposed && epoch === generation;
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
  let honeycomb = true; // the user can hide the red honeycomb; the gaze still goes to the agent
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
      const reason = lastReason || (trackerState && trackerState.state === "no_camera" ? trackerState.message : undefined);
      return { available: true, running: alive || Boolean(starting), starting: Boolean(starting), tracking: alive && live,
        builtin: true, native: true, errorPx, samples, reason, checkingCamera, cameraIndex,
        preview: checkingCamera ? preview : null, fps: trackerState?.fps || 0,
        face: trackerState ? trackerState.face : undefined };
    }
    if (!ready()) return { available: false, running: false, builtin: true, reason: "Run `npm install && npm run assets` in heatmap/ once (local WebGazer)." };
    if (mode === "browser") {
      const live = Date.now() - lastFeed < 3000;
      return { available: true, running: live || Date.now() - opened < 120000, tracking: live, builtin: true, browser: true, errorPx, samples };
    }
    return { available: true, running: Boolean(starting || win && !win.isDestroyed()), starting: Boolean(starting),
      tracking, builtin: true, errorPx, samples, reason: lastReason };
  }

  /** Screen point -> the overlay (full screen, click-through, never captured): the user sees what is tracked. */
  async function showGaze(x, y) {
    if (!server) return;
    const epoch = generation;
    await ensureOverlay(false, epoch);
    if (!current(epoch) || !overlay || overlay.isDestroyed()) return;
    const b = overlay.getBounds();
    overlay.webContents.send("overlay:gaze", { x: x - b.x, y: y - b.y });
    clearTimeout(overlayIdle);
    overlayIdle = setTimeout(() => overlay && !overlay.isDestroyed() && overlay.webContents.send("overlay:gaze", null), 1500);
  }

  let overlayLoading = null;
  /** The full-screen transparent window. interactive = calibration (takes clicks); else click-through. */
  async function ensureOverlay(interactive, epoch = generation) {
    if (overlayLoading) await overlayLoading;
    if (!current(epoch)) return;
    if (!overlay || overlay.isDestroyed()) {
      const loading = createOverlay(epoch);
      overlayLoading = loading;
      try { await loading; } finally { if (overlayLoading === loading) overlayLoading = null; }
    }
    if (!current(epoch) || !overlay || overlay.isDestroyed()) return;
    if (overlayInteractive === interactive) return;
    overlayInteractive = interactive;
    const display = screen.getPrimaryDisplay();
    // Calibration is an ordinary window inside the usable desktop. OS permission
    // prompts, the menu bar, the Dock and other apps must remain reachable.
    overlay.setAlwaysOnTop(!interactive, "floating");
    overlay.setVisibleOnAllWorkspaces?.(!interactive, { visibleOnFullScreen: !interactive });
    overlay.setSkipTaskbar(!interactive);
    overlay.setBounds(interactive ? display.workArea : display.bounds);
    overlay.setIgnoreMouseEvents(!interactive);
    overlay.setFocusable(interactive);
    if (interactive) { overlay.show(); overlay.focus(); }
    else { overlay.blur(); overlay.showInactive(); }
  }

  function installExitHandlers(window) {
    // Main-process handler also works when the calibration renderer is busy.
    window.webContents.on("before-input-event", (event, input) => {
      if (input.type === "keyDown" && (input.key === "Escape"
          || input.key?.toLowerCase() === "w" && (input.meta || input.control))) {
        event.preventDefault();
        stop();
      }
    });
    window.webContents.on("render-process-gone", () => {
      if (!window.isDestroyed()) fail("The calibration window stopped. You can try Recalibrate again.");
    });
  }

  async function createOverlay(epoch) {
    {
      const { workArea } = screen.getPrimaryDisplay();
      const created = new BrowserWindow({
        ...workArea, title: "H Companion · Gaze calibration", frame: false, transparent: true,
        fullscreenable: false, resizable: false, movable: false, focusable: false,
        alwaysOnTop: false, skipTaskbar: false, hasShadow: false, backgroundColor: "#00000000", show: false,
        webPreferences: { preload: overlayPreload, contextIsolation: true, sandbox: true, backgroundThrottling: false },
      });
      overlay = created;
      overlayInteractive = null;
      created.setIgnoreMouseEvents(true);
      created.setContentProtection(true);
      installExitHandlers(created);
      created.on("closed", () => { if (overlay === created) { overlay = null; stop(); } });
      await created.loadURL(`http://127.0.0.1:${server.address().port}/overlay.html`);
      if (!current(epoch) || created.isDestroyed()) return;
      if (Number.isFinite(errorPx)) created.webContents.send("overlay:accuracy", errorPx);
      created.webContents.send("overlay:honeycomb", honeycomb);
    }
  }

  /** Show or hide the honeycomb (calibration dots stay visible). Tracking and the agent feed are unchanged. */
  function setHoneycomb(on) {
    honeycomb = Boolean(on);
    if (overlay && !overlay.isDestroyed()) overlay.webContents.send("overlay:honeycomb", honeycomb);
    return honeycomb;
  }

  // --- native mode: calibration driven by the overlay page, gaze from the background tracker -------------------
  const fromOverlay = (e) => overlay && !overlay.isDestroyed() && e.sender === overlay.webContents;
  const toScreen = (p) => { const b = overlay.getBounds(); return { x: b.x + p.x, y: b.y + p.y }; };
  ipcMain.handle("overlay:calib-point", (e, p) => (fromOverlay(e) ? trackerCall("POST", "/calibrate/point", toScreen(p)) : null));
  ipcMain.handle("overlay:fit", (e) => (fromOverlay(e) ? trackerCall("POST", "/calibrate/fit", {}) : null));
  ipcMain.handle("overlay:validate", (e, p) => (fromOverlay(e) ? trackerCall("POST", "/validate/point", toScreen(p)) : null));
  ipcMain.on("overlay:close", (e) => { if (fromOverlay(e)) stop(); });
  ipcMain.on("overlay:done", async (e, px) => {
    if (!fromOverlay(e)) return;
    const epoch = generation;
    if (Number.isFinite(px) && px > 0) {
      errorPx = Math.round(px);
      overlay.webContents.send("overlay:accuracy", errorPx);
      await trackerCall("POST", "/accuracy", { px: errorPx });
    }
    if (!current(epoch)) return;
    await ensureOverlay(false, epoch); // tracking: click-through from now on
    if (current(epoch)) startPolling();
  });

  function startPolling() {
    clearInterval(poll);
    const epoch = generation;
    poll = setInterval(async () => {
      const g = await trackerCall("GET", "/gaze");
      if (current(epoch) && g && Number.isFinite(g.x) && Number.isFinite(g.y)) {
        lastFeed = Date.now();
        samples += 1;
        forward(g.x, g.y);
      }
    }, 50);
  }

  async function startNative(epoch) {
    if (!proc || proc.exitCode !== null) {
      const child = spawn(trackerPython, [trackerScript, "--camera", String(cameraIndex)], { stdio: "ignore" });
      proc = child;
      child.on("exit", () => { if (proc === child) { proc = null; fail("The camera tracker stopped. You can try Recalibrate again."); } });
      child.on("error", () => { if (proc === child) fail("The camera tracker could not start. Check its Python installation."); });
    }
    let cameraReady = false;
    for (let i = 0; i < 120; i++) { // first start downloads the face model (3.6 MB)
      if (!current(epoch)) return status();
      trackerState = await trackerCall("GET", "/status");
      if (!current(epoch)) return status();
      if (["no_camera", "error"].includes(trackerState?.state)) break;
      // "ready" alone is insufficient: OpenCV may still be awaiting permission.
      cameraReady = ["ready", "calibrating", "tracking"].includes(trackerState?.state) && trackerState.fps > 0;
      if (cameraReady) break;
      await new Promise((r) => setTimeout(r, 250));
    }
    if (!current(epoch)) return status();
    if (!cameraReady) return fail(trackerState?.message || "The camera is not ready. Check its permission, then try Recalibrate again.");
    // Let the user see and confirm the camera before any calibration window appears.
    checkingCamera = true;
    return inspect();
  }

  async function inspect() {
    const epoch = generation;
    if (mode === "native" && checkingCamera && proc) {
      const camera = await trackerCall("GET", "/camera");
      if (!current(epoch)) return status();
      preview = camera?.preview || null;
      if (camera) trackerState = camera;
    }
    return status();
  }

  async function calibrate() {
    const epoch = generation;
    if (mode !== "native" || !checkingCamera || !proc || starting) return status();
    trackerState = await trackerCall("GET", "/status");
    if (!current(epoch)) return status();
    if (!trackerState?.face || !(trackerState.fps > 0)) {
      lastReason = "No face detected yet. Check the preview and face the camera before starting.";
      return status();
    }
    lastReason = null;
    const reset = await trackerCall("POST", "/calibrate/start", {});
    if (!current(epoch)) return status();
    if (!reset?.ok) return fail("The camera could not start calibration. Please try again.");
    checkingCamera = false;
    preview = null;
    clearInterval(poll);
    lastFeed = 0;
    await ensureOverlay(true, epoch);
    if (!current(epoch) || !overlay) return status();
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

  async function cameraAllowed(epoch) {
    if (process.platform !== "darwin" || mode === "browser") return true;
    const permission = systemPreferences.getMediaAccessStatus("camera");
    if (permission === "granted") return true;
    if (permission === "not-determined") {
      const granted = await systemPreferences.askForMediaAccess("camera");
      if (!current(epoch)) return false;
      if (granted) return true;
    }
    lastReason = "Camera access is off. Allow H Companion / Electron in System Settings → Privacy & Security → Camera, then try Recalibrate.";
    return false;
  }

  async function begin(epoch) {
    // Never cover a permission prompt, including when recalibrating an existing overlay.
    for (const window of [win, overlay]) {
      if (window && !window.isDestroyed()) { window.setIgnoreMouseEvents(true); window.hide(); }
    }
    overlayInteractive = null;
    const allowed = await cameraAllowed(epoch);
    if (!current(epoch)) return status();
    if (!allowed) return fail(lastReason);
    if (!server) {
      const created = await serve(heatmapDir, onFeed);
      if (!current(epoch)) { created.close(); return status(); }
      server = created;
    }
    if (mode === "native") {
      if (!pythonOk) return status();
      checkingCamera = true;
      return startNative(epoch);
    }
    if (!ready()) return status();
    if (win && !win.isDestroyed()) {
      win.setIgnoreMouseEvents(false);
      win.setFocusable(true);
      win.setAlwaysOnTop(false);
      win.show();
      return status();
    }
    const origin = `http://127.0.0.1:${server.address().port}`;
    if (mode === "browser") {
      opened = Date.now();
      await shell.openExternal(`${origin}/vision.html?feed=1`);
      return status();
    }
    const ses = session.fromPartition("gaze-calibration");
    ses.setPermissionRequestHandler((wc, permission, cb) => cb(permission === "media" && wc.getURL().startsWith(origin)));
    ses.setPermissionCheckHandler((wc, permission) => permission === "media" && (wc?.getURL() || "").startsWith(origin));
    const { workArea } = screen.getPrimaryDisplay();
    tracking = false;
    win = new BrowserWindow({
      ...workArea, title: "H Companion · Gaze calibration", frame: false, transparent: true, resizable: false, movable: false, fullscreenable: false,
      alwaysOnTop: false, skipTaskbar: false, hasShadow: false, backgroundColor: "#00000000",
      webPreferences: { preload, partition: "gaze-calibration", contextIsolation: true, sandbox: true, backgroundThrottling: false },
    });
    win.setContentProtection(true); // like the overlay: never in a screenshot, so never seen by H
    const created = win;
    installExitHandlers(created);
    created.on("closed", () => { if (win === created) { win = null; stop(); } });
    await created.loadURL(`${origin}/vision.html?embedded=1`);
    return status();
  }

  async function start(selectedCamera) {
    if (disposed) return status();
    if (selectedCamera !== undefined) {
      if (!Number.isInteger(selectedCamera) || selectedCamera < 0 || selectedCamera > 7) return status();
      if (cameraIndex !== selectedCamera) { stop(); cameraIndex = selectedCamera; }
    }
    if (starting) return starting;
    lastReason = null;
    const epoch = ++generation;
    const pending = begin(epoch);
    starting = pending;
    try { await pending; }
    catch { if (current(epoch)) fail("Calibration could not open. You can try Recalibrate again."); }
    finally { if (starting === pending) starting = null; }
    return status();
  }

  function fail(reason) {
    stop();
    lastReason = reason;
    return status();
  }

  function stop() {
    ++generation; // invalidate permission prompts, startup polling and late gaze callbacks
    starting = null;
    clearInterval(poll);
    poll = null;
    if (proc && proc.exitCode === null) {
      const p = proc;
      proc = null;
      p.kill(); // only the child we own; release the camera even during startup
    }
    proc = null;
    checkingCamera = false;
    preview = null;
    opened = 0;
    lastFeed = 0; // browser mode: the tab keeps running until the user closes it; the feed is ignored from now
    clearTimeout(overlayIdle);
    const windows = [win, overlay];
    overlay = null;
    win = null;
    overlayInteractive = null;
    for (const window of windows) {
      if (window && !window.isDestroyed()) { window.setIgnoreMouseEvents(true); window.destroy(); }
    }
    tracking = false;
    if (!disposed) onStopped();
    return status();
  }

  function dispose() {
    disposed = true;
    stop();
    if (server) server.close();
    server = null;
  }

  return { status, inspect, start, calibrate, stop, dispose, setHoneycomb };
}
