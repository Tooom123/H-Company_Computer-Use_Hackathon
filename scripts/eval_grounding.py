"""Check a procedure's element descriptions against a page's accessibility snapshot (offline, no model).

    uv run python scripts/eval_grounding.py --snapshot            # save the current Chrome page to runs/snapshots/
    uv run python scripts/eval_grounding.py hcompany_platform_create_api_key runs/snapshots/<file>.json

Open the right page in Chrome (in front), run --snapshot, then run the check for each procedure whose steps live on
that page: every `element` and annotation description is matched by `a11y.match`; a description that matches
nothing, or matches a weak/ambiguous candidate, is reported so it can be rewritten before a demo.
Snapshots contain labels, roles and rectangles only (no field values).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent" / "src"))

from hcs_agent import a11y  # noqa: E402
from hcs_agent.procedures import ProcedureRegistry  # noqa: E402


def snapshot() -> Path:
    info = a11y.page()
    if info is None or len(info.elements) <= 1:
        raise SystemExit("no browser page readable (is Chrome open with a page loaded?)")
    out = ROOT / "runs" / "snapshots"
    out.mkdir(parents=True, exist_ok=True)
    name = (info.url.split("//")[-1].split("?")[0].replace("/", "_").strip("_") or "page")[:60]
    path = out / f"{int(time.time())}_{name}.json"
    path.write_text(json.dumps({"url": info.url, "title": info.title,
                                "elements": [{"role": e.role, "name": e.name, "frame": e.frame} for e in info.elements]},
                               indent=0, ensure_ascii=False))
    print(f"{len(info.elements)} elements -> {path}")
    return path


def load(path: Path) -> list[a11y.Candidate]:
    data = json.loads(path.read_text())
    return [a11y.Candidate(e["role"], e["name"], tuple(e["frame"])) for e in data["elements"]]


def check(procedure_id: str, path: Path) -> int:
    proc = ProcedureRegistry().get(procedure_id)
    elements = load(path)
    bad = 0
    descs = []
    for st in proc.guide_steps:
        if st.element:
            descs.append(("step", st.element))
        for a in st.annotations or []:
            descs.append(("annotation", a.element))
    for st in proc.recovery_steps:
        if st.element:
            descs.append(("recovery", st.element))
    for kind, d in descs:
        ranked = a11y.match(d.replace("{", "").replace("}", ""), elements)
        if not ranked:
            print(f"MISS  [{kind}] {d[:80]}")
            bad += 1
            continue
        best = ranked[0]
        ties = [c for c in ranked[1:] if c.score >= best.score - 1.0]
        flag = "OK  " if best.score >= 10 and not ties else "WEAK" if best.score < 10 else "TIE "
        if flag != "OK  ":
            bad += 1
        print(f"{flag}  [{kind}] {d[:70]:70} -> {best.role[2:]} '{best.name[:30]}' score={best.score:.0f} ties={len(ties)}")
    print(f"\n{len(descs) - bad}/{len(descs)} descriptions resolve cleanly on this page")
    return bad


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] == "--snapshot":
        snapshot()
        return 0
    if len(args) < 2:
        raise SystemExit(__doc__)
    return 1 if check(args[0], Path(args[1])) else 0


if __name__ == "__main__":
    raise SystemExit(main())
