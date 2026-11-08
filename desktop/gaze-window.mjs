// Built-in gaze calibration and tracking (Tom), for any computer where Édouard's Vision Lab cannot run (it needs
// macOS for its native capture helper). It opens the webcam vision page (heatmap/vision.html: WebGazer + MediaPipe,
// local copies, Édouard's calibration grid) in a full-screen window. After calibration the window turns transparent,
// lets every click through, stays invisible to screen capture, and keeps tracking: each gaze point (screen points,
// no image) goes to the agent's control point (POST /gaze), so the agent can crop its screenshots around it.

import { BrowserWindow, ipcMain, screen, session, shell } from "electron";
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

export function createGazeCalibrator({ heatmapDir, agentUrl, preload }) {
  let win = null;
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
  const mode = process.platform === "linux" && process.env.HCS_VISION_WINDOW !== "electron" ? "browser" : "electron";
  const onFeed = (url, d) => {
    if (url === "/accuracy" && Number.isFinite(d.px) && d.px > 0) errorPx = Math.round(d.px);
    if (url === "/gaze" && opened && Number.isFinite(d.x) && Number.isFinite(d.y)) {
      lastFeed = Date.now();
      samples += 1;
      forward(d.x, d.y); // full screen in the browser: page coordinates are screen coordinates
    }
  };

  const ready = () => fs.existsSync(path.join(heatmapDir, "vision.html")) && fs.existsSync(path.join(heatmapDir, "vendor", "webgazer.js"));

  function status() {
    if (!ready()) return { available: false, running: false, builtin: true, reason: "Run `npm install && npm run assets` in heatmap/ once (local WebGazer)." };
    if (mode === "browser") {
      const live = Date.now() - lastFeed < 3000;
      return { available: true, running: live || Date.now() - opened < 120000, tracking: live, builtin: true, browser: true, errorPx, samples };
    }
    return { available: true, running: Boolean(win && !win.isDestroyed()), tracking, builtin: true, errorPx, samples };
  }

  function forward(x, y) {
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
    opened = 0;
    lastFeed = 0; // browser mode: the tab keeps running until the user closes it; the feed is ignored from now
    if (win && !win.isDestroyed()) win.destroy(); // the page's unload stops the camera
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
