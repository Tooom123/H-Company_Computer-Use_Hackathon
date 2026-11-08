// Gaze feed to the H Companion agent (Tom). When the user turns Vision on in the desktop app, the agent sends
// Holo a crop around where they look instead of the whole screen (agent/src/hcs_agent/gaze_crop.py). This module
// forwards the accepted gaze points (screen points, no image) to the agent's local control point, at most ~15 per
// second. If the agent is not running or Vision is off, it backs off quietly; the lab works exactly as before.

const URL = process.env.HCS_CONTROL_URL || 'http://127.0.0.1:8768';
const MIN_INTERVAL_MS = 66;
const BACKOFF_MS = 5000;

let lastSent = 0;
let pausedUntil = 0;
let inFlight = false;

/** @param {{x:number,y:number}|null} point screen point (display-local) @param {{x:number,y:number}} origin display origin */
export function forwardGaze(point, origin, errorPx, now = Date.now()) {
  if (!point || inFlight || now < pausedUntil || now - lastSent < MIN_INTERVAL_MS) return false;
  lastSent = now;
  inFlight = true;
  const body = { x: point.x + (origin?.x || 0), y: point.y + (origin?.y || 0) };
  if (Number.isFinite(errorPx) && errorPx > 0) body.error_px = errorPx;
  fetch(`${URL}/gaze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-HCS-Gaze': '1' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(500),
  })
    .then((r) => r.json().catch(() => ({})))
    .then((r) => { if (r && r.accepted === false) pausedUntil = Date.now() + BACKOFF_MS; }) // Vision off in the app
    .catch(() => { pausedUntil = Date.now() + BACKOFF_MS; }) // agent not running
    .finally(() => { inFlight = false; });
  return true;
}
