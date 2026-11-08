// Pure formatting for the UI (no DOM): what to say about the agent's state. Tested with `node --test`.

export const PLANS = {
  starter: { name: "Starter", price: "€0", per: "/ month", quota: 25, unit: "assisted sessions a month" },
  pro: { name: "Pro", price: "€49", per: "/ month", quota: null, unit: "unlimited assisted sessions" },
  fixpack: { name: "Fix pack", price: "€79", per: "one-time", quota: 100, unit: "verified fixes" },
};

export function keyLabel(key) {
  if (!key) return "⌘H";
  return key
    .split("+")
    .map((k) => ({ cmd: "⌘", ctrl: "⌃", alt: "⌥", shift: "⇧", space: "Space" })[k.toLowerCase()] || k.toUpperCase())
    .join("");
}

export function procedureName(id) {
  if (!id) return "";
  const soft = id.startsWith("odoo_crm_") ? "Odoo CRM" : "";
  const name = id.replace(/^odoo_crm_/, "").replaceAll("_", " ");
  return (name.charAt(0).toUpperCase() + name.slice(1)) + (soft ? ` · ${soft}` : "");
}

/** One headline for the status pill: {text, sub, tone: off|idle|live|done|warn, pulse}. */
export function headline(status) {
  if (!status) {
    return { text: "Agent not running", sub: "The app connects as soon as it runs", tone: "off", pulse: false };
  }
  const v = status.voice || {};
  if (v.state === "starting") return { text: "Opening microphone…", sub: "Allow microphone access if macOS asks", tone: "live", pulse: true };
  if (typeof v.state === "string" && v.state.startsWith("error:")) return { text: "Microphone or transcription error", sub: v.state.slice(6).trim(), tone: "warn", pulse: false };
  if (v.state === "too_short") return { text: "Recording too short", sub: `Hold ${keyLabel(v.ptt_key)} while speaking, then release`, tone: "warn", pulse: false };
  if (v.state === "recording") return { text: "Listening…", sub: "Release the key when you are done", tone: "live", pulse: true };
  if (v.state === "transcribing") return { text: "Transcribing…", sub: v.last_text || "", tone: "live", pulse: true };
  const c = status.current;
  if (c && !c.terminal) {
    const step = c.step;
    switch (c.state) {
      case "created":
      case "awaiting_approval":
        return { text: "Waiting for your approval", sub: c.goal || "", tone: "live", pulse: true };
      case "awaiting_user":
        return {
          text: step ? `Step ${step.index}${step.total ? ` of ${step.total}` : ""}` : "Your turn",
          sub: step ? step.instruction : "",
          tone: "live",
          pulse: false,
        };
      case "running":
        return c.takeover
          ? { text: "Taking over", sub: c.last_action || "I finish the task and show each action", tone: "live", pulse: true }
          : { text: "Looking at the screen…", sub: step ? step.instruction : c.goal || "", tone: "live", pulse: true };
      case "verifying":
        return { text: "Checking the result…", sub: "A separate check reads the software, read-only", tone: "live", pulse: true };
      case "stopping":
        return { text: "Stopping…", sub: "No new action leaves this computer", tone: "warn", pulse: true };
      default:
        return { text: c.state, sub: "", tone: "live", pulse: false };
    }
  }
  const ready = { text: "Ready", sub: `Hold ${keyLabel(v.ptt_key)} and say what you need`, tone: "idle", pulse: false };
  if (c && c.terminal) {
    if (c.status === "resolved" && c.verified) return { ...ready, text: "Done, result verified", tone: "done" };
    if (c.status === "escalated") return { ...ready, text: "Handed over to support", sub: c.blocked_on || ready.sub, tone: "warn" };
    if (c.status === "abandoned" || c.state === "stopped") return { ...ready, text: "Stopped. Nothing else changed" };
    if (c.state === "failed" || c.status === "failed") return { ...ready, text: "Something went wrong", tone: "warn" };
  }
  return ready;
}

export function isBusy(status) {
  return Boolean(status && status.current && !status.current.terminal);
}

export function money(usd) {
  if (usd === null || usd === undefined) return "—";
  return usd < 0.01 && usd > 0 ? "< $0.01" : `$${usd.toFixed(2)}`;
}

export function duration(s) {
  if (s === null || s === undefined) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  return `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function ratio(used, limit) {
  if (!limit) return null;
  return Math.max(0, Math.min(1, used / limit));
}

/** Credits for the plan: sessions (Starter), verified fixes (Fix pack), nothing to count (Pro). */
export function planMeter(planId, month) {
  const p = PLANS[planId] || PLANS.starter;
  const m = month || { sessions: 0, verified: 0 };
  const used = planId === "fixpack" ? m.verified : m.sessions;
  return { used, limit: p.quota, unit: p.unit, ratio: ratio(used, p.quota) };
}

export const STATUS_LABEL = {
  resolved: "Verified",
  escalated: "To support",
  abandoned: "Stopped",
  failed: "Failed",
};

export function when(iso, now = new Date()) {
  if (!iso) return "";
  const d = new Date(iso);
  const mins = Math.round((now - d) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 24 * 60) return `${Math.round(mins / 60)} h ago`;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
