// Pure formatting for the UI (no DOM): what to say about the agent's state. Tested with `node --test`.

export function keyLabel(key) {
  if (!key) return "⌘H";
  const names = { cmd: "⌘", ctrl: "⌃", alt: "⌥", shift: "⇧", space: "Space", alt_r: "Right ⌥", cmd_r: "Right ⌘" };
  return key
    .toLowerCase()
    .split("+")
    .map((k) => names[k] || k.toUpperCase())
    .join("");
}

export function procedureName(id) {
  if (!id) return "";
  const soft = id.startsWith("odoo_crm_") ? "Odoo CRM" : "";
  const name = id.replace(/^odoo_crm_/, "").replaceAll("_", " ");
  return name.charAt(0).toUpperCase() + name.slice(1) + (soft ? ` · ${soft}` : "");
}

/** One headline for the status pill: {text, sub, tone: off|idle|live|done|warn, pulse}. */
export function headline(status) {
  if (!status) {
    return { text: "Assistant not running", sub: "The app connects as soon as it runs", tone: "off", pulse: false };
  }
  const v = status.voice || {};
  if (v.state === "recording") return { text: "Listening…", sub: "Release the key when you are done", tone: "live", pulse: true };
  if (v.state === "transcribing") return { text: "Transcribing…", sub: "", tone: "live", pulse: true };
  const c = status.current;
  if (c && !c.terminal) {
    const step = c.step;
    switch (c.state) {
      case "created":
      case "awaiting_approval":
        return { text: "Waiting for your approval", sub: c.goal || "", tone: "live", pulse: true };
      case "awaiting_user":
        return {
          text: step ? `Your turn · step ${step.index}${step.total ? ` of ${step.total}` : ""}` : "Your turn",
          sub: step ? step.instruction : "",
          tone: "live",
          pulse: false,
        };
      case "running":
        return c.takeover
          ? { text: "I'm doing it", sub: c.last_action || "Watch: I show each action on screen", tone: "live", pulse: true }
          : { text: "Looking at your screen…", sub: step ? `Next: ${step.instruction}` : c.goal || "", tone: "live", pulse: true };
      case "verifying":
        return { text: "Checking it worked…", sub: "I look in the software to see that the change is really there", tone: "live", pulse: true };
      case "stopping":
        return { text: "Stopping…", sub: "Nothing else will be changed", tone: "warn", pulse: true };
      default:
        return { text: c.state, sub: "", tone: "live", pulse: false };
    }
  }
  const ready = { text: "Ready", sub: `Hold ${keyLabel(v.ptt_key)} and say what you need`, tone: "idle", pulse: false };
  if (c && c.terminal) {
    const goal = c.goal ? `“${c.goal}”` : "The task";
    if (c.status === "resolved" && c.verified) {
      return { text: "Done ✓", sub: `${goal} is done: I checked it in the software`, tone: "done", pulse: false };
    }
    if (c.status === "resolved") return { text: "Done", sub: `${goal}: I could not check it myself, have a look`, tone: "warn", pulse: false };
    if (c.status === "escalated") {
      return { text: "Sent to support", sub: c.blocked_on ? `I could not finish: ${c.blocked_on}` : "Support has the details", tone: "warn", pulse: false };
    }
    if (c.status === "abandoned" || c.state === "stopped") return { text: "Stopped", sub: "Nothing else will be changed", tone: "idle", pulse: false };
    if (c.state === "failed" || c.status === "failed") return { text: "Something went wrong", sub: "Support has the details", tone: "warn", pulse: false };
  }
  return ready;
}

export function isBusy(status) {
  return Boolean(status && status.current && !status.current.terminal);
}

export function duration(s) {
  if (s === null || s === undefined) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  return `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export const STATUS_LABEL = {
  resolved: "Checked",
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
