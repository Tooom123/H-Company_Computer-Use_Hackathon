"""Command line for testing the agent directly on the Mac.

    hcs-agent procedures
    hcs-agent run --procedure odoo_crm_followup_activity --role "new sales rep" \
        --goal "Help me schedule the follow-up on Acme Demo" -p opportunity="Acme Demo" -p due_date=2026-11-14
    hcs-agent serve [--port 8765] [--mock]
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

from .backend import make_backend
from .contract import AgentEvent, ApproveCommand, InterventionRequest, StopCommand
from .procedures import ProcedureRegistry
from .runner import Intervention


def _print_event(e: AgentEvent) -> None:
    tag = "SIM " if e.simulated else ""
    msg = e.message or ""
    if e.type == "step":
        print(f"  {tag}[{e.data['step']['kind']}] {msg}")
    elif e.type == "finished":
        print(f"{tag}== finished: {msg}")
    else:
        print(f"{tag}[{e.type}] ({e.state.value}) {msg}")


def cmd_procedures(_: argparse.Namespace) -> int:
    for p in ProcedureRegistry().all():
        params = ", ".join(f"{x.name}{'' if x.required else '?'}" for x in p.parameters)
        print(f"{p.id:40} {p.software:8} attempts={p.max_attempts} reversible={p.reversible} params: {params}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    params = dict(kv.split("=", 1) for kv in args.param or [])
    request = InterventionRequest(software=args.software, role=args.role, goal=args.goal, symptom=args.symptom,
                                  procedure_id=args.procedure, parameters=params)
    backend = make_backend(args.mock)
    it = Intervention(request, backend, ProcedureRegistry(), _print_event, Path(args.runs_dir))
    print(f"session {request.session_id} (backend: {'MOCK' if backend.simulated else 'H desktop'})")
    it.start()
    if it.state.terminal:
        return 1
    if args.yes:
        print(">> auto-approving (--yes)")
    else:
        print("\nProposed plan:")
        print(json.dumps(it.plan.model_dump(), indent=2))
        answer = input("\nApprove this scope? [y/N] ").strip().lower()
        if answer != "y":
            it.approve(ApproveCommand(approved=False))
            it.wait()
            return 2
    it.approve(ApproveCommand(approved=True, scope_note=args.scope_note))

    if args.stop_after:
        def _stopper() -> None:
            time.sleep(args.stop_after)
            print(f">> requesting stop after {args.stop_after}s")
            it.stop(StopCommand(reason="cli --stop-after"))
        threading.Thread(target=_stopper, daemon=True).start()

    try:
        it.wait()
    except KeyboardInterrupt:
        print(">> Ctrl+C: stopping")
        it.stop(StopCommand(reason="Ctrl+C"))
        it.wait(60)
    if it.report:
        print(f"\nreport: {it.runs_dir / 'report.json'}")
        print(json.dumps(it.report.to_support_summary(), indent=2))
        if it.report.timings.stop_latency_s is not None:
            print(f"stop latency: {it.report.timings.stop_latency_s:.2f}s")
        return 0 if it.report.status.value == "resolved" else 3
    return 1


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    serve(host=args.host, port=args.port, mock=args.mock)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hcs-agent", description="Customer-success assistant agent (H desktop).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("procedures", help="List available procedures").set_defaults(fn=cmd_procedures)

    run = sub.add_parser("run", help="Run one intervention from the terminal")
    run.add_argument("--software", default="odoo")
    run.add_argument("--procedure", required=True)
    run.add_argument("--role")
    run.add_argument("--goal", required=True)
    run.add_argument("--symptom")
    run.add_argument("-p", "--param", action="append", metavar="KEY=VALUE")
    run.add_argument("--scope-note")
    run.add_argument("-y", "--yes", action="store_true", help="Approve the plan without prompting")
    run.add_argument("--stop-after", type=float, metavar="SECONDS", help="Test the stop button after N seconds")
    run.add_argument("--mock", action="store_true", help="Use the simulated backend (no H, no desktop control)")
    run.add_argument("--runs-dir", default="runs")
    run.set_defaults(fn=cmd_run)

    srv = sub.add_parser("serve", help="Serve the local API for the Electron app")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8765)
    srv.add_argument("--mock", action="store_true")
    srv.set_defaults(fn=cmd_serve)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
