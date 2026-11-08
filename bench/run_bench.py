"""Gaze-assisted grounding benchmark: full screenshot vs crop around the gaze (with fallback to full screen).

For each trial of bench/data/dataset.json (built by make_dataset.mjs), Holo is asked to locate one control:

  F  full screen   the whole 1440x900 screen, downscaled to 1024 px wide: what the agent sends today
                   (agent/src/hcs_agent/grounding.py: same request, same prompt, same tool, thinking off).
  G  gaze crop     only the crop around where the user looks (heatmap ROI + margin, native resolution).
                   Holo may answer "not here" (not_found / is_the_control=false): then the full screen is sent
                   (F), and both calls count in G's cost and time. That is the strategy as it would ship.

Success = the centre Holo returns, mapped back to screen pixels, falls inside the target's box.
Measured per call: wall time, prompt/completion tokens (from the API's usage), pixels and bytes sent.
F and G alternate first/second across trials (order effects, server warm-up).

    .venv/bin/python bench/run_bench.py --dry-run           # no API: geometry, pixels, crop coverage, previews
    HAI_API_KEY=... .venv/bin/python bench/run_bench.py      # real Holo calls (H Models API), ~2 calls per trial
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import statistics as st
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent" / "src"))
from hcs_agent.grounding import GROUNDING_WIDTH, H_MODELS_URL, _NOT_FOUND, _POINT  # noqa: E402  same request as the agent

CROP_CONTEXT = ("This image is a zoomed crop of the screen, around where the user is looking; "
                "the control may or may not be in it.")


def jpeg_b64(img: Image.Image) -> tuple[str, int]:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)  # as grounding.capture()
    data = buf.getvalue()
    return base64.b64encode(data).decode(), len(data)


def full_image(screen: Image.Image) -> Image.Image:
    scale = GROUNDING_WIDTH / screen.width
    return screen.resize((GROUNDING_WIDTH, int(screen.height * scale)))


def crop_image(screen: Image.Image, crop: dict) -> Image.Image:
    img = screen.crop((crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"]))
    if img.width > GROUNDING_WIDTH:  # never larger than the full-screen request
        img = img.resize((GROUNDING_WIDTH, int(img.height * GROUNDING_WIDTH / img.width)))
    return img


def prompt_for(description: str, crop: bool) -> str:
    # grounding.Grounder.locate(), word for word; the crop adds one sentence and the not_found escape.
    p = (f"{CROP_CONTEXT + ' ' if crop else ''}Locate: {description}. Give the tight bounding box of that "
         "element, coordinates in [0,1000] of the image (x1,y1 top-left; x2,y2 bottom-right).")
    if crop:
        p += " If it is really not on this screen, call not_found and describe what is visible instead."
    return p


class Holo:
    def __init__(self, model: str) -> None:
        import httpx

        key = os.environ.get("HAI_API_KEY")
        if not key:
            from hai_agents.client import default_api_key

            key = default_api_key()
        if not key:
            raise SystemExit("No H key: set HAI_API_KEY (or `holo login`), or use --dry-run.")
        self.model = model
        self.http = httpx.Client(timeout=60, headers={"Authorization": f"Bearer {key}"})

    def locate(self, img_b64: str, prompt: str, tools: list) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": prompt}]}],
            "tools": tools, "tool_choice": "required", "temperature": 0, "max_tokens": 200,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        t0 = time.perf_counter()
        for attempt in range(5):
            r = self.http.post(f"{H_MODELS_URL}/chat/completions", json=body)
            if r.status_code != 429 or attempt == 4:
                break
            time.sleep(min(float(r.headers.get("retry-after") or 0) or 1.5 * (attempt + 1), 5.0))
        latency = time.perf_counter() - t0  # includes rate-limit waits: noted, they hit both modes alike
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        fn = calls[0]["function"] if calls else {}
        args = json.loads(fn.get("arguments") or "{}") if fn else {}
        u = data.get("usage") or {}
        return {"fn": fn.get("name"), "args": args, "latency_s": latency,
                "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens")}


def to_screen(args: dict, region: dict) -> tuple[float, float] | None:
    """[0,1000] box on the image sent -> centre in screen pixels (region = the part of the screen shown)."""
    if not all(k in args for k in ("x1", "y1", "x2", "y2")):
        return None
    cx = (int(args["x1"]) + int(args["x2"])) / 2000
    cy = (int(args["y1"]) + int(args["y2"])) / 2000
    return region["x"] + cx * region["width"], region["y"] + cy * region["height"]


def hit(xy, rect, pad: float = 2.0) -> bool:
    return xy is not None and rect["x"] - pad <= xy[0] <= rect["x"] + rect["width"] + pad \
        and rect["y"] - pad <= xy[1] <= rect["y"] + rect["height"] + pad


def run_trial(holo: Holo | None, t: dict, screen: Image.Image, full_first: bool) -> dict:
    full_region = {"x": 0, "y": 0, "width": screen.width, "height": screen.height}
    f_img, g_img = full_image(screen), crop_image(screen, t["crop"])
    f_b64, f_bytes = jpeg_b64(f_img)
    g_b64, g_bytes = jpeg_b64(g_img)
    out = {"id": t["id"], "screen": t["screen"], "target": t["target"], "miss": t["gaze"]["miss"],
           "gaze_error_px": t["gaze"]["error_px"], "target_in_crop": t["target_in_crop"],
           "F": {"pixels": f_img.width * f_img.height, "bytes": f_bytes},
           "G": {"pixels": g_img.width * g_img.height, "bytes": g_bytes, "fallback": False}}
    if holo is None:
        return out

    def do_full() -> dict:
        r = holo.locate(f_b64, prompt_for(t["instruction"], crop=False), [_POINT])
        r["xy"] = to_screen(r["args"], full_region)
        r["success"] = hit(r["xy"], t["target_rect"])
        return r

    def do_gaze() -> dict:
        r = holo.locate(g_b64, prompt_for(t["instruction"], crop=True), [_POINT, _NOT_FOUND])
        found = r["fn"] == "locate" and r["args"].get("is_the_control", True)
        g = {"crop_call": {k: r[k] for k in ("latency_s", "prompt_tokens", "completion_tokens")}, "found_in_crop": bool(found)}
        if found:
            xy = to_screen(r["args"], t["crop"])
            g.update(xy=xy, success=hit(xy, t["target_rect"]), latency_s=r["latency_s"],
                     prompt_tokens=r["prompt_tokens"], completion_tokens=r["completion_tokens"], fallback=False)
        else:  # not in the crop: send the full screen, pay for both
            f = holo.locate(f_b64, prompt_for(t["instruction"], crop=False), [_POINT])
            xy = to_screen(f["args"], full_region)
            g.update(xy=xy, success=hit(xy, t["target_rect"]), latency_s=r["latency_s"] + f["latency_s"],
                     prompt_tokens=(r["prompt_tokens"] or 0) + (f["prompt_tokens"] or 0),
                     completion_tokens=(r["completion_tokens"] or 0) + (f["completion_tokens"] or 0), fallback=True)
        return g

    if full_first:
        out["F"].update(do_full())
        out["G"].update(do_gaze())
    else:
        out["G"].update(do_gaze())
        out["F"].update(do_full())
    out["F"].pop("args", None)
    return out


def preview(screen: Image.Image, t: dict, path: Path) -> None:
    """What G sends, drawn on the full screen: target (green), gaze (red), crop (red box)."""
    img = screen.convert("RGB").copy()
    d = ImageDraw.Draw(img)
    c, r, g = t["crop"], t["target_rect"], t["gaze"]
    d.rectangle([c["x"], c["y"], c["x"] + c["width"], c["y"] + c["height"]], outline=(227, 36, 43), width=4)
    d.rectangle([r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]], outline=(31, 157, 71), width=3)
    d.ellipse([g["x"] - 9, g["y"] - 9, g["x"] + 9, g["y"] + 9], fill=(227, 36, 43))
    img.resize((720, 450)).save(path, quality=80)


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def summarise(results: list[dict], meta: dict, dry: bool, model: str) -> tuple[dict, str]:
    n = len(results)
    s = {"n": n, "model": None if dry else model, "dataset": meta,
         "pixels": {"F": med(r["F"]["pixels"] for r in results), "G": med(r["G"]["pixels"] for r in results)},
         "target_in_crop": sum(r["target_in_crop"] for r in results)}
    lines = [f"# Gaze-assisted grounding benchmark — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ""]
    lines += [f"{n} trials on {len({r['screen'] for r in results})} synthetic screens (1440×900), simulated gaze with a "
              f"median error of {meta['error_px']} px, {round(meta['miss_rate'] * 100)} % of trials looking elsewhere "
              f"({sum(r['miss'] for r in results)} here). Crop = heatmap ROI + {meta['margin_px']} px, min "
              f"{meta['min_crop']['w']}×{meta['min_crop']['h']}.", ""]
    px_ratio = s["pixels"]["G"] / s["pixels"]["F"] if s["pixels"]["F"] else None
    if dry:
        lines += ["**Dry run: no model call.** Geometry only.", "",
                  "| | Full screen (F) | Gaze crop (G) |", "|---|---|---|",
                  f"| median pixels sent | {s['pixels']['F']:,} | {s['pixels']['G']:,} ({px_ratio:.0%} of F) |",
                  f"| target fully inside what is sent | {n}/{n} | {s['target_in_crop']}/{n} (the rest must fall back) |"]
        return s, "\n".join(lines) + "\n"
    F = [r["F"] for r in results]
    G = [r["G"] for r in results]
    fb = sum(g["fallback"] for g in G)
    for k, rows in (("F", F), ("G", G)):
        s[k] = {"success": sum(bool(x.get("success")) for x in rows), "median_latency_s": med(x.get("latency_s") for x in rows),
                "mean_prompt_tokens": mean(x.get("prompt_tokens") for x in rows), "mean_completion_tokens": mean(x.get("completion_tokens") for x in rows)}
    s["G"]["fallbacks"] = fb
    s["G"]["success_without_fallback"] = sum(bool(g.get("success")) and not g["fallback"] for g in G)
    tok = (s["G"]["mean_prompt_tokens"] / s["F"]["mean_prompt_tokens"]) if s["F"]["mean_prompt_tokens"] else None
    lat = (s["G"]["median_latency_s"] / s["F"]["median_latency_s"]) if s["F"]["median_latency_s"] else None
    lines += [f"Model: `{model}` (H Models API, thinking off), same request as the agent's grounding.", "",
              "| | Full screen (F) | Gaze crop + fallback (G) |", "|---|---|---|",
              f"| success (centre inside the target) | {s['F']['success']}/{n} | {s['G']['success']}/{n} |",
              f"| median time per locate | {s['F']['median_latency_s']:.2f} s | {s['G']['median_latency_s']:.2f} s ({lat:.0%} of F) |",
              f"| mean prompt tokens | {s['F']['mean_prompt_tokens']:.0f} | {s['G']['mean_prompt_tokens']:.0f} ({tok:.0%} of F) |",
              f"| median pixels sent | {s['pixels']['F']:,} | {s['pixels']['G']:,} ({px_ratio:.0%} of F) |",
              f"| fell back to full screen | — | {fb}/{n} |", "",
              "G's time and tokens include the fallback calls (both calls are paid when the crop misses).",
              "Synthetic screens and simulated gaze: a pilot on the method, not a result on real users "
              "(see docs/gaze-research-protocol.md, experiment A)."]
    return s, "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(ROOT / "bench" / "data"))
    ap.add_argument("--out", default=str(ROOT / "bench" / "results"))
    ap.add_argument("--model", default=os.environ.get("HCS_GROUNDING_MODEL", "holo4-35b-a3b"))
    ap.add_argument("--limit", type=int, default=0, help="first N trials only")
    ap.add_argument("--dry-run", action="store_true", help="no model call: geometry, pixels, previews")
    ap.add_argument("--previews", type=int, default=6, help="how many preview images to draw")
    a = ap.parse_args()

    data = json.loads((Path(a.data) / "dataset.json").read_text())
    screens = {s["name"]: Image.open(Path(a.data) / s["file"]) for s in data["screens"]}
    trials = data["trials"][: a.limit or None]
    holo = None if a.dry_run else Holo(a.model)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + ("-dry" if a.dry_run else "")
    out = Path(a.out) / stamp
    (out / "previews").mkdir(parents=True, exist_ok=True)

    results = []
    for i, t in enumerate(trials):
        r = run_trial(holo, t, screens[t["screen"]], full_first=(i % 2 == 0))
        results.append(r)
        if i < a.previews:
            preview(screens[t["screen"]], t, out / "previews" / f"{t['id']}.jpg")
        if holo is not None:
            print(f"{i + 1:3}/{len(trials)} {t['id']:32} F {'ok ' if r['F'].get('success') else 'MISS'} "
                  f"{r['F'].get('latency_s', 0):.2f}s | G {'ok ' if r['G'].get('success') else 'MISS'} "
                  f"{r['G'].get('latency_s', 0):.2f}s{' (fallback)' if r['G']['fallback'] else ''}", flush=True)
    summary, report = summarise(results, data["meta"], a.dry_run, a.model)
    (out / "results.json").write_text(json.dumps({"summary": summary, "trials": results}, indent=2))
    (out / "report.md").write_text(report)
    print(report)
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
