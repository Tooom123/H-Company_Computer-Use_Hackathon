// Collects the clickable controls visible in the viewport and sends their boxes, in screen pixels, to the H Companion
// desktop app (through background.js), so the red gaze honeycomb can snap to them. Only geometry and a short label
// leave the page, and only to 127.0.0.1. Nothing is sent while the window is not focused.
(() => {
  const SELECTOR = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea", "summary", "label[for]",
    "[role=button]", "[role=link]", "[role=tab]", "[role=menuitem]", "[role=checkbox]", "[role=radio]", "[role=switch]",
    "[role=option]", "[onclick]", "[contenteditable=true]", "[tabindex]:not([tabindex='-1'])",
  ].join(",");
  const MAX = 250;
  let timer = null;
  let lastKey = "";
  let lastSent = 0;

  /** Where the viewport's top-left corner is on the screen. Browsers do not expose it: assume the toolbars are at
   * the top and borders are even. On Wayland screenX/screenY are 0, so this is exact only for a maximized window. */
  function viewportOrigin() {
    const zoom = window.outerWidth > 0 && window.innerWidth > 0 ? Math.max(0.25, window.devicePixelRatio / (window.__hcsBaseDpr || window.devicePixelRatio)) : 1;
    const border = Math.max(0, (window.outerWidth - window.innerWidth * zoom) / 2);
    return { x: window.screenX + border, y: window.screenY + Math.max(0, window.outerHeight - window.innerHeight * zoom - border), zoom };
  }

  function collect() {
    const vw = innerWidth;
    const vh = innerHeight;
    const o = viewportOrigin();
    const out = [];
    for (const el of document.querySelectorAll(SELECTOR)) {
      if (out.length >= MAX) break;
      if (el.disabled || el.getAttribute("aria-hidden") === "true") continue;
      const r = el.getBoundingClientRect();
      if (r.width < 6 || r.height < 6 || r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh) continue;
      if (r.width * r.height > vw * vh * 0.4) continue; // a whole-page link or wrapper is not a target
      const cx = Math.min(vw - 1, Math.max(0, r.left + r.width / 2));
      const cy = Math.min(vh - 1, Math.max(0, r.top + r.height / 2));
      const top = document.elementFromPoint(cx, cy);
      if (top && top !== el && !el.contains(top) && !top.contains(el)) continue; // covered by something else
      const label = (el.getAttribute("aria-label") || el.innerText || el.value || el.title || el.tagName || "").trim().slice(0, 40);
      out.push({
        x: Math.round(o.x + r.left * o.zoom), y: Math.round(o.y + r.top * o.zoom),
        w: Math.round(r.width * o.zoom), h: Math.round(r.height * o.zoom), label,
      });
    }
    return out;
  }

  function send(force) {
    timer = null;
    const active = document.visibilityState === "visible" && document.hasFocus();
    const targets = active ? collect() : [];
    const key = JSON.stringify(targets);
    const now = Date.now();
    if (!force && key === lastKey && now - lastSent < 1000) return; // unchanged: a heartbeat each second is enough
    lastKey = key;
    lastSent = now;
    try { chrome.runtime.sendMessage({ type: "hcs-targets", targets }); } catch { /* extension reloaded */ }
  }

  const schedule = () => { if (!timer) timer = setTimeout(send, 150); };
  window.__hcsBaseDpr = window.devicePixelRatio; // page zoom at load is taken as 100 %
  addEventListener("scroll", schedule, { passive: true, capture: true });
  addEventListener("resize", schedule);
  addEventListener("focus", () => send(true));
  addEventListener("blur", () => send(true));
  document.addEventListener("visibilitychange", () => send(true));
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true, attributes: true,
    attributeFilter: ["class", "style", "hidden", "disabled"] });
  setInterval(() => { if (document.hasFocus()) send(false); }, 1000);
  send(true);
})();
