import assert from "node:assert/strict";
import test from "node:test";
import { duration, isBusy, keyLabel, procedureName, readyBadge, taskLine } from "../renderer/view.js";
import { circlePoints, paperPoints, rng, wobble } from "../renderer/sketch.js";

test("ready badge: the on-screen words, Listening only while the key is held", () => {
  assert.deepEqual(readyBadge({ voice: { ptt_key: "cmd+h" } }), { text: "⌘H: new request", pulse: false });
  assert.equal(readyBadge({ voice: { ptt_key: "alt_r" } }).text, "Right ⌥: new request");
  assert.deepEqual(readyBadge({ voice: { state: "recording" } }), { text: "Listening…", pulse: true });
  assert.equal(readyBadge({ voice: { state: "transcribed" } }).text, "⌘H: new request");
  assert.equal(readyBadge(null).text, "⌘H: new request");
});

test("task line says plainly who does what", () => {
  const step = { index: 2, total: 4, instruction: "Click New" };
  assert.equal(taskLine({ state: "awaiting_user", step }), "Now you: Click New");
  assert.equal(taskLine({ state: "running", takeover: true, last_action: "Typing the name" }), "I'm doing it: Typing the name");
  assert.equal(taskLine({ state: "running" }), "Looking at your screen…");
  assert.equal(taskLine({ state: "verifying" }), "Checking in the software that it worked…");
  assert.equal(taskLine(null), "");
  assert.ok(isBusy({ current: { terminal: false } }));
  assert.ok(!isBusy({ current: { terminal: true } }));
});

test("formatting", () => {
  assert.equal(keyLabel("ctrl+alt+space"), "⌃⌥Space");
  assert.equal(keyLabel("f9"), "F9");
  assert.equal(keyLabel("cmd+j"), "⌘J");
  assert.equal(procedureName("odoo_crm_create_opportunity"), "Create opportunity · Odoo CRM");
  assert.equal(duration(42), "42 s");
  assert.equal(duration(125), "2 min 05");
});

test("pencil like the overlay: deterministic, two passes, overshooting loop, rough paper", () => {
  assert.deepEqual(wobble([[0, 0], [10, 0]], rng(7), 1), wobble([[0, 0], [10, 0]], rng(7), 1));
  const [a, b] = wobble([[0, 0], [10, 0]], rng(7), 1);
  assert.notEqual(a, b);
  const pts = circlePoints(0, 0, 8, 7);
  assert.equal(pts.length, 40);
  const paper = paperPoints(0, 0, 200, 40, rng(11));
  assert.equal(paper.length, 16);
  for (const [x, y] of paper) assert.ok(x > -10 && x < 210 && y > -10 && y < 50);
});

test("the stick figure's waving hand never passes over its head", async () => {
  const { readFile } = await import("node:fs/promises");
  const html = await readFile(new URL("../renderer/index.html", import.meta.url), "utf8");
  const css = await readFile(new URL("../renderer/style.css", import.meta.url), "utf8");
  const head = html.match(/<path d="(M24\.5 9\.6[^"]+)"/)[1].match(/-?\d+(\.\d+)?/g).map(Number);
  const hx = head.filter((_, i) => i % 2 === 0);
  const hy = head.filter((_, i) => i % 2 === 1);
  const box = { x0: Math.min(...hx) - 1, x1: Math.max(...hx) + 1, y0: Math.min(...hy) - 1, y1: Math.max(...hy) + 1 };
  const arm = html.match(/<g class="wave"><path d="([^"]+)"/)[1].match(/-?\d+(\.\d+)?/g).map(Number);
  const [p0, p1, p2, p3] = [0, 2, 4, 6].map((i) => [arm[i], arm[i + 1]]);
  const origin = css.match(/\.buddy \.wave \{[^}]*transform-origin: ([\d.]+)px ([\d.]+)px/).slice(1).map(Number);
  const angles = [...css.match(/@keyframes wave \{([^\n]+)\n/)[1].matchAll(/rotate\((-?[\d.]+)deg\)/g)].map((m) => Number(m[1]));
  const lo = Math.min(0, ...angles);
  const hi = Math.max(0, ...angles);
  for (let a = lo; a <= hi; a += 0.5) {
    const rad = (a * Math.PI) / 180;
    for (let t = 0.15; t <= 1; t += 0.05) { // the shoulder (t = 0) touches the neck, by design
      const u = 1 - t;
      const x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0];
      const y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1];
      const dx = x - origin[0];
      const dy = y - origin[1];
      const rx = origin[0] + dx * Math.cos(rad) - dy * Math.sin(rad);
      const ry = origin[1] + dx * Math.sin(rad) + dy * Math.cos(rad);
      assert.ok(!(rx > box.x0 && rx < box.x1 && ry > box.y0 && ry < box.y1), `arm over the head at ${a}° (t=${t.toFixed(2)})`);
    }
  }
});
