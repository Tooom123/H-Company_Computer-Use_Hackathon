// Builds the benchmark dataset (run with Electron, offscreen):
//   1. renders each screen of bench/screens/ at 1440x900 to a PNG, with the exact box of every clickable
//      element (data-id) and the tasks (window.TASKS: which element, in words);
//   2. for each task and repeat, draws a gaze point the way a webcam tracker would give it: the target's
//      centre + noise whose median error is the one measured on the vision page (--error-px), or, with
//      probability --miss-rate, a point elsewhere (the user was looking at something else);
//   3. computes the crop to send with the REAL heatmap (heatmap/gaze-heatmap.js, computeHeatmap → roi),
//      widened by a margin and to a minimum size.
// The gaze is decided before any model call and never uses the model's answer (docs/gaze-research-protocol.md).
//
//   ELECTRON_RUN_AS_NODE= electron bench/make_dataset.mjs [--error-px 120] [--repeats 3] [--miss-rate 0.1] [--seed 42]

import { app, BrowserWindow } from "electron";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { computeHeatmap, DEFAULTS } = await import(pathToFileURL(path.join(here, "..", "heatmap", "gaze-heatmap.js")).href);

const arg = (name, dflt) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : dflt;
};
const ERROR_PX = Number(arg("error-px", 120)); // median gaze error measured on the vision page
const REPEATS = Number(arg("repeats", 3));
const MISS_RATE = Number(arg("miss-rate", 0.1));
const SEED = Number(arg("seed", 42));
const OUT = path.resolve(arg("out", path.join(here, "data")));
const W = 1440;
const H = 900;
const MARGIN = 40; // px added around the heatmap ROI
const MIN_CROP = { w: 512, h: 320 }; // never send less than this

let s = SEED;
const rand = () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
const gauss = () => Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
// 2-D gaussian noise: the radial distance follows a Rayleigh law, median = σ·√(2 ln 2).
const SIGMA_NOISE = ERROR_PX / Math.sqrt(2 * Math.LN2);

export function cropFromRoi(roi) {
  let x0 = roi.x - MARGIN;
  let y0 = roi.y - MARGIN;
  let x1 = roi.x + roi.width + MARGIN;
  let y1 = roi.y + roi.height + MARGIN;
  const grow = (lo, hi, min, max) => {
    const need = min - (hi - lo);
    if (need > 0) {
      lo -= need / 2;
      hi += need / 2;
    }
    if (lo < 0) [lo, hi] = [0, hi - lo];
    if (hi > max) [lo, hi] = [Math.max(0, lo - (hi - max)), max];
    return [Math.round(lo), Math.round(hi)];
  };
  [x0, x1] = grow(x0, x1, MIN_CROP.w, W);
  [y0, y1] = grow(y0, y1, MIN_CROP.h, H);
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}

const contains = (r, x, y) => x >= r.x && x <= r.x + r.width && y >= r.y && y <= r.y + r.height;
const inside = (inner, outer) =>
  inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;

app.commandLine.appendSwitch("force-device-scale-factor", "1");
app.setPath("userData", fs.mkdtempSync(path.join(os.tmpdir(), "hcs-bench-")));
app.whenReady().then(async () => {
  fs.mkdirSync(path.join(OUT, "screens"), { recursive: true });
  const win = new BrowserWindow({ width: W, height: H, show: false, useContentSize: true, webPreferences: { offscreen: true } });
  const screens = [];
  const trials = [];
  for (const file of fs.readdirSync(path.join(here, "screens")).filter((f) => f.endsWith(".html")).sort()) {
    const name = file.replace(/\.html$/, "");
    await win.loadFile(path.join(here, "screens", file));
    await new Promise((r) => setTimeout(r, 400));
    const page = await win.webContents.executeJavaScript(`({
      size: [innerWidth, innerHeight],
      tasks: window.TASKS,
      elements: [...document.querySelectorAll("[data-id]")].map((e) => {
        const r = e.getBoundingClientRect();
        return { id: e.dataset.id, label: (e.title || e.textContent || "").trim().slice(0, 40), rect: { x: r.x, y: r.y, width: r.width, height: r.height } };
      }),
    })`);
    const img = await win.webContents.capturePage();
    const png = img.toPNG();
    fs.writeFileSync(path.join(OUT, "screens", `${name}.png`), png);
    const { width: iw, height: ih } = img.getSize();
    if (iw !== W || ih !== H) throw new Error(`${name}: captured ${iw}x${ih}, expected ${W}x${H}`);
    screens.push({ name, file: `screens/${name}.png`, width: iw, height: ih, elements: page.elements });
    const targets = page.elements.map((e) => ({ id: e.id, rect: e.rect, label: e.label }));

    for (const task of page.tasks) {
      const el = page.elements.find((e) => e.id === task.target);
      if (!el) throw new Error(`${name}: no element ${task.target}`);
      const cx = el.rect.x + el.rect.width / 2;
      const cy = el.rect.y + el.rect.height / 2;
      for (let rep = 0; rep < REPEATS; rep++) {
        const miss = rand() < MISS_RATE;
        let gx;
        let gy;
        if (miss) { // looking somewhere else on the screen, at least 300 px away
          do {
            gx = 40 + rand() * (W - 80);
            gy = 40 + rand() * (H - 80);
          } while (Math.hypot(gx - cx, gy - cy) < 300);
        } else {
          gx = Math.min(W - 1, Math.max(0, cx + gauss() * SIGMA_NOISE));
          gy = Math.min(H - 1, Math.max(0, cy + gauss() * SIGMA_NOISE));
        }
        const sigma = Math.min(DEFAULTS.sigmaMax, Math.max(DEFAULTS.sigmaMin, ERROR_PX));
        const heat = computeHeatmap({ x: gx, y: gy }, sigma, targets, { ...DEFAULTS, bounds: { x: 0, y: 0, width: W, height: H } });
        const crop = cropFromRoi(heat.roi);
        trials.push({
          id: `${name}-${task.target}-${rep}`,
          screen: name,
          target: task.target,
          instruction: task.instruction,
          target_rect: el.rect,
          gaze: { x: Math.round(gx), y: Math.round(gy), error_px: Math.round(Math.hypot(gx - cx, gy - cy)), miss },
          sigma,
          heat_best: heat.best?.id ?? null,
          roi: heat.roi,
          crop,
          target_in_crop: inside(el.rect, crop),
          target_centre_in_crop: contains(crop, cx, cy),
        });
      }
    }
  }
  const meta = { error_px: ERROR_PX, repeats: REPEATS, miss_rate: MISS_RATE, seed: SEED, margin_px: MARGIN, min_crop: MIN_CROP, screen: [W, H], heatmap: { sigmaMin: DEFAULTS.sigmaMin, roiMass: DEFAULTS.roiMass }, created_at: new Date().toISOString() };
  fs.writeFileSync(path.join(OUT, "dataset.json"), JSON.stringify({ meta, screens, trials }, null, 2));
  const ok = trials.filter((t) => t.target_in_crop).length;
  console.log(`${screens.length} screens, ${trials.length} trials (gaze error ${ERROR_PX} px, miss ${MISS_RATE}): target fully inside the crop in ${ok}/${trials.length}`);
  app.quit();
});
