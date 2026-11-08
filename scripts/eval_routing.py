"""Routing evaluation against the real router (Holo text). Not a pytest: needs HAI_API_KEY.

    uv run python scripts/eval_routing.py            # all cases
    uv run python scripts/eval_routing.py --only task   # one kind

Prints one line per case (OK / FAIL with what came out) and the accuracy. Kinds: proc | task | ask | point.
A 'proc' case also checks the procedure id; a 'task' case accepts task OR a procedure that fits the same goal
only when listed under `accept`.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent" / "src"))

from hcs_agent.cli import _load_env  # noqa: E402
from hcs_agent.procedures import ProcedureRegistry  # noqa: E402
from hcs_agent.voice import IntentRouter  # noqa: E402


def kind_of(intent) -> str:
    if intent.procedure_id:
        return "proc"
    if intent.task:
        return "task"
    if intent.ask:
        return "ask"
    if intent.point_at:
        return "point"
    return "question" if intent.question else "none"


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    cases = yaml.safe_load((ROOT / "agent/tests/data/routing_eval.yaml").read_text())
    if args.only:
        cases = [c for c in cases if c["kind"] == args.only]
    router = IntentRouter(ProcedureRegistry())
    ok = 0
    t_all = time.time()
    for c in cases:
        t = time.time()
        intent = None
        for attempt in range(4):
            try:
                intent = router.route(c["text"])
                break
            except Exception as exc:  # noqa: BLE001
                if "429" in str(exc) and attempt < 3:
                    time.sleep(4.0 * (attempt + 1))  # Models API rate limit: back off
                    continue
                print(f"ERR  {c['text'][:60]:60} -> {str(exc)[:80]}")
                break
        if intent is None:
            continue
        time.sleep(0.8)  # pace the calls: the Models API limits bursts
        got = kind_of(intent)
        good = got == c["kind"] and (c["kind"] != "proc" or intent.procedure_id == c.get("procedure"))
        if not good and got == "proc" and intent.procedure_id in (c.get("accept") or []):
            good = True
        if not good and c["kind"] == "ask" and got == "task" and c.get("accept_task"):
            good = True
        ok += good
        detail = intent.procedure_id or intent.task or intent.ask or intent.point_at or intent.question or ""
        print(f"{'OK  ' if good else 'FAIL'} {c['text'][:60]:60} -> {got:5} {str(detail)[:70]}  ({time.time() - t:.1f}s)")
    print(f"\n{ok}/{len(cases)} = {100 * ok / max(1, len(cases)):.0f}%  in {time.time() - t_all:.0f}s")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
