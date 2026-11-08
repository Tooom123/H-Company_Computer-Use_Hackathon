// Standalone renderer QA, with a loopback fixture only. No Electron IPC, credentials, H, or audio.
// Run after app/ dev dependencies are installed: node desktop/test/step-reply.ui.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const { chromium, expect } = createRequire(path.join(root, "app/package.json"))("@playwright/test");
const step = (index = 2) => ({ index, total: 4, instruction: "Ouvre la documentation — simulation." });
const current = () => ({ session_id: "simulated-step-session", terminal: false, state: "awaiting_user",
  step: step(), mode: "guide", procedure_id: "hcompany_general_guide", goal: "Essai UI simulé" });
const state = {
  online: true,
  status: { agent: { command: "talk", simulated: true, observe_only: true }, autonomy: 0,
    voice: { state: null, ptt_key: "ctrl+shift+h" },
    speech: { available: true, enabled: true, provider: "elevenlabs", voice: "EXAVITQu4vr4xnSDxMaL", speed: 1 },
    current: current() },
  nextCalls: [], voiceCalls: [], feedbackCalls: [], holdNext: false, releaseNext: null, nextStatus: 200,
  feedback: { session_id: "simulated-step-session", available: false, saved: false, comment: "", dictation_armed: false },
};
const checks = [];
const server = http.createServer(async (req, res) => {
  const reply = (code, data) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(data)); };
  if (req.url.startsWith("/fixture/")) {
    let raw = "";
    for await (const chunk of req) raw += chunk;
    const body = raw ? JSON.parse(raw) : undefined;
    const name = req.url.slice("/fixture".length);
    if (name === "/status") return reply(state.online ? 200 : 503, state.online ? state.status : {});
    if (name === "/next") {
      state.nextCalls.push({ method: req.method, path: name, body });
      if (state.holdNext) await new Promise((resolve) => { state.releaseNext = resolve; });
      return reply(state.nextStatus, state.nextStatus === 409 ? { error: "Step changed" } : { accepted: true });
    }
    if (name === "/voice" || name === "/voice/test") {
      state.voiceCalls.push({ method: req.method, path: name, body });
      if (typeof body?.enabled === "boolean") state.status.speech.enabled = body.enabled;
      return reply(200, name === "/voice/test" ? { requested: true } : state.status.speech);
    }
    if (name === "/feedback") {
      if (req.method === "POST") { state.feedbackCalls.push(body); state.feedback.saved = true; }
      return reply(200, state.feedback);
    }
    if (name === "/feedback/dictate") {
      state.feedback.dictation_armed = true;
      return reply(200, state.feedback);
    }
    if (name === "/usage") return reply(200, { month: { month: "2026-11", sessions: 0, verified: 0, h_spend_usd: 0, h_cost_per_session_usd: null }, configured: {} });
    if (name === "/sessions") return reply(200, { sessions: [] });
    return reply(404, { error: "Unexpected fixture route" });
  }
  const name = req.url === "/" ? "index.html" : req.url.slice(1);
  if (!["index.html", "app.js", "view.js", "style.css", "companion.svg"].includes(name)) return reply(404, {});
  const mime = name.endsWith(".js") ? "text/javascript" : name.endsWith(".css") ? "text/css" : name.endsWith(".svg") ? "image/svg+xml" : "text/html";
  res.writeHead(200, { "Content-Type": mime });
  res.end(fs.readFileSync(path.join(root, "desktop/renderer", name)));
});

let browser;
try {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({ viewport: { width: 1100, height: 850 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => route.request().url().startsWith(`${base}/`) ? route.continue() : route.abort());
  // The real app's CSP forbids renderer fetch. Mimic its privileged IPC bridge;
  // only this fixture host, and never a user-supplied URL, is reachable here.
  await page.exposeFunction("fixtureAgent", async (method, target, body) => {
    const response = await fetch(`${base}/fixture${target}`, { method,
      headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { ok: response.ok, status: response.status, data: await response.json() };
  });
  await page.addInitScript(() => {
    window.hcs = {
      agent: (method, path, body) => window.fixtureAgent(method, path, body),
      vision: { status: async () => ({ available: false }) },
      plans: async () => ({ ok: true, data: [] }), openDashboard: () => {}, openCase: () => {},
    };
  });
  await page.goto(base);
  await expect(page.locator("#stepReply")).toBeVisible();
  checks.push("awaiting_user displays step controls");

  state.holdNext = true;
  await page.evaluate(() => { document.querySelector("#stepDone").click(); document.querySelector("#stepDone").click(); });
  await expect.poll(() => state.nextCalls.length).toBe(1);
  await expect(page.locator("#stepDone")).toBeDisabled();
  await expect(page.locator("#stepStuck")).toBeDisabled();
  assert.deepEqual(state.nextCalls[0], { method: "POST", path: "/next",
    body: { session_id: "simulated-step-session", step_index: 2, done: true } });
  state.holdNext = false;
  state.releaseNext();
  await expect(page.locator("#stepDone")).toBeEnabled();
  checks.push("done request is correlated and double click suppressed while pending");

  await page.locator("#stepStuck").click();
  await expect.poll(() => state.nextCalls.length).toBe(2);
  assert.deepEqual(state.nextCalls[1].body, { session_id: "simulated-step-session", step_index: 2, done: false });
  await expect(page.locator("#stepDone")).toBeEnabled();
  checks.push("stuck sends done=false with the same session and step");

  state.nextStatus = 409;
  await page.locator("#stepDone").click();
  await expect(page.locator("#stepReplyMessage")).toHaveText("L’étape a changé. Vérifie la consigne actuelle.");
  await expect(page.locator("#stepReplyMessage")).toBeVisible();
  await expect(page.locator("#stepDone")).toBeEnabled();
  checks.push("409 stays visible and allows retry");
  state.nextStatus = 200;

  for (const [name, headline] of [["running", "Looking at the screen…"],
    ["verifying", "Checking the result…"], ["stopping", "Stopping…"],
    ["awaiting_approval", "Waiting for your approval"]]) {
    state.status.current.state = name;
    await expect(page.locator("#pillText")).toHaveText(headline);
    await expect(page.locator("#stepReply")).toBeHidden();
  }
  state.status.current = { ...current(), step: null };
  await expect(page.locator("#pillText")).toHaveText("Your turn");
  await expect(page.locator("#stepReply")).toBeHidden();
  state.status.current = { ...current(), terminal: true, state: "resolved", status: "resolved", verified: true };
  await expect(page.locator("#pillText")).toHaveText("Done, result verified");
  await expect(page.locator("#stepReply")).toBeHidden();
  state.online = false;
  await expect(page.locator("#offline")).toBeVisible();
  await expect(page.locator("#stepReply")).toBeHidden();
  checks.push("controls hidden for other states, missing step, terminal, and offline");

  state.online = true;
  state.status.current = current();
  await expect(page.locator("#stepReply")).toBeVisible();
  await page.locator('nav button[data-go="voice"]').click();
  await expect(page.locator("#ttsNote")).toContainText("ElevenLabs");
  await expect(page.locator("#testVoice")).toBeEnabled();
  await page.locator("#testVoice").click();
  await expect.poll(() => state.voiceCalls.some((call) => call.path === "/voice/test")).toBe(true);
  await page.locator("#ttsSwitch").click();
  await expect(page.locator("#testVoice")).toBeDisabled();
  state.status.speech = { available: true, enabled: true, provider: "macos", voice: "Thomas", speed: 1 };
  await expect(page.locator("#ttsNote")).toContainText("Thomas");
  await expect(page.locator("#voices .voice").first()).toBeDisabled();
  await expect(page.locator("#testVoice")).toBeEnabled();
  checks.push("voice test, mute, and local-provider display still work");

  state.status.current = { ...current(), terminal: true, state: "resolved", status: "resolved", verified: true };
  state.feedback.available = true;
  await page.locator('nav button[data-go="feedback"]').click();
  await expect(page.locator("#feedbackDictate")).toBeEnabled();
  await expect(page.locator("#feedbackSave")).toBeDisabled();
  await page.locator("#feedbackDictate").click();
  state.feedback.dictation_armed = false;
  state.feedback.comment = "Retour simulé transcrit.";
  await expect(page.locator("#feedbackComment")).toHaveValue("Retour simulé transcrit.");
  await page.locator("#feedbackComment").fill("Retour relu, simulation uniquement.");
  await page.waitForTimeout(1100);
  await expect(page.locator("#feedbackComment")).toHaveValue("Retour relu, simulation uniquement.");
  await page.locator("#feedbackSuccess").selectOption("partial");
  await page.locator("#feedbackUseful").selectOption("yes");
  await page.locator("#feedbackSave").click();
  await expect.poll(() => state.feedbackCalls.length).toBe(1);
  assert.equal(state.feedbackCalls[0].session_id, "simulated-step-session");
  assert.equal(state.feedbackCalls[0].success, "partial");
  assert.equal(state.feedbackCalls[0].useful, "yes");
  assert.equal(state.feedbackCalls[0].confirmed_by_human, true);
  assert.equal(state.feedbackCalls[0].training_consent, false);
  checks.push("feedback dictation, edited draft, and explicit labels preserved");
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ passed: true, simulated: true, checks, page_errors: errors.length,
    limits: "Renderer + fixture HTTP only; Electron hide/show and live engine not tested." }, null, 2));
} finally {
  state.releaseNext?.();
  if (browser) await browser.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
