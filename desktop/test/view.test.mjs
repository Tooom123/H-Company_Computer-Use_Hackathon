import assert from "node:assert/strict";
import test from "node:test";
import { duration, headline, isBusy, keyLabel, procedureName } from "../renderer/view.js";
import { circlePoints, rng, wobble } from "../renderer/magnet.js";

const base = { voice: { state: null, ptt_key: "cmd+h" }, current: null };
const task = (over) => ({ ...base, current: { session_id: "s", terminal: false, takeover: false, mode: "guide", goal: "g", ...over } });

test("offline and idle", () => {
  assert.equal(headline(null).tone, "off");
  assert.deepEqual(headline(base), { text: "Ready", sub: "Hold ⌘H and say what you need", tone: "idle", pulse: false });
  assert.equal(headline({ ...base, voice: { ptt_key: "alt_r" } }).sub, "Hold Right ⌥ and say what you need");
});

test("voice states win", () => {
  assert.equal(headline({ ...task({ state: "awaiting_user" }), voice: { state: "recording" } }).text, "Listening…");
});

test("guide step, takeover, verification, stopping", () => {
  const step = { index: 2, total: 3, instruction: "Click New" };
  assert.deepEqual(headline(task({ state: "awaiting_user", step })), { text: "Your turn · step 2 of 3", sub: "Click New", tone: "live", pulse: false });
  assert.equal(headline(task({ state: "running", takeover: true, last_action: "Typing" })).sub, "Typing");
  assert.equal(headline(task({ state: "verifying" })).text, "Checking it worked…");
  assert.equal(headline(task({ state: "stopping" })).tone, "warn");
  assert.ok(isBusy(task({ state: "running" })));
});

test("end of a task says what happened, and only claims checked when observed", () => {
  const done = (o) => headline({ ...base, current: { terminal: true, goal: "Log a note", ...o } });
  assert.deepEqual(done({ status: "resolved", verified: true }), { text: "Done ✓", sub: "“Log a note” is done: I checked it in the software", tone: "done", pulse: false });
  assert.equal(done({ status: "resolved", verified: false }).tone, "warn");
  assert.equal(done({ status: "escalated", blocked_on: "Won refused" }).sub, "I could not finish: Won refused");
  assert.equal(done({ status: "abandoned", state: "stopped" }).text, "Stopped");
  assert.ok(!isBusy({ ...base, current: { terminal: true } }));
});

test("formatting", () => {
  assert.equal(keyLabel("ctrl+alt+space"), "⌃⌥Space");
  assert.equal(keyLabel("f9"), "F9");
  assert.equal(keyLabel("cmd+j"), "⌘J");
  assert.equal(procedureName("odoo_crm_create_opportunity"), "Create opportunity · Odoo CRM");
  assert.equal(duration(42), "42 s");
  assert.equal(duration(125), "2 min 05");
});

test("magnet strokes: deterministic pencil, two passes, overshooting loop", () => {
  const a = wobble([[0, 0], [10, 0]], rng(7), 1);
  const b = wobble([[0, 0], [10, 0]], rng(7), 1);
  assert.deepEqual(a, b);
  assert.equal(a.length, 2);
  assert.notEqual(a[0], a[1]);
  const pts = circlePoints(0, 0, 10, 10);
  assert.equal(pts.length, 40);
  assert.ok(Math.abs(pts[0][0] - pts[39][0]) > 0.1 || Math.abs(pts[0][1] - pts[39][1]) > 0.1);
});
