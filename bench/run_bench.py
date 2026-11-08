"""Gaze-assisted grounding benchmark: full screenshot vs crop around the gaze (fallback to full screen).

Dataset: bench/data/dataset.json (make_dataset.mjs): screens (synthetic Odoo-like + real websites), tasks (one
control to locate, its exact box), gaze trials per task (several webcam qualities + "looking elsewhere").

Calls (each one = the agent's own grounding request, agent/src/hcs_agent/grounding.py: same prompt, same tool,
temperature 0, thinking off):
  F   full screen downscaled to 1024 px wide: what the agent sends today          (per task)
  Fn  full screen at native 1440 px: control for sharpness (G sends native pixels) (per task)
  G   crop around the gaze (heatmap ROI + margin), native pixels, with a "not here" escape  (per gaze trial)
      When G says "not here", the strategy falls back to F: its cost and time are added (the same task's F call
      is reused: same image, same request, temperature 0).
  B   text-only baselines (tiny 28x28 image) per prompt variant: the fixed tokens, to isolate image tokens.

Calls are shuffled across models / modes / tasks and run by a few workers; every call is appended to
calls.jsonl as soon as it returns, so a run can be resumed (--resume <dir>) and reports rebuilt (--report <dir>).

    .venv/bin/python bench/run_bench.py --dry-run
    .venv/bin/python bench/run_bench.py --models holo4-35b-a3b,holo4-27b --workers 4     (HAI_API_KEY in env)
    .venv/bin/python bench/run_bench.py --report bench/results/<dir>
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import random
import statistics as st
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent" / "src"))
from hcs_agent.grounding import GROUNDING_WIDTH, H_MODELS_URL, _NOT_FOUND, _POINT  # noqa: E402  the agent's request

# Variants of G, to understand and fix its misses (same trials, same model):
#   plain   same prompt as F (no "zoomed crop" sentence), still with the not_found escape
#   min768  crop grown to at least 768x480 around its centre (less tight)
#   up1024  crop upscaled to 1024 px wide (tests "small image" vs "less context"; costs like F)
VARIANTS = {"plain": {"context": False}, "min768": {"min": (768, 480)}, "up1024": {"upscale": GROUNDING_WIDTH},
            "min768plain": {"min": (768, 480), "context": False}}

CROP_CONTEXT = ("This image is a zoomed crop of the screen, around where the user is looking; "
                "the control may or may not be in it.")


# ------------------------------------------------------------------------------------------------ images

def jpeg_b64(img: Image.Image) -> tuple[str, int]:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)  # as grounding.capture()
    data = buf.getvalue()
    return base64.b64encode(data).decode(), len(data)


def full_image(screen: Image.Image) -> Image.Image:
    return screen.resize((GROUNDING_WIDTH, int(screen.height * GROUNDING_WIDTH / screen.width)))


def crop_image(screen: Image.Image, crop: dict) -> Image.Image:
    img = screen.crop((crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"]))
    if img.width > GROUNDING_WIDTH:  # never larger than the full-screen request
        img = img.resize((GROUNDING_WIDTH, int(img.height * GROUNDING_WIDTH / img.width)))
    return img


def prompt_for(description: str, crop: bool, context: bool = True) -> str:
    # grounding.Grounder.locate(), word for word; the crop adds one sentence and the not_found escape.
    p = (f"{CROP_CONTEXT + ' ' if crop and context else ''}Locate: {description}. Give the tight bounding box of that "
         "element, coordinates in [0,1000] of the image (x1,y1 top-left; x2,y2 bottom-right).")
    if crop:
        p += " If it is really not on this screen, call not_found and describe what is visible instead."
    return p


def grow_crop(crop: dict, w: int, h: int, mw: int, mh: int) -> dict:
    """Same centre, at least mw x mh, kept on screen."""
    cw, ch = max(crop["width"], mw), max(crop["height"], mh)
    cx, cy = crop["x"] + crop["width"] / 2, crop["y"] + crop["height"] / 2
    x = int(min(max(0, cx - cw / 2), w - cw))
    y = int(min(max(0, cy - ch / 2), h - ch))
    return {"x": x, "y": y, "width": int(cw), "height": int(ch)}


def centre_crop(crop: dict, w: int, h: int) -> dict:
    """Control without gaze: a crop of the same size as the gaze crop, at the centre of the screen."""
    return {"x": (w - crop["width"]) // 2, "y": (h - crop["height"]) // 2, "width": crop["width"], "height": crop["height"]}


def to_screen(args: dict, region: dict) -> tuple[float, float] | None:
    """[0,1000] box on the image sent -> centre in screen pixels (region = the part of the screen shown)."""
    try:
        cx = (int(args["x1"]) + int(args["x2"])) / 2000
        cy = (int(args["y1"]) + int(args["y2"])) / 2000
    except (KeyError, TypeError, ValueError):
        return None
    return region["x"] + cx * region["width"], region["y"] + cy * region["height"]


def hit(xy, rect, pad: float = 2.0) -> bool:
    return xy is not None and rect["x"] - pad <= xy[0] <= rect["x"] + rect["width"] + pad \
        and rect["y"] - pad <= xy[1] <= rect["y"] + rect["height"] + pad


# ------------------------------------------------------------------------------------------------ API

class Holo:
    def __init__(self) -> None:
        import httpx

        key = os.environ.get("HAI_API_KEY")
        if not key:
            raise SystemExit("No H key: export HAI_API_KEY (e.g. `set -a; . backend/.env; set +a`), or --dry-run.")
        self.http = httpx.Client(timeout=90, headers={"Authorization": f"Bearer {key}"})

    def pricing(self) -> dict:
        r = self.http.get(f"{H_MODELS_URL}/models")
        r.raise_for_status()
        return {m["id"]: {"prompt": float(m["pricing"]["prompt"]), "completion": float(m["pricing"]["completion"])}
                for m in r.json().get("data", []) if m.get("pricing")}

    def locate(self, model: str, img_b64: str, prompt: str, tools: list) -> dict:
        body = {"model": model, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            {"type": "text", "text": prompt}]}],
            "tools": tools, "tool_choice": "required", "temperature": 0, "max_tokens": 200,
            "chat_template_kwargs": {"enable_thinking": False}}
        import httpx

        waited = 0.0
        for attempt in range(6):
            t0 = time.perf_counter()
            try:
                r = self.http.post(f"{H_MODELS_URL}/chat/completions", json=body)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 5:
                    raise
                waited += 2.0 * (attempt + 1)
                time.sleep(2.0 * (attempt + 1))  # cold model or network blip: retry, the timing restarts
                continue
            latency = time.perf_counter() - t0  # one request, rate-limit waits excluded (reported apart)
            if r.status_code not in (429, 502, 503, 504) or attempt == 5:
                break
            pause = min(float(r.headers.get("retry-after") or 0) or 1.5 * (attempt + 1), 8.0)
            waited += pause
            time.sleep(pause)
        r.raise_for_status()
        data = r.json()
        calls = data["choices"][0]["message"].get("tool_calls") or []
        fn = calls[0]["function"] if calls else {}
        try:
            args = json.loads(fn.get("arguments") or "{}") if fn else {}
        except json.JSONDecodeError:
            args = {}
        u = data.get("usage") or {}
        return {"fn": fn.get("name"), "args": args, "latency_s": latency, "retries": attempt, "waited_s": waited,
                "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens")}


# ------------------------------------------------------------------------------------------------ plan

def plan_calls(data: dict, models: list[str], f_repeats: int, control_crop: bool = True,
               variants: dict[str, list[str]] | None = None) -> list[dict]:
    tasks = {t["id"]: t for t in data["tasks"]}
    calls = []
    for m in models:
        for variant in ("full", "crop"):
            calls.append({"key": f"{m}|B|{variant}", "model": m, "mode": "B", "variant": variant})
        for t in data["tasks"]:
            for rep in range(f_repeats):
                calls.append({"key": f"{m}|F|{t['id']}|{rep}", "model": m, "mode": "F", "task": t["id"], "rep": rep})
            calls.append({"key": f"{m}|Fn|{t['id']}", "model": m, "mode": "Fn", "task": t["id"]})
        mid = f"gaze{data['meta']['errors_px'][len(data['meta']['errors_px']) // 2]}"
        for tr in data["trials"]:
            calls.append({"key": f"{m}|G|{tr['id']}", "model": m, "mode": "G", "task": tr["task"], "trial": tr["id"]})
            if control_crop and tr["condition"] == mid:  # same-size crop at the screen centre: no gaze
                calls.append({"key": f"{m}|C|{tr['id']}", "model": m, "mode": "C", "task": tr["task"], "trial": tr["id"]})
            for vname, conds in (variants or {}).items():
                if m == models[0] and tr["condition"] in conds:  # variants: first model only (the agent's)
                    calls.append({"key": f"{m}|V-{vname}|{tr['id']}", "model": m, "mode": f"V-{vname}", "task": tr["task"], "trial": tr["id"]})
    assert all(c.get("task") in tasks or c["mode"] == "B" for c in calls)
    # the mid condition key must exist when control crops are planned
    return calls


def execute(call: dict, holo: Holo, data: dict, screens: dict) -> dict:
    tasks = {t["id"]: t for t in data["tasks"]}
    if call["mode"] == "B":
        tiny, _ = jpeg_b64(Image.new("RGB", (28, 28), "white"))
        r = holo.locate(call["model"], tiny, prompt_for("the OK button", call["variant"] == "crop"),
                        [_POINT, _NOT_FOUND] if call["variant"] == "crop" else [_POINT])
        return {**call, **{k: r[k] for k in ("latency_s", "prompt_tokens", "completion_tokens")}}
    t = tasks[call["task"]]
    screen = screens[t["screen"]]
    full_region = {"x": 0, "y": 0, "width": screen.width, "height": screen.height}
    if call["mode"] in ("F", "Fn"):
        img = full_image(screen) if call["mode"] == "F" else screen
        b64, nbytes = jpeg_b64(img)
        r = holo.locate(call["model"], b64, prompt_for(t["instruction"], False), [_POINT])
        xy = to_screen(r["args"], full_region)
        found = r["fn"] == "locate"
    else:
        tr = next(x for x in data["trials"] if x["id"] == call["trial"])
        v = VARIANTS.get(call["mode"][2:], {}) if call["mode"].startswith("V-") else {}
        crop = centre_crop(tr["crop"], screen.width, screen.height) if call["mode"] == "C" else tr["crop"]
        if "min" in v:
            crop = grow_crop(crop, screen.width, screen.height, *v["min"])
        img = crop_image(screen, crop)
        if "upscale" in v and img.width < v["upscale"]:
            img = img.resize((v["upscale"], int(img.height * v["upscale"] / img.width)))
        b64, nbytes = jpeg_b64(img)
        r = holo.locate(call["model"], b64, prompt_for(t["instruction"], True, v.get("context", True)), [_POINT, _NOT_FOUND])
        found = r["fn"] == "locate" and bool(r["args"].get("is_the_control", True))
        xy = to_screen(r["args"], crop) if found else None
    tgt = t["target_rect"]
    dist = math.hypot(xy[0] - (tgt["x"] + tgt["width"] / 2), xy[1] - (tgt["y"] + tgt["height"] / 2)) if xy else None
    return {**call, "pixels": img.width * img.height, "bytes": nbytes, "fn": r["fn"], "found": found,
            "xy": xy, "success": hit(xy, tgt), "dist_px": dist, "retries": r["retries"], "waited_s": r["waited_s"],
            "latency_s": r["latency_s"], "prompt_tokens": r["prompt_tokens"], "completion_tokens": r["completion_tokens"],
            "seen": str(r["args"].get("seen") or r["args"].get("what_is_visible") or "")[:80]}


# ------------------------------------------------------------------------------------------------ stats

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def boot_ci(xs: list[float], fn=st.median, n: int = 2000, seed: int = 1) -> tuple[float, float]:
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed)
    vals = sorted(fn([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def mcnemar(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value on discordant pairs (b: only A right, c: only B right)."""
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def pct(k, n):
    return f"{k}/{n} ({k / n:.0%})" if n else "—"


# ------------------------------------------------------------------------------------------------ report

def build_report(rows: list[dict], data: dict, pricing: dict, meta_run: dict) -> tuple[dict, str]:
    tasks = {t["id"]: t for t in data["tasks"]}
    trials = {t["id"]: t for t in data["trials"]}
    by = defaultdict(list)
    for r in rows:
        by[(r["model"], r["mode"])].append(r)
    models = sorted({r["model"] for r in rows})
    out = {"run": meta_run, "dataset": data["meta"], "models": {}}
    L = [f"# Gaze-assisted grounding benchmark", "",
         f"Run {meta_run.get('started_at', '')} · {len(data['screens'])} screens "
         f"({sum(s['kind'] == 'web' for s in data['screens'])} real websites, "
         f"{sum(s['kind'] == 'synthetic' for s in data['screens'])} synthetic Odoo-like) · {len(tasks)} tasks · "
         f"{len(trials)} gaze trials · {len(rows)} calls.", "",
         "**Question.** The agent sends Holo the whole screen to find a control. If a webcam tells us roughly where "
         "the user looks, can we send only that part, pay less per screenshot, and still find it — falling back to "
         "the full screen when the gaze was elsewhere?", "",
         "- **F** full screen downscaled to 1024 px (what the agent sends today) · **Fn** full screen at native "
         "1440 px (sharpness control) · **G** crop around the gaze (heatmap ROI + 40 px, ≥ 512×320, native pixels), "
         "with fallback to F when Holo says the control is not in the crop (both calls paid).",
         "- Success = the centre Holo returns, mapped to screen pixels, lies inside the target's box (± 2 px). "
         "95 % intervals: Wilson (rates), bootstrap (medians, means). Paired test vs F: exact McNemar.",
         "- Gaze is simulated around the target with a median error of "
         f"{', '.join(str(e) for e in data['meta']['errors_px'])} px (good / fair / poor webcam), plus "
         "\"looking elsewhere\" trials (≥ 300 px away). Latency = one HTTPS request from Paris to the API "
         "(US datacenter), rate-limit waits excluded.", ""]

    for m in models:
        price = pricing.get(m, {"prompt": 0.0, "completion": 0.0})
        cost = lambda r: (r.get("prompt_tokens") or 0) * price["prompt"] + (r.get("completion_tokens") or 0) * price["completion"]  # noqa: E731
        base = {r["variant"]: r for r in by[(m, "B")]}
        F = [r for r in by[(m, "F")] if r.get("rep", 0) == 0]
        F_by_task = {r["task"]: r for r in F}
        Fn = by[(m, "Fn")]
        G = by[(m, "G")]
        mm = out["models"][m] = {}
        L += [f"## `{m}`", ""]
        fixed_f = base.get("full", {}).get("prompt_tokens")
        fixed_c = base.get("crop", {}).get("prompt_tokens")

        def line(name, rs, extra=""):
            n = len(rs)
            k = sum(bool(r.get("success")) for r in rs)
            lo, hi = wilson(k, n)
            lat = [r["latency_s"] for r in rs]
            tok = [r.get("prompt_tokens") for r in rs]
            costs = [cost(r) for r in rs]
            mlat = st.median(lat) if lat else float("nan")
            llo, lhi = boot_ci(lat)
            mt = st.mean([x for x in tok if x is not None]) if tok else float("nan")
            mc = st.mean(costs) if costs else float("nan")
            px = st.median([r["pixels"] for r in rs]) if rs else 0
            mm[name] = {"n": n, "success": k, "success_ci": [lo, hi], "median_latency_s": mlat, "latency_ci": [llo, lhi],
                        "mean_prompt_tokens": mt, "mean_cost_usd": mc, "median_pixels": px}
            return (f"| {name} | {pct(k, n)} [{lo:.0%}–{hi:.0%}] | {mlat:.2f} s [{llo:.2f}–{lhi:.2f}] | {mt:,.0f} | "
                    f"${mc * 1000:.3f} | {px:,.0f} |{extra}")

        L += ["| strategy | success [95 % CI] | median time [95 % CI] | prompt tokens (mean) | cost / 1000 locates | pixels (median) | paired vs F |",
              "|---|---|---|---|---|---|---|",
              line("F · full 1024 (today)", F, " — |"),
              line("Fn · full native", Fn, f" {paired(Fn, F_by_task)} |")]

        # G as shipped: crop call + (if not found) the F call
        def shipped(rs):
            outr = []
            for g in rs:
                f = F_by_task.get(g["task"])
                if g["found"]:
                    outr.append({**g, "fallback": False})
                elif f is None:
                    continue  # its fallback answer is not there (partial run): leave the trial out
                else:
                    outr.append({**g, "fallback": True, "success": f["success"], "latency_s": g["latency_s"] + f["latency_s"],
                                 "prompt_tokens": (g["prompt_tokens"] or 0) + (f["prompt_tokens"] or 0),
                                 "completion_tokens": (g["completion_tokens"] or 0) + (f["completion_tokens"] or 0)})
            return outr

        conds = sorted({trials[g["trial"]]["condition"] for g in G}, key=lambda c: (c == "elsewhere", int(c[4:]) if c.startswith("gaze") else 0))
        detail = []
        for c in conds:
            rs = shipped([g for g in G if trials[g["trial"]]["condition"] == c])
            label = f"G · gaze ~{c[4:]} px" if c.startswith("gaze") else "G · looking elsewhere"
            L.append(line(label, rs, f" {paired(rs, F_by_task)} |"))
            raw = [g for g in G if trials[g["trial"]]["condition"] == c]
            fb = sum(r["fallback"] for r in rs)
            in_crop = [g for g in raw if trials[g["trial"]]["target_in_crop"]]
            wrong_found = sum(1 for g in raw if g["found"] and not g["success"])
            missed_in_crop = sum(1 for g in in_crop if not g["found"])
            mm[label].update(fallbacks=fb, found_but_wrong=wrong_found, target_in_crop=len(in_crop), not_found_although_in_crop=missed_in_crop)
            detail.append(f"| {label} | {pct(len(in_crop), len(raw))} | {pct(fb, len(raw))} | {pct(missed_in_crop, len(in_crop))} | {pct(wrong_found, len(raw))} |")
        # realistic mix: the fair webcam, 1 trial in 10 looking elsewhere
        mid = f"gaze{data['meta']['errors_px'][len(data['meta']['errors_px']) // 2]}"
        if mid in conds and "elsewhere" in conds:
            a = shipped([g for g in G if trials[g["trial"]]["condition"] == mid])
            b = shipped([g for g in G if trials[g["trial"]]["condition"] == "elsewhere"])
            rnd = random.Random(7)
            mix = a + rnd.sample(b, min(len(b), max(1, round(len(a) / 9))))
            L.append(line("G · mix: fair webcam + 10 % elsewhere", mix, f" {paired(mix, F_by_task)} |"))
        C = by[(m, "C")]
        if C:
            cs = shipped(C)
            L.append(line(f"C · centre crop, no gaze (size of G ~{mid[4:]} px)", cs, f" {paired(cs, F_by_task)} |"))
            Gm = {g["trial"]: g for g in shipped([g for g in G if trials[g["trial"]]["condition"] == mid])}
            pairs = [(Gm[c["trial"]], c) for c in cs if c["trial"] in Gm]
            b = sum(1 for g, c in pairs if g["success"] and not c["success"])
            cc = sum(1 for g, c in pairs if c["success"] and not g["success"])
            mm["gaze_vs_centre"] = {"n": len(pairs), "only_gaze_right": b, "only_centre_right": cc, "p": mcnemar(b, cc)}
        for vname in VARIANTS:
            for c in conds:
                V = [r for r in by[(m, f"V-{vname}")] if trials[r["trial"]]["condition"] == c]
                if V:
                    vs = shipped(V)
                    base_g = {g["trial"]: g for g in shipped([g for g in G if trials[g["trial"]]["condition"] == c])}
                    pr = [(base_g[x["trial"]], x) for x in vs if x["trial"] in base_g]
                    b2 = sum(1 for g, x in pr if g["success"] and not x["success"])
                    c2 = sum(1 for g, x in pr if x["success"] and not g["success"])
                    L.append(line(f"G variant `{vname}` · gaze ~{c[4:]} px", vs,
                                  f" {paired(vs, F_by_task)} · vs G: +{c2} / −{b2}, p={mcnemar(b2, c2):.2f} |"))
        if C and "gaze_vs_centre" in mm:
            gv = mm["gaze_vs_centre"]
            L += ["", f"Gaze vs centre crop of the same size, same trials: gaze right and centre wrong {gv['only_gaze_right']}, "
                  f"the reverse {gv['only_centre_right']} (n={gv['n']}, McNemar p={gv['p']:.3g}). "
                  f"Centre crop fell back {pct(sum(r['fallback'] for r in cs), len(cs))}."]
        L += ["", "| G condition | target inside the crop | fell back to full screen | said \"not here\" although inside | answered in the crop but wrong |",
              "|---|---|---|---|---|", *detail, ""]
        if fixed_f and fixed_c:
            img_f = st.mean([r["prompt_tokens"] - fixed_f for r in F if r.get("prompt_tokens")])
            img_g = st.mean([g["prompt_tokens"] - fixed_c for g in G if g.get("prompt_tokens")])
            mm["image_tokens"] = {"fixed_full_prompt": fixed_f, "fixed_crop_prompt": fixed_c, "F_image": img_f, "G_image": img_g}
            L += [f"Fixed text + tool tokens: {fixed_f} (full-screen prompt), {fixed_c} (crop prompt, with the not_found tool). "
                  f"Image tokens only: F ≈ {img_f:,.0f}, G crop ≈ {img_g:,.0f} ({img_g / img_f:.0%} of F).", ""]
        # breakdowns on F vs G (fair webcam)
        Gmid = shipped([g for g in G if trials[g["trial"]]["condition"] == mid]) if mid in conds else []
        for dim, name in (("site_kind", "site"), ("target_kind", "target"), ("size", "target size")):
            vals = sorted({tasks[r["task"]][dim] for r in F})
            L += [f"| by {name} | n tasks | F success | G (~{mid[4:]} px) success | G fallback | G tokens vs F |", "|---|---|---|---|---|---|"]
            for v in vals:
                fr = [r for r in F if tasks[r["task"]][dim] == v]
                gr = [r for r in Gmid if tasks[r["task"]][dim] == v]
                ft = st.mean([r["prompt_tokens"] for r in fr]) if fr else 0
                gt = st.mean([r["prompt_tokens"] for r in gr]) if gr else 0
                L.append(f"| {v} | {len(fr)} | {pct(sum(r['success'] for r in fr), len(fr))} | {pct(sum(r['success'] for r in gr), len(gr))} | "
                         f"{pct(sum(r['fallback'] for r in gr), len(gr))} | {gt / ft:.0%} |" if ft else f"| {v} | {len(fr)} | — | — | — | — |")
            L.append("")
        L += ["| by screen | F success | G (~%s px) success | G fallback |" % mid[4:], "|---|---|---|---|"]
        for sname in [s["name"] for s in data["screens"]]:
            fr = [r for r in F if tasks[r["task"]]["screen"] == sname]
            gr = [r for r in Gmid if tasks[r["task"]]["screen"] == sname]
            L.append(f"| {sname} | {pct(sum(r['success'] for r in fr), len(fr))} | {pct(sum(r['success'] for r in gr), len(gr))} | {pct(sum(r['fallback'] for r in gr), len(gr))} |")
        reps = [r for r in by[(m, "F")] if r.get("rep", 0) == 1]
        reps = [r for r in reps if r["task"] in F_by_task]  # pairs only
        if reps:
            same = sum(1 for r in reps if (r["xy"] is not None) == (F_by_task[r["task"]]["xy"] is not None)
                       and (r["xy"] is None or math.dist(r["xy"], F_by_task[r["task"]]["xy"]) < 3))
            L += ["", f"Repeatability (F asked twice, temperature 0): same answer (± 3 px) in {pct(same, len(reps))}; "
                  f"median time {st.median([r['latency_s'] for r in reps]):.2f} s on the second ask."]
        L.append("")
    L += ["## Limits", "",
          "- Simulated gaze (gaussian around the target, error from webcam qualities measured on the vision page), "
          "not recorded gaze; real websites captured once, logged out, cookie banners included; synthetic Odoo-like "
          "screens with hand-written tasks. A pilot on the method, not a result on users (protocol, experiment A).",
          "- Real-site tasks are drawn automatically among controls with a unique label; icon targets are named by their "
          "aria-label. Instructions name the control, they are not user goals.",
          "- The fallback reuses the task's F answer (same image, same request, temperature 0) and adds its cost and time.",
          f"- Prices from the API's /models at run time: {json.dumps({m: pricing.get(m) for m in models})} (USD per token)."]
    return out, "\n".join(L) + "\n"


def paired(rs: list[dict], f_by_task: dict) -> str:
    b = c = 0
    for r in rs:
        f = f_by_task.get(r["task"])
        if f is None:
            continue
        if f["success"] and not r["success"]:
            b += 1
        elif r["success"] and not f["success"]:
            c += 1
    return f"+{c} / −{b}, p={mcnemar(b, c):.2f}"


# ------------------------------------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "bench" / "data"))
    ap.add_argument("--out", default=str(ROOT / "bench" / "results"))
    ap.add_argument("--models", default=os.environ.get("HCS_GROUNDING_MODEL", "holo4-35b-a3b"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--f-repeats", type=int, default=2, help="ask F this many times (repeatability, latency spread)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N calls of the shuffled plan (pilot)")
    ap.add_argument("--resume", help="continue a run directory (skips the calls already in calls.jsonl)")
    ap.add_argument("--report", help="rebuild report.md from a run directory, no call")
    ap.add_argument("--dry-run", action="store_true", help="no model call: geometry, pixels, previews")
    ap.add_argument("--variants", default="", help='e.g. "plain:gaze60,gaze120;min768:gaze120" (first model only)')
    a = ap.parse_args()
    variants = {v.split(":")[0]: v.split(":")[1].split(",") for v in a.variants.split(";") if ":" in v}

    data = json.loads((Path(a.data) / "dataset.json").read_text())
    screens = {s["name"]: Image.open(Path(a.data) / s["file"]).convert("RGB") for s in data["screens"]}

    if a.dry_run:
        return dry_run(data, screens, Path(a.out))

    run_dir = Path(a.report or a.resume or Path(a.out) / datetime.now().strftime("%Y%m%d-%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "calls.jsonl"
    done = {}
    if log.exists():
        for line in log.read_text().splitlines():
            r = json.loads(line)
            if "error" not in r:
                done[r["key"]] = r
    meta_path = run_dir / "run.json"
    meta_run = json.loads(meta_path.read_text()) if meta_path.exists() else {
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "models": a.models.split(","),
        "workers": a.workers, "f_repeats": a.f_repeats}

    holo = Holo()
    if "pricing" not in meta_run:
        meta_run["pricing"] = holo.pricing()
    meta_path.write_text(json.dumps(meta_run, indent=2))

    if not a.report:
        if variants:
            meta_run.setdefault("variants", {}).update(variants)
            meta_path.write_text(json.dumps(meta_run, indent=2))
        plan = plan_calls(data, meta_run["models"], meta_run["f_repeats"], variants=meta_run.get("variants"))
        random.Random(11).shuffle(plan)  # interleave models / modes / screens: no order or warm-up bias
        if a.limit:
            plan = plan[: a.limit]
        todo = [c for c in plan if c["key"] not in done]
        print(f"{len(plan)} calls planned, {len(done)} already done, {len(todo)} to go -> {run_dir}", flush=True)
        # warm-up (not recorded): one call per model
        for m in meta_run["models"]:
            tiny, _ = jpeg_b64(Image.new("RGB", (28, 28), "white"))
            t0 = time.time()
            try:
                holo.locate(m, tiny, prompt_for("the OK button", False), [_POINT])
                print(f"  warm-up {m}: {time.time() - t0:.1f} s", flush=True)
            except Exception as exc:  # noqa: BLE001 - a slow wake-up is not a reason to stop
                print(f"  warm-up {m} failed after {time.time() - t0:.0f} s ({exc}); its calls will retry", flush=True)
        lock = threading.Lock()
        t0 = time.time()
        errors = 0
        with ThreadPoolExecutor(max_workers=a.workers) as pool, log.open("a") as fh:
            futs = {pool.submit(execute, c, holo, data, screens): c for c in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                c = futs[fut]
                try:
                    r = fut.result()
                except Exception as exc:  # noqa: BLE001 - keep going, record it, a resume retries it
                    r = {**c, "error": str(exc)[:200]}
                    errors += 1
                with lock:
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
                if "error" not in r:
                    done[r["key"]] = r
                if i % 25 == 0 or i == len(todo):
                    el = time.time() - t0
                    print(f"  {i}/{len(todo)} calls, {errors} errors, {el / 60:.1f} min, ~{el / i * (len(todo) - i) / 60:.1f} min left", flush=True)
    rows = [r for r in done.values() if r["mode"] != "B" or True]
    summary, report = build_report(rows, data, meta_run["pricing"], meta_run)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    (run_dir / "report.md").write_text(report)
    print(report)
    print(f"-> {run_dir}")
    return 0


def dry_run(data: dict, screens: dict, out: Path) -> int:
    d = out / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-dry")
    (d / "previews").mkdir(parents=True, exist_ok=True)
    tasks = {t["id"]: t for t in data["tasks"]}
    fpx = full_image(next(iter(screens.values()))).size
    by = defaultdict(list)
    for tr in data["trials"]:
        by[tr["condition"]].append(tr)
    lines = [f"# Dry run: {len(data['screens'])} screens, {len(tasks)} tasks, {len(data['trials'])} gaze trials", "",
             f"F sends {fpx[0] * fpx[1]:,} px (1024 wide); Fn {1440 * 900:,} px.", "",
             "| condition | trials | target inside the crop | crop pixels (median) |", "|---|---|---|---|"]
    for c, trs in sorted(by.items()):
        px = st.median([min(t["crop"]["width"], 1024) * t["crop"]["height"] * (min(1, 1024 / t["crop"]["width"])) for t in trs])
        lines.append(f"| {c} | {len(trs)} | {pct(sum(t['target_in_crop'] for t in trs), len(trs))} | {px:,.0f} ({px / (fpx[0] * fpx[1]):.0%} of F) |")
    for tr in data["trials"][:: max(1, len(data["trials"]) // 12)][:12]:
        t = tasks[tr["task"]]
        img = screens[t["screen"]].copy()
        dr = ImageDraw.Draw(img)
        c, r, g = tr["crop"], t["target_rect"], tr["gaze"]
        dr.rectangle([c["x"], c["y"], c["x"] + c["width"], c["y"] + c["height"]], outline=(227, 36, 43), width=4)
        dr.rectangle([r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]], outline=(31, 157, 71), width=3)
        dr.ellipse([g["x"] - 9, g["y"] - 9, g["x"] + 9, g["y"] + 9], fill=(227, 36, 43))
        img.resize((720, 450)).save(d / "previews" / f"{tr['id']}.jpg", quality=80)
    (d / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"-> {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
