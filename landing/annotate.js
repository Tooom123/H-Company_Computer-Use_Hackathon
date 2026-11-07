// Red-pen review driven by scroll: every [data-mark] / [data-write] is corrected when it reaches the
// reading zone, one after the other in document order, and stays corrected afterwards.
// [data-mark]  -> rough-notation (strike-through, underline, circle, box, crossed-off, highlight)
// [data-write] -> handwritten note revealed as if written left to right
import { annotate } from "rough-notation";

const RED = "#e3242b";
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms) => new Promise((r) => setTimeout(r, reduce ? 0 : ms));

const STYLE = {
  "strike-through": { strokeWidth: 2.6, duration: 520 },
  "crossed-off": { strokeWidth: 2.6, padding: 6, duration: 650 },
  underline: { strokeWidth: 2.4, padding: 2, duration: 560 },
  circle: { strokeWidth: 2.4, padding: [6, 12], duration: 760 },
  box: { strokeWidth: 2.2, padding: 6, duration: 650 },
  highlight: { color: "rgba(227,36,43,.22)", duration: 650 },
};

async function correct(el) {
  if (el.hasAttribute("data-write")) {
    el.classList.add("on");
    return sleep(Math.min(1000, 240 + el.textContent.length * 26));
  }
  const type = el.dataset.mark;
  const s = STYLE[type] || {};
  annotate(el, {
    type, color: s.color || RED, strokeWidth: s.strokeWidth, padding: s.padding, multiline: true,
    iterations: type === "highlight" ? 1 : 2, animate: !reduce, animationDuration: s.duration,
  }).show();
  return sleep(s.duration * 0.85);
}

// one pen: corrections queue up in document order
const items = [...document.querySelectorAll("[data-mark],[data-write]")];
const pending = new Set();
let busy = false;
async function drain() {
  if (busy) return;
  busy = true;
  while (pending.size) {
    const next = items.find((el) => pending.has(el));
    pending.delete(next);
    await correct(next);
  }
  busy = false;
}

await document.fonts.ready;
if (new URLSearchParams(location.search).has("review")) {
  items.forEach((el) => pending.add(el));
  drain();
} else {
  // the reading zone: an element is corrected once it has scrolled above 78% of the viewport height
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        io.unobserve(e.target);
        pending.add(e.target);
      }
      drain();
    },
    { rootMargin: "0px 0px -22% 0px" },
  );
  items.forEach((el) => io.observe(el));
}
