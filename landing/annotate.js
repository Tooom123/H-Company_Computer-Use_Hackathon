// Red-pen review driven by scroll. Every [data-mark] / [data-write] is corrected as soon as it enters the
// screen, and stays corrected forever (never hidden again).
// [data-mark]  -> rough-notation (strike-through, underline, circle, box, crossed-off, highlight)
// [data-write] -> handwritten note revealed as if written left to right
//
// Keeping up with fast scrolling: corrections are not queued behind each other. Each one starts as soon as
// it is reached, with a small stagger to keep document order (a strike, then its note); the stagger and the
// drawing speed shrink when several arrive at once, and anything already scrolled past is shown instantly.
import { annotate } from "rough-notation";

const RED = "#e3242b";
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

const STYLE = {
  "strike-through": { strokeWidth: 2.6, duration: 480 },
  "crossed-off": { strokeWidth: 2.6, padding: 6, duration: 600 },
  underline: { strokeWidth: 2.4, padding: 2, duration: 520 },
  circle: { strokeWidth: 2.4, padding: [6, 12], duration: 700 },
  box: { strokeWidth: 2.2, padding: 6, duration: 600 },
  highlight: { color: "rgba(227,36,43,.22)", duration: 600 },
};

const done = new WeakSet();

function correct(el, speed) {
  if (done.has(el)) return;
  done.add(el);
  const instant = reduce || speed === 0;
  if (el.hasAttribute("data-write")) {
    if (instant) el.style.transition = "none";
    else el.style.transitionDuration = `${Math.round(750 * speed)}ms`;
    el.classList.add("on");
    return;
  }
  const type = el.dataset.mark;
  const s = STYLE[type] || {};
  annotate(el, {
    type, color: s.color || RED, strokeWidth: s.strokeWidth, padding: s.padding, multiline: true,
    iterations: type === "highlight" ? 1 : 2,
    animate: !instant, animationDuration: Math.max(120, Math.round(s.duration * speed)),
  }).show();
}

// everything reached since the last frame, launched together in document order
const items = [...document.querySelectorAll("[data-mark],[data-write]")];
const order = new Map(items.map((el, i) => [el, i]));
let batch = [];
let scheduled = false;
function launch() {
  scheduled = false;
  const now = batch.sort((a, b) => order.get(a) - order.get(b));
  batch = [];
  const n = now.length;
  const stagger = n > 4 ? 40 : n > 1 ? 110 : 0; // many at once = scrolling fast: tighter, quicker
  const speed = n > 4 ? 0.45 : n > 1 ? 0.75 : 1;
  now.forEach((el, i) => {
    const passed = el.getBoundingClientRect().bottom < 0; // already above the screen: no need to animate
    if (passed) correct(el, 0);
    else setTimeout(() => correct(el, speed), i * stagger);
  });
}
function reach(el) {
  if (done.has(el) || batch.includes(el)) return;
  batch.push(el);
  if (!scheduled) { scheduled = true; requestAnimationFrame(launch); }
}

await document.fonts.ready;
if (new URLSearchParams(location.search).has("review")) {
  items.forEach(reach);
} else {
  // on every scroll frame: anything whose top has reached 92% of the screen height, or that is already
  // above it (fast scroll, jump to an anchor), is corrected. Nothing is ever un-corrected.
  let waiting = [...items];
  let ticking = false;
  const check = () => {
    ticking = false;
    const line = innerHeight * 0.92;
    waiting = waiting.filter((el) => {
      if (el.getBoundingClientRect().top < line) { reach(el); return false; }
      return true;
    });
    if (!waiting.length) removeEventListener("scroll", onScroll);
  };
  const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(check); } };
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);
  check();
}
