// The margin firefighter: a stick figure on the red margin line, which is his pole.
// - At the start (before the white page reaches the top of the screen) he waves hello.
// - Then he slides down as you read: his position follows your scroll progress through the page,
//   so he travels from the top of the screen to the bottom, eased so he lags and "slides".
// - While sliding: tilt, body judder, head looks down, free leg kicks, friction sparks at the hands.
// - Scrolling back up: he climbs, hand over hand, legs pushing, looking up, with effort marks.
const paper = document.querySelector(".paper");
const fig = document.getElementById("pompier");
const man = fig.querySelector(".man");
const head = fig.querySelector(".head");
const armA = fig.querySelector(".armA");
const gripA = fig.querySelector(".gripA");
const armB = fig.querySelector(".armB");
const legWrap = fig.querySelector(".legWrap");
const gripB = fig.querySelector(".gripB");
const leg = fig.querySelector(".legFree");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

let y = 0, wave = 1, climb = 0, phase = 0;
function state() {
  const r = paper.getBoundingClientRect();
  const figH = fig.getBoundingClientRect().height;
  const travel = Math.max(1, r.height - innerHeight);
  const p = clamp(-r.top / travel, 0, 1); // 0 until the page top reaches the screen top, 1 at the end
  return { goal: p * (r.height - figH - 24), start: p === 0 };
}
function tick(now) {
  const t = now / 1000;
  const { goal, start } = state();
  const prev = y;
  y += (goal - y) * (reduce ? 1 : 0.1);
  const v = y - prev;
  const speed = clamp(Math.abs(v) / 4, 0, 1);
  wave += ((start && Math.abs(v) < 0.3 && !reduce ? 1 : 0) - wave) * 0.1;

  fig.style.transform = `translateY(${y.toFixed(1)}px) rotate(${clamp(-v * 0.45, -9, 9 ).toFixed(2)}deg)`;
  fig.style.setProperty("--speed", speed.toFixed(2));
  fig.classList.toggle("up", v < -0.3);
  climb += ((v < -0.3 && !reduce ? 1 : 0) - climb) * 0.15;
  phase += Math.max(0, -v) * 0.16; // the climbing rhythm follows the distance climbed
  fig.style.setProperty("--climb", climb.toFixed(2));
  if (!reduce) {
    const slide = 1 - climb;
    const s1 = Math.sin(phase), s2 = Math.sin(phase + Math.PI);
    const judder = Math.sin(t * 46) * 0.7 * speed * slide;
    const lift = -Math.abs(s1) * 1.6 * climb; // body bobs up with each pull
    man.setAttribute("transform", `translate(${judder.toFixed(2)} ${lift.toFixed(2)})`);
    // free leg: swing at rest, kick back when sliding, push when climbing
    const legA = (Math.sin(t * 2.3) * 6 * (1 - speed) - clamp(v * 5, -32, 32) + Math.sin(t * 13) * 5 * speed) * slide + s2 * 24 * climb;
    leg.setAttribute("transform", `rotate(${legA.toFixed(1)} 22.8 44)`);
    legWrap.setAttribute("transform", `rotate(${(s1 * 14 * climb).toFixed(1)} 22.8 44)`);
    // hand over hand: each arm reaches up in turn (and lets go of the pole while reaching)
    armA.setAttribute("transform", `rotate(${(Math.max(0, s1) * 22 * climb).toFixed(1)} 23.8 26)`);
    gripA.style.opacity = (1 - Math.max(0, s1) * climb).toFixed(2);
    const reachB = Math.max(0, s2) * 22 * climb;
    armB.setAttribute("transform", `rotate(${(wave * (112 + Math.sin(t * 9) * 16) + reachB).toFixed(1)} 23.6 28.5)`);
    gripB.style.opacity = ((1 - wave) * (1 - Math.max(0, s2) * climb)).toFixed(2);
    // head: looks down when sliding, up when climbing, tilts while waving
    const look = clamp(v * 3, -14, 14) * slide - 12 * climb + wave * 8;
    head.setAttribute("transform", `translate(0 ${(Math.sin(t * 2) * 0.5).toFixed(2)}) rotate(${look.toFixed(1)} 24 21)`);
  }
  requestAnimationFrame(tick);
}
y = state().goal;
requestAnimationFrame(tick);
