// H Companion desktop app — main process.
// The window is the assistant's home: live status, autonomy, voice, usage and plan, vision.
// It talks to the running agent (`hcs-agent talk`) on 127.0.0.1:8768 and to the support backend on :8766.
// No key ever lives here: the agent and the backend keep them; the renderer only sees JSON via IPC.

import { app, BrowserWindow, ipcMain, shell } from "electron";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const AGENT = process.env.HCS_CONTROL_URL || "http://127.0.0.1:8768";
const BACKEND = process.env.HCS_BACKEND_URL || "http://127.0.0.1:8766";
const VISION_DIR = path.resolve(here, "..", "app"); // Édouard's Vision Lab
const AGENT_PATHS = /^\/(status|sessions|usage|autonomy|stop|voice|voice\/test)$/;
const PLANS = new Set(["pro", "fixpack"]);

const smoke = process.argv.includes("--smoke");
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

ipcMain.handle("agent", (_e, method, p, body) => {
  if (!["GET", "POST"].includes(method) || typeof p !== "string" || !AGENT_PATHS.test(p)) {
    return { ok: false, status: 400, data: { error: "not allowed" } };
  }
  return call(AGENT, method, p, method === "POST" ? body ?? {} : undefined, { "X-HCS-App": "1" });
});

ipcMain.handle("plans", () => call(BACKEND, "GET", "/billing/plans"));

ipcMain.handle("checkout", async (_e, plan) => {
  if (!PLANS.has(plan)) return { ok: false, error: "unknown plan" };
  const r = await call(BACKEND, "POST", "/billing/checkout", { plan });
  const url = r.data && r.data.url;
  if (r.ok && typeof url === "string" && url.startsWith("https://checkout.stripe.com/")) {
    await shell.openExternal(url);
    return { ok: true };
  }
  if (r.offline) return { ok: false, error: "Support backend offline: run hcs-backend serve" };
  if (r.status === 503) return { ok: false, error: "Stripe is not set up: add a test key in backend/.env" };
  return { ok: false, error: `Checkout failed (${r.status})` };
});

ipcMain.handle("open-case", (_e, caseId) => {
  if (typeof caseId !== "string" || !/^[\w-]{1,80}$/.test(caseId)) return false;
  shell.openExternal(`${BACKEND}/dashboard/cases/${caseId}`);
  return true;
});

ipcMain.handle("open-dashboard", () => {
  shell.openExternal(`${BACKEND}/dashboard`);
  return true;
});

// Vision Lab (Édouard): started as its own process from app/, stopped with this app.
let vision = null;
function visionStatus() {
  if (!fs.existsSync(path.join(VISION_DIR, "package.json"))) {
    return { available: false, running: false, reason: "app/ (Vision Lab) is not in this checkout" };
  }
  if (!fs.existsSync(path.join(VISION_DIR, "node_modules"))) {
    return { available: false, running: false, reason: "Run `npm ci` in app/ once" };
  }
  return { available: true, running: Boolean(vision && vision.exitCode === null) };
}
ipcMain.handle("vision:status", () => visionStatus());
ipcMain.handle("vision:start", () => {
  const s = visionStatus();
  if (!s.available || s.running) return s;
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE; // the lab is a full Electron app of its own
  vision = spawn(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "dev"], {
    cwd: VISION_DIR,
    stdio: "ignore",
    env,
  });
  vision.on("exit", () => (vision = null));
  return { ...visionStatus(), running: true };
});
ipcMain.handle("vision:stop", () => {
  if (vision && vision.exitCode === null) vision.kill();
  return { ...visionStatus(), running: false };
});

function createWindow() {
  const win = new BrowserWindow({
    width: 940,
    height: 640,
    minWidth: 780,
    minHeight: 540,
    title: "H Companion",
    backgroundColor: "#f9f9fb",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    show: !smoke,
    webPreferences: {
      preload: path.join(here, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (e) => e.preventDefault());
  win.loadFile(path.join(here, "renderer", "index.html"), { hash: section });

  if (smoke) {
    // `npm run smoke -- --section=usage`: render, capture a PNG, quit (used to check the UI without a Mac).
    win.webContents.once("did-finish-load", () => {
      setTimeout(async () => {
        if (process.env.HCS_SMOKE_JS) {
          // e.g. click a control, then capture what the app shows after the agent answered
          await win.webContents.executeJavaScript(process.env.HCS_SMOKE_JS);
          await new Promise((r) => setTimeout(r, 1800));
        }
        const img = await win.webContents.capturePage();
        const out = process.env.HCS_SMOKE_OUT || path.join(here, `smoke-${section}.png`);
        fs.writeFileSync(out, img.toPNG());
        console.log(`smoke: wrote ${out}`);
        app.quit();
      }, Number(process.env.HCS_SMOKE_WAIT_MS || 2500));
    });
  }
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit()); // closing the window gives the Magnet back to the screen
app.on("before-quit", () => {
  if (vision && vision.exitCode === null) vision.kill();
});
