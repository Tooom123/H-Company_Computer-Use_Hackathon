import assert from "node:assert/strict";
import test from "node:test";
import { duration, headline, isBusy, keyLabel, money, planMeter, procedureName } from "../renderer/view.js";

const base = { voice: { state: null, ptt_key: "cmd+h" }, current: null };
const task = (over) => ({ ...base, current: { session_id: "s", terminal: false, takeover: false, mode: "guide", goal: "g", ...over } });

test("offline and idle", () => {
  assert.equal(headline(null).tone, "off");
  assert.deepEqual(headline(base), { text: "Ready", sub: "Hold ⌘H and say what you need", tone: "idle", pulse: false });
});

test("voice states win", () => {
  assert.equal(headline({ ...task({ state: "awaiting_user" }), voice: { state: "recording" } }).text, "Listening…");
});

test("guide step, takeover, verification, stopping", () => {
  const step = { index: 2, total: 3, instruction: "Click New" };
  assert.deepEqual(headline(task({ state: "awaiting_user", step })), { text: "Step 2 of 3", sub: "Click New", tone: "live", pulse: false });
  assert.equal(headline(task({ state: "running", takeover: true, last_action: "Typing" })).sub, "Typing");
  assert.equal(headline(task({ state: "verifying" })).text, "Checking the result…");
  assert.equal(headline(task({ state: "stopping" })).tone, "warn");
  assert.ok(isBusy(task({ state: "running" })));
});

test("terminal outcomes only claim verified when observed", () => {
  const done = (o) => headline({ ...base, current: { terminal: true, ...o } });
  assert.equal(done({ status: "resolved", verified: true }).text, "Done, result verified");
  assert.equal(done({ status: "resolved", verified: false }).text, "Ready");
  assert.equal(done({ status: "escalated", blocked_on: "Won refused" }).sub, "Won refused");
  assert.equal(done({ status: "abandoned", state: "stopped" }).text, "Stopped. Nothing else changed");
  assert.ok(!isBusy({ ...base, current: { terminal: true } }));
});

test("formatting", () => {
  assert.equal(keyLabel("ctrl+alt+space"), "⌃⌥Space");
  assert.equal(keyLabel("f9"), "F9");
  assert.equal(procedureName("odoo_crm_create_opportunity"), "Create opportunity · Odoo CRM");
  assert.equal(money(null), "—");
  assert.equal(money(0.004), "< $0.01");
  assert.equal(money(1.5), "$1.50");
  assert.equal(duration(42), "42 s");
  assert.equal(duration(125), "2 min 05");
});

test("plan credits", () => {
  const m = { sessions: 20, verified: 7 };
  assert.deepEqual(planMeter("starter", m), { used: 20, limit: 25, unit: "assisted sessions a month", ratio: 0.8 });
  assert.equal(planMeter("fixpack", m).used, 7);
  assert.equal(planMeter("pro", m).ratio, null);
  assert.equal(planMeter("starter", { sessions: 40, verified: 0 }).ratio, 1);
});
