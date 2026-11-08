"""Gaze × clickable controls × intent → crop. Each signal on its own, and combined.

For every gaze trial of bench/data-intent (tasks with a spoken-style user request, see make_intents.py), the crop
sent to Holo is chosen from the screen's clickable elements (exact boxes, recorded at capture time):

  p(element) ∝ gaze(element) × intent(element)          (clickable: only real controls are candidates)

  gaze(e)    = exp(-d²/2σ²) + 0.02   d = distance from the gaze point to the element's box, σ = webcam error
  intent(e)  = score(request, label) + 0.15   local word match (FR/EN action synonyms, prefix stemming), 0..1

The crop is the box of the most probable elements holding 80 % of the probability, + 40 px, at least 768×480
(the size that kept full-screen accuracy in the gaze benchmark). Holo gets F's own request with a "not here"
escape; "not here" falls back to the full screen (both calls counted).

Strategies (ablation):
  F    full screen (today)                       G    gaze only: a box around the gaze point (no controls)
  GC   gaze × clickable controls                 I    intent × clickable controls (no webcam)
  GCI  gaze × clickable controls × intent (all three)

The request given to Holo is the user's request (not the control's name), the same in every strategy.

    .venv/bin/python bench/run_intent.py --geometry                 # free: target-in-crop and pixels, all trials
    .venv/bin/python bench/run_intent.py --tasks 30 --conditions gaze120,elsewhere   # real calls on a subset
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import re
import statistics as st
import sys
import threading
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("run_bench", ROOT / "bench" / "run_bench.py")
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)

W, H = 1440, 900
MIN_W, MIN_H, MARGIN, MASS = 768, 480, 40, 0.8
GAZE_FLOOR, INTENT_FLOOR = 0.02, 0.15
STRATS = ["F", "G", "GC", "I", "GCI", "GCIa"]
AGREE_MIN = 0.5  # intent score needed for "the request clearly names a control"

# --------------------------------------------------------------------------------------------- intent

STOP = set("""a an the to of in on at for my me i it this that is be can could you please want need would like and or
with from page site your some help show open click go get do make le la les un une des de du au aux à a et ou en sur
pour mon ma mes me je j moi tu te vous peux pouvez peut veux voudrais besoin aide aider ce cette cet ces qui que quoi
est sont faire fais montre montrer ouvrir ouvre cliquer clique aller va sur dans par avec site page lien bouton link
button""".split())
SYNONYMS = [
    "delete remove supprimer supprime retirer effacer trash corbeille revoke revoquer erase",
    "new create creer cree nouveau nouvelle add ajouter ajoute plus",
    "search rechercher recherche chercher cherche find trouver trouve look",
    "login log sign signin connexion connecter connecte account compte",
    "menu navigation nav",
    "home accueil homepage principale",
    "save enregistrer sauvegarder sauvegarde",
    "more voir see plus suite details",
    "next suivant suivante",
    "previous precedent back retour",
    "settings parametres reglages preferences configuration config",
    "download telecharger telechargement",
    "comment comments commentaire commentaires discussion",
    "discard annuler cancel abandonner",
    "confirm valider confirmer validate",
    "share partager",
    "filter filters filtrer filtre",
    "group grouper regrouper regroupement",
    "list liste",
    "note notes",
    "message messages send envoyer",
    "activity activities activite activites schedule planifier",
    "user users utilisateur utilisateurs people",
    "language languages langue langues",
    "currency currencies devise devises",
    "inventory inventaire stock",
    "favorite favorites favoris",
    "article articles story",
    "question questions ask poser",
    "price pricing prix tarif tarifs",
    "contact contacter",
    "about propos",
    "jobs emplois carriere careers",
    "donate don faire",
]
SYN = {}
for line in SYNONYMS:
    words = line.split()
    for w in words:
        SYN.setdefault(w[:5], set()).update(x[:5] for x in words)


def tokens(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [w for w in re.findall(r"[a-z0-9]+", t) if len(w) >= 2 and w not in STOP]


def intent_score(request: str, label: str) -> float:
    """Share of the label's words that the request mentions (prefix-stemmed, with action synonyms), 0..1."""
    lab = [w[:5] for w in tokens(label)]
    if not lab:
        return 0.0
    req = set()
    for w in tokens(request):
        req.add(w[:5])
        req |= SYN.get(w[:5], set())
    hits = sum(1 for w in lab if w in req)
    return hits / len(lab)


# --------------------------------------------------------------------------------------------- crops

def dist_to_rect(x, y, r):
    dx = max(r["x"] - x, 0, x - (r["x"] + r["width"]))
    dy = max(r["y"] - y, 0, y - (r["y"] + r["height"]))
    return math.hypot(dx, dy)


def fit(x0, y0, x1, y1):
    """Box + margin, grown to the minimum size around its centre, kept on screen."""
    x0, y0, x1, y1 = x0 - MARGIN, y0 - MARGIN, x1 + MARGIN, y1 + MARGIN
    w, h = max(x1 - x0, MIN_W), max(y1 - y0, MIN_H)
    w, h = min(w, W), min(h, H)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x = min(max(0, cx - w / 2), W - w)
    y = min(max(0, cy - h / 2), H - h)
    return {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}


def mass_box(elements, probs):
    order = sorted(range(len(elements)), key=lambda i: -probs[i])
    total = sum(probs) or 1
    acc, box = 0.0, None
    for i in order:
        r = elements[i]["rect"]
        b = (r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"])
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        acc += probs[i] / total
        if acc >= MASS:
            break
    return box


def crop_for(strategy: str, elements: list, gaze: dict | None, sigma: float, request: str) -> dict | None:
    """None = full screen (no crop)."""
    if strategy == "F":
        return None
    if strategy == "G":  # gaze alone: a box around the point, as wide as the uncertainty
        half = 1.3 * sigma
        return fit(gaze["x"] - half, gaze["y"] - half, gaze["x"] + half, gaze["y"] + half)
    use_gaze = strategy in ("GC", "GCI", "GCIa")
    use_intent = strategy in ("I", "GCI", "GCIa")
    scores = [intent_score(request, e["label"]) for e in elements] if use_intent else None
    if strategy == "I" and max(scores or [0]) == 0:
        return None  # the request matches no control: nothing to crop on, send the full screen
    probs = []
    for i, e in enumerate(elements):
        p = 1.0
        if use_gaze:
            d = dist_to_rect(gaze["x"], gaze["y"], e["rect"])
            p *= math.exp(-(d * d) / (2 * sigma * sigma)) + GAZE_FLOOR
        if use_intent:
            # alone, intent keeps only the controls the request mentions; with gaze, a floor lets gaze decide
            # when the request names nothing on screen
            p *= scores[i] + (INTENT_FLOOR if use_gaze else 0.0)
        probs.append(p)
    return fit(*mass_box(elements, probs))


def agree(elements, gaze, request, crop, sigma) -> bool:
    """Gaze and intent agree: the control the request names best (score ≥ AGREE_MIN) lies within 2σ of the gaze,
    and inside the crop. Then Holo is asked to point, without the "not here" escape (no needless fallback)."""
    if crop is None:
        return False
    sc = [intent_score(request, e["label"]) for e in elements]
    i = max(range(len(elements)), key=lambda k: sc[k])
    if sc[i] < AGREE_MIN:
        return False
    r = elements[i]["rect"]
    cx, cy = r["x"] + r["width"] / 2, r["y"] + r["height"] / 2
    within = lambda x, y: crop["x"] <= x <= crop["x"] + crop["width"] and crop["y"] <= y <= crop["y"] + crop["height"]  # noqa: E731
    return within(cx, cy) and dist_to_rect(gaze["x"], gaze["y"], r) <= 2 * sigma


def inside(r, c):
    return c is None or (r["x"] >= c["x"] and r["y"] >= c["y"] and r["x"] + r["width"] <= c["x"] + c["width"]
                         and r["y"] + r["height"] <= c["y"] + c["height"])


# --------------------------------------------------------------------------------------------- run

def load(data_dir: Path):
    data = json.loads((data_dir / "dataset.json").read_text())
    screens = {s["name"]: s for s in data["screens"]}
    tasks = {t["id"]: t for t in data["tasks"]}
    return data, screens, tasks


def geometry(data, screens, tasks, conditions):
    rows = defaultdict(list)
    for tr in data["trials"]:
        if tr["condition"] not in conditions:
            continue
        t = tasks[tr["task"]]
        sigma = max(96, tr["error_px"])
        for s in STRATS:
            c = crop_for(s, screens[t["screen"]]["elements"], tr["gaze"], sigma, t["intent"])
            px = W * H if c is None else c["width"] * c["height"]
            rows[(tr["condition"], s)].append((inside(t["target_rect"], c), px))
    out = ["| condition | " + " | ".join(STRATS) + " |", "|---|" + "---|" * len(STRATS)]
    for cond in conditions:
        cells = []
        for s in STRATS:
            r = rows[(cond, s)]
            k = sum(x for x, _ in r)
            px = st.median(p for _, p in r) / (W * H)
            cells.append(f"{k / len(r):.0%} in · {px:.0%} px")
        out.append(f"| {cond} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "bench" / "data-intent"))
    ap.add_argument("--out", default=str(ROOT / "bench" / "results"))
    ap.add_argument("--model", default="holo4-35b-a3b")
    ap.add_argument("--conditions", default="gaze120,elsewhere")
    ap.add_argument("--tasks", type=int, default=0, help="random subset of N tasks (0 = all)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--resume")
    ap.add_argument("--geometry", action="store_true", help="free: target inside the crop and pixels, no call")
    a = ap.parse_args()
    data, screens, tasks = load(Path(a.data))
    conditions = a.conditions.split(",")
    if a.geometry:
        print(geometry(data, screens, tasks, conditions))
        return 0

    ids = sorted(tasks)
    if a.tasks:
        ids = sorted(random.Random(3).sample(ids, min(a.tasks, len(ids))))
    keep = set(ids)
    run_dir = Path(a.resume or Path(a.out) / ("intent-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "calls.jsonl"
    done = {}
    if log.exists():
        for line in log.read_text().splitlines():
            r = json.loads(line)
            if "error" not in r:
                done[r["key"]] = r
    imgs = {n: Image.open(Path(a.data) / s["file"]).convert("RGB") for n, s in screens.items()}
    holo = rb.Holo()
    price = holo.pricing().get(a.model, {"prompt": 0, "completion": 0})

    # one call per distinct (task, image region): identical crops are asked once and shared
    plan = {}
    for tid in ids:
        plan[f"{tid}|full"] = {"task": tid, "crop": None}
    for tr in data["trials"]:
        if tr["task"] not in keep or tr["condition"] not in conditions:
            continue
        t = tasks[tr["task"]]
        for s in STRATS[1:]:
            c = crop_for(s, screens[t["screen"]]["elements"], tr["gaze"], max(96, tr["error_px"]), t["intent"])
            if c is None:
                continue
            ck = f"{tr['task']}|{c['x']},{c['y']},{c['width']},{c['height']}"
            if s == "GCIa":
                if agree(screens[t["screen"]]["elements"], tr["gaze"], t["intent"], c, max(96, tr["error_px"])):
                    plan.setdefault(ck + "|point", {"task": tr["task"], "crop": c, "point": True})
            else:
                plan.setdefault(ck, {"task": tr["task"], "crop": c})
    todo = [(k, v) for k, v in plan.items() if k not in done]
    random.Random(1).shuffle(todo)
    print(f"{len(ids)} tasks, {len(plan)} distinct images, {len(todo)} to ask -> {run_dir}", flush=True)

    def ask(key, item):
        t = tasks[item["task"]]
        img = imgs[t["screen"]]
        if item["crop"] is None:
            sent = rb.full_image(img)
            region = {"x": 0, "y": 0, "width": W, "height": H}
            r = holo.locate(a.model, rb.jpeg_b64(sent)[0], rb.prompt_for(t["intent"], False), [rb._POINT])
            found = r["fn"] == "locate"
        elif item.get("point"):  # signals agree: point, no escape (F's request on the crop)
            sent = rb.crop_image(img, item["crop"])
            region = item["crop"]
            r = holo.locate(a.model, rb.jpeg_b64(sent)[0], rb.prompt_for(t["intent"], False), [rb._POINT])
            found = r["fn"] == "locate"
        else:
            sent = rb.crop_image(img, item["crop"])
            region = item["crop"]
            r = holo.locate(a.model, rb.jpeg_b64(sent)[0], rb.prompt_for(t["intent"], True, context=False), [rb._POINT, rb._NOT_FOUND])
            found = r["fn"] == "locate" and bool(r["args"].get("is_the_control", True))
        xy = rb.to_screen(r["args"], region) if found else None
        return {"key": key, "task": item["task"], "crop": item["crop"], "found": found, "xy": xy,
                "success": rb.hit(xy, t["target_rect"]), "latency_s": r["latency_s"], "pixels": sent.width * sent.height,
                "prompt_tokens": r["prompt_tokens"], "completion_tokens": r["completion_tokens"]}

    lock = threading.Lock()
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as pool, log.open("a") as fh:
        futs = {pool.submit(ask, k, v): k for k, v in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as exc:  # noqa: BLE001
                r = {"key": futs[f], "error": str(exc)[:200]}
            with lock:
                fh.write(json.dumps(r) + "\n")
                fh.flush()
            if "error" not in r:
                done[r["key"]] = r
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} calls, {(time.time() - t0) / 60:.1f} min", flush=True)

    report = build(data, screens, tasks, ids, conditions, done, price, a.model)
    (run_dir / "report.md").write_text(report)
    print(report)
    print(f"-> {run_dir}")
    return 0


def build(data, screens, tasks, ids, conditions, done, price, model) -> str:
    keep = set(ids)
    cost = lambda r: (r["prompt_tokens"] or 0) * price["prompt"] + (r["completion_tokens"] or 0) * price["completion"]  # noqa: E731
    full = {tid: done.get(f"{tid}|full") for tid in ids}
    res = defaultdict(list)  # (condition, strategy) -> outcomes
    for tr in data["trials"]:
        if tr["task"] not in keep or tr["condition"] not in conditions or full.get(tr["task"]) is None:
            continue
        t = tasks[tr["task"]]
        f = full[tr["task"]]
        verbatim = bool(t["label"]) and t["label"].lower() in t["intent"].lower()
        for s in STRATS:
            c = None if s == "F" else crop_for(s, screens[t["screen"]]["elements"], tr["gaze"], max(96, tr["error_px"]), t["intent"])
            if c is None:
                o = {"success": f["success"], "lat": f["latency_s"], "cost": cost(f), "px": f["pixels"], "fb": False, "in": True}
            else:
                ck = f"{tr['task']}|{c['x']},{c['y']},{c['width']},{c['height']}"
                if s == "GCIa" and agree(screens[t["screen"]]["elements"], tr["gaze"], t["intent"], c, max(96, tr["error_px"])):
                    ck += "|point"
                g = done.get(ck)
                if g is None:
                    continue
                if g["found"]:
                    o = {"success": g["success"], "lat": g["latency_s"], "cost": cost(g), "px": g["pixels"], "fb": False}
                else:  # "not here": the full screen is asked too
                    o = {"success": f["success"], "lat": g["latency_s"] + f["latency_s"], "cost": cost(g) + cost(f),
                         "px": g["pixels"] + f["pixels"], "fb": True}
                o["in"] = inside(t["target_rect"], c)
            o.update(task=tr["task"], trial=tr["id"], verbatim=verbatim)
            res[(tr["condition"], s)].append(o)
    names = {"F": "F · full screen (today)", "G": "G · gaze only", "GC": "GC · gaze × controls",
             "I": "I · intent × controls (no webcam)", "GCI": "GCI · gaze × controls × intent",
             "GCIa": "GCIa · GCI, \"not here\" only when gaze and intent disagree"}
    L = [f"# Gaze × controls × intent → crop · `{model}`", "",
         f"{len(ids)} tasks with a user-style request, conditions {', '.join(conditions)}. "
         "Crop ≥ 768×480, F's prompt + \"not here\" → full-screen fallback (both calls paid). "
         "Success = Holo's centre inside the target box. 95 % Wilson intervals; paired exact McNemar vs F.", ""]
    for cond in conditions:
        L += [f"## {cond}", "", "| strategy | success [95 % CI] | target in crop | fallback | median time | cost / 1000 | pixels (median) | vs F |",
              "|---|---|---|---|---|---|---|---|"]
        fby = {o["trial"]: o for o in res[(cond, "F")]}
        for s in STRATS:
            rs = res[(cond, s)]
            if not rs:
                continue
            k, n = sum(o["success"] for o in rs), len(rs)
            lo, hi = rb.wilson(k, n)
            b = sum(1 for o in rs if fby[o["trial"]]["success"] and not o["success"])
            c = sum(1 for o in rs if o["success"] and not fby[o["trial"]]["success"])
            L.append(f"| {names[s]} | {k}/{n} ({k / n:.0%}) [{lo:.0%}–{hi:.0%}] | {sum(o['in'] for o in rs) / n:.0%} | "
                     f"{sum(o['fb'] for o in rs) / n:.0%} | {st.median(o['lat'] for o in rs):.2f} s | "
                     f"${st.mean(o['cost'] for o in rs) * 1000:.3f} | {st.median(o['px'] for o in rs):,.0f} | "
                     + ("—" if s == "F" else f"+{c} / −{b}, p={rb.mcnemar(b, c):.2f}") + " |")
        # requests that quote the label vs paraphrases (the intent signal is much easier with the former)
        L.append("")
        for v, name in ((False, "paraphrased requests"), (True, "requests quoting the label")):
            parts = []
            for s in ("I", "GCI"):
                rs = [o for o in res[(cond, s)] if o["verbatim"] == v]
                if rs:
                    parts.append(f"{s} {sum(o['success'] for o in rs)}/{len(rs)}, target in crop {sum(o['in'] for o in rs) / len(rs):.0%}")
            if parts:
                L.append(f"- {name}: " + " · ".join(parts))
        L.append("")
    # global view: every condition pooled (equal weight), and a realistic mix (fair webcam 90 %, elsewhere 10 %)
    mixes = [("all conditions, equal weight", {c: 1 / len(conditions) for c in conditions})]
    if "gaze120" in conditions and "elsewhere" in conditions:
        mixes.append(("realistic: fair webcam 90 %, looking elsewhere 10 %", {"gaze120": 0.9, "elsewhere": 0.1}))
        mixes.append(("distracted: fair webcam 70 %, looking elsewhere 30 %", {"gaze120": 0.7, "elsewhere": 0.3}))
    for title, wts in mixes:
        L += [f"## Global · {title}", "", "| strategy | success | mean time | cost / 1000 | fallback |", "|---|---|---|---|---|"]
        for s in STRATS:
            acc = {"success": 0.0, "lat": 0.0, "cost": 0.0, "fb": 0.0}
            ok = True
            for c, w in wts.items():
                rs = res[(c, s)]
                if not rs:
                    ok = False
                    break
                for key in acc:
                    acc[key] += w * st.mean(float(o[key]) for o in rs)
            if ok:
                L.append(f"| {names[s]} | {acc['success']:.1%} | {acc['lat']:.2f} s | ${acc['cost'] * 1000:.3f} | {acc['fb']:.0%} |")
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
