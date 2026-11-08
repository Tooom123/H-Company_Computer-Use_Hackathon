// Builds the benchmark dataset (Electron, offscreen, 1440x900 at scale 1). Run once; the runs replay it.
//
//  Screens: the synthetic Odoo-like pages of bench/screens/ (hand-written tasks) and real public websites
//  (bench/sites.txt): each is rendered once, captured to a PNG, and every visible, clickable, unobstructed
//  element is recorded with its exact box. On real sites the tasks are drawn automatically among elements whose
//  label is unique on the page (text links / buttons, and icon buttons named by aria-label or title), spread
//  over the screen.
//
//  Gaze: for each task, draws per webcam quality (--errors, median error in px: good / fair / poor) plus
//  "looking elsewhere" draws. Gaze = target centre + 2-D gaussian noise with that median error (Rayleigh:
//  median = σ·√(2 ln 2)); elsewhere = a random point ≥ 300 px away. The crop is the REAL heatmap's ROI
//  (heatmap/gaze-heatmap.js computeHeatmap, all clickable elements as context) + margin, min size.
//  The gaze never depends on any model answer (docs/gaze-research-protocol.md).
//
//   ELECTRON_RUN_AS_NODE= electron bench/make_dataset.mjs [--errors 60,120,200] [--draws 2] [--elsewhere 1]
//        [--per-site 8] [--seed 42] [--sites bench/sites.txt] [--no-web]

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
const ERRORS = String(arg("errors", "60,120,200")).split(",").map(Number);
const DRAWS = Number(arg("draws", 2));
const ELSEWHERE = Number(arg("elsewhere", 1));
const PER_SITE = Number(arg("per-site", 8));
const SEED = Number(arg("seed", 42));
const SITES = arg("sites", path.join(here, "sites.txt"));
const WEB = !process.argv.includes("--no-web");
const OUT = path.resolve(arg("out", path.join(here, "data")));
const W = 1440;
const H = 900;
const MARGIN = 40;
const MIN_CROP = { w: 512, h: 320 };
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36";

let s = SEED;
const rand = () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
const gauss = () => Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
const shuffle = (xs) => {
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

export function cropFromRoi(roi) {
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
  const [x0, x1] = grow(roi.x - MARGIN, roi.x + roi.width + MARGIN, MIN_CROP.w, W);
  const [y0, y1] = grow(roi.y - MARGIN, roi.y + roi.height + MARGIN, MIN_CROP.h, H);
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}
const inside = (a, b) => a.x >= b.x && a.y >= b.y && a.x + a.width <= b.x + b.width && a.y + a.height <= b.y + b.height;

// In-page collector: every visible, unobstructed clickable element, with its label and kind.
const COLLECT = `(() => {
  const sel = 'a[href], button, [role=button], [role=tab], [role=menuitem], [role=link], input[type=submit], input[type=button], input[type=checkbox], input[type=radio], summary, [data-id]';
  const out = [];
  for (const e of document.querySelectorAll(sel)) {
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.width > 520 || r.height > 140) continue;
    if (r.left < 0 || r.top < 0 || r.right > innerWidth || r.bottom > innerHeight) continue;
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || Number(cs.opacity) < 0.3) continue;
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!top || !(top === e || e.contains(top) || top.contains(e))) continue; // covered (banner, overlay...)
    const text = (e.innerText || e.value || '').trim().replace(/\\s+/g, ' ');
    const named = (e.getAttribute('aria-label') || e.title || '').trim().replace(/\\s+/g, ' ');
    const role = e.matches('a, [role=link]') ? 'link' : e.matches('input[type=checkbox]') ? 'checkbox' : e.matches('[role=tab]') ? 'tab' : 'button';
    out.push({ id: e.dataset.id || null, text, named, role, rect: { x: r.left, y: r.top, width: r.width, height: r.height } });
  }
  return { elements: out, tasks: window.TASKS || null, url: location.href, title: document.title };
})()`;

function autoTasks(elements, n) {
  const key = (e) => (e.text || e.named).toLowerCase();
  const counts = new Map();
  for (const e of elements) counts.set(key(e), (counts.get(key(e)) || 0) + 1);
  const cands = elements.filter((e) => {
    const k = key(e);
    if (!k || counts.get(k) !== 1) return false; // unique label on the page, or the task is ambiguous
    if (e.text) return e.text.length >= 2 && e.text.length <= 40 && /[a-z]/i.test(e.text);
    return e.named.length >= 3 && e.named.length <= 40; // icon: no visible text, named by aria-label/title
  });
  // spread over a 3x3 grid of the screen, round robin, icons first in each cell when there are some
  const cells = new Map();
  for (const e of shuffle(cands)) {
    const c = `${Math.min(2, Math.floor((e.rect.x + e.rect.width / 2) / (W / 3)))}${Math.min(2, Math.floor((e.rect.y + e.rect.height / 2) / (H / 3)))}`;
    if (!cells.has(c)) cells.set(c, []);
    cells.get(c)[e.text ? "push" : "unshift"](e);
  }
  const picked = [];
  while (picked.length < n && [...cells.values()].some((l) => l.length)) {
    for (const l of cells.values()) if (l.length && picked.length < n) picked.push(l.shift());
  }
  return picked.map((e) => ({
    element: e,
    kind: e.text ? "text" : "icon",
    instruction: e.text ? `the "${e.text}" ${e.role}` : `the ${e.role} labelled "${e.named}" (an icon, no visible text)`,
  }));
}

const sizeClass = (r) => (Math.min(r.width, r.height) < 24 || r.width * r.height < 900 ? "small" : r.width * r.height < 6000 ? "medium" : "large");

app.commandLine.appendSwitch("force-device-scale-factor", "1");
app.setPath("userData", fs.mkdtempSync(path.join(os.tmpdir(), "hcs-bench-")));
app.whenReady().then(async () => {
  fs.mkdirSync(path.join(OUT, "screens"), { recursive: true });
  const win = new BrowserWindow({ width: W, height: H, show: false, useContentSize: true, webPreferences: { offscreen: true, javascript: true } });
  win.webContents.setUserAgent(UA);
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  const sources = fs.readdirSync(path.join(here, "screens")).filter((f) => f.endsWith(".html")).sort()
    .map((f) => ({ name: f.replace(/\.html$/, ""), kind: "synthetic", load: () => win.loadFile(path.join(here, "screens", f)) }));
  if (WEB && fs.existsSync(SITES)) {
    for (const line of fs.readFileSync(SITES, "utf8").split("\n")) {
      const [name, url] = line.trim().split(/\s+/);
      if (!name || name.startsWith("#") || !url) continue;
      sources.push({ name, kind: "web", url, load: () => win.loadURL(url) });
    }
  }
  const screens = [];
  const tasks = [];
  const trials = [];
  for (const src of sources) {
    try {
      await Promise.race([src.load(), new Promise((_, rej) => setTimeout(() => rej(new Error("load timeout")), 25000))]);
    } catch (e) {
      if (!String(e).includes("ERR_ABORTED")) { console.log(`skip ${src.name}: ${e.message || e}`); continue; }
    }
    await new Promise((r) => setTimeout(r, src.kind === "web" ? 3500 : 400)); // late fonts, banners, images
    await win.webContents.executeJavaScript("window.scrollTo(0, 0)");
    await new Promise((r) => setTimeout(r, 300));
    const page = await win.webContents.executeJavaScript(COLLECT);
    const img = await win.webContents.capturePage();
    const { width: iw, height: ih } = img.getSize();
    if (iw !== W || ih !== H) { console.log(`skip ${src.name}: captured ${iw}x${ih}`); continue; }
    const elements = page.elements;
    let picked;
    if (src.kind === "synthetic") {
      picked = page.tasks.map((t) => {
        const e = elements.find((x) => x.id === t.target);
        if (!e) throw new Error(`${src.name}: no element ${t.target}`);
        return { element: e, kind: e.text ? "text" : "icon", instruction: t.instruction };
      });
    } else {
      picked = autoTasks(elements, PER_SITE);
    }
    if (picked.length < 3) { console.log(`skip ${src.name}: only ${picked.length} usable targets`); continue; }
    fs.writeFileSync(path.join(OUT, "screens", `${src.name}.png`), img.toPNG());
    screens.push({ name: src.name, kind: src.kind, url: src.url || null, title: page.title, file: `screens/${src.name}.png`, width: W, height: H, n_elements: elements.length });
    const context = elements.map((e, i) => ({ id: `e${i}`, rect: e.rect }));
    picked.forEach((p, ti) => {
      const r = p.element.rect;
      const task = { id: `${src.name}-${ti}`, screen: src.name, site_kind: src.kind, instruction: p.instruction, target_kind: p.kind,
        size: sizeClass(r), target_rect: r, label: p.element.text || p.element.named };
      tasks.push(task);
      const cx = r.x + r.width / 2;
      const cy = r.y + r.height / 2;
      const draw = (condition, errorPx, elsewhere) => {
        let gx;
        let gy;
        if (elsewhere) {
          do {
            gx = 40 + rand() * (W - 80);
            gy = 40 + rand() * (H - 80);
          } while (Math.hypot(gx - cx, gy - cy) < 300);
        } else {
          const sd = errorPx / Math.sqrt(2 * Math.LN2);
          gx = Math.min(W - 1, Math.max(0, cx + gauss() * sd));
          gy = Math.min(H - 1, Math.max(0, cy + gauss() * sd));
        }
        const sigma = Math.min(DEFAULTS.sigmaMax, Math.max(DEFAULTS.sigmaMin, errorPx));
        const heat = computeHeatmap({ x: gx, y: gy }, sigma, context, { ...DEFAULTS, bounds: { x: 0, y: 0, width: W, height: H } });
        const crop = cropFromRoi(heat.roi);
        trials.push({ id: `${task.id}-${condition}-${trials.filter((t) => t.task === task.id && t.condition === condition).length}`,
          task: task.id, condition, error_px: errorPx, elsewhere,
          gaze: { x: Math.round(gx), y: Math.round(gy), off_px: Math.round(Math.hypot(gx - cx, gy - cy)) },
          crop, target_in_crop: inside(r, crop) });
      };
      for (const e of ERRORS) for (let d = 0; d < DRAWS; d++) draw(`gaze${e}`, e, false);
      for (let d = 0; d < ELSEWHERE; d++) draw("elsewhere", ERRORS[Math.floor(ERRORS.length / 2)], true);
    });
    console.log(`${src.name.padEnd(14)} ${src.kind.padEnd(9)} ${String(elements.length).padStart(4)} clickable, ${picked.length} tasks (${picked.filter((p) => p.kind === "icon").length} icons)`);
  }
  const meta = { errors_px: ERRORS, draws: DRAWS, elsewhere: ELSEWHERE, per_site: PER_SITE, seed: SEED, margin_px: MARGIN, min_crop: MIN_CROP,
    screen: [W, H], heatmap: { sigmaMin: DEFAULTS.sigmaMin, sigmaMax: DEFAULTS.sigmaMax, roiMass: DEFAULTS.roiMass }, created_at: new Date().toISOString() };
  fs.writeFileSync(path.join(OUT, "dataset.json"), JSON.stringify({ meta, screens, tasks, trials }, null, 1));
  const inCrop = trials.filter((t) => !t.elsewhere && t.target_in_crop).length;
  console.log(`\n${screens.length} screens, ${tasks.length} tasks, ${trials.length} gaze trials; target in crop (looking at it): ${inCrop}/${trials.filter((t) => !t.elsewhere).length}`);
  app.quit();
});
