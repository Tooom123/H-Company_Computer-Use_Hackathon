// Pure formatting for the UI (no DOM): what to say about the agent's state. Tested with `node --test`.

export function keyLabel(key) {
  if (!key) return "⌃⇧H";
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

/** The paper badge on Home: the same words as the on-screen badge. Only "Listening…" while the key is held. */
export function readyBadge(status) {
  const v = (status && status.voice) || {};
  if (v.state === "starting") return { text: "Opening microphone…", sub: "Allow microphone access if macOS asks", pulse: true };
  if (typeof v.state === "string" && v.state.startsWith("error:")) return { text: "Microphone or transcription error", sub: v.state.slice(6).trim(), pulse: false };
  if (v.state === "too_short") return { text: "Recording too short", sub: `Hold ${keyLabel(v.ptt_key)} while speaking, then release`, pulse: false };
  if (v.state === "recording") return { text: "Listening…", pulse: true };
  if (v.state === "transcribing") return { text: "Transcribing…", pulse: true };
  return { text: `${keyLabel(v.ptt_key)}: new request`, pulse: false };
}

/** One plain line about the running task, for the task card. */
export function taskLine(c) {
  if (!c) return "";
  const step = c.step;
  switch (c.state) {
    case "created":
    case "awaiting_approval":
      return "Waiting for your go";
    case "awaiting_user":
      return step ? `Now you: ${step.instruction}` : "Now you: do the step shown on screen";
    case "running":
      return c.takeover ? `I'm doing it${c.last_action ? `: ${c.last_action}` : ""}` : "Looking at your screen…";
    case "verifying":
      return "Checking in the software that it worked…";
    case "stopping":
      return "Stopping: nothing else will be changed";
    default:
      return "";
  }
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

/** Never restore the macOS Hide shortcut from an old app preference. */
export function safePttPreference(key) {
  return ["ctrl+shift+h", "cmd+j", "alt_r", "f9"].includes(key) ? key : null;
}
