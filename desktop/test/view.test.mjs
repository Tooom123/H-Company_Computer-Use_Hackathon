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
