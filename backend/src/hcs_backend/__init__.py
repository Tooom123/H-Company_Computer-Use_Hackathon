"""HCS backend: receives InterventionReports, stores cases, groups similar difficulties, serves the
support dashboard (authenticated). Owner: Tom."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hcs-backend", description=__doc__)
    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="run the API and dashboard (default)")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    seed = sub.add_parser("seed-demo", help="load the demo cases (flagged demo_data + simulated) into the DB")
    seed.add_argument("--reset", action="store_true", help="delete existing demo cases first")
    sub.add_parser("reset-demo", help="delete every case flagged demo_data")
    fx = sub.add_parser("fix", help="ask Devin to fix the defect behind a case and follow it until the PR")
    fx.add_argument("case_id")
    fx.add_argument("--timeout", type=float, default=3600, help="seconds to follow the session (default 1h)")
    args = parser.parse_args(argv)

    from .config import Settings
    from .store import Store

    settings = Settings.from_env()
    if args.cmd == "fix":
        import time

        from .autofix import AutoFixer, is_done

        store = Store(settings.db_path)
        case = store.get_case(args.case_id)
        if case is None:
            print(f"unknown case {args.case_id} (seed-demo first?)")
            return 2
        fixer = AutoFixer(settings, store)
        fix = fixer.request(case, trigger="cli")
        print(f"provider={fix['provider']} simulated={fix['simulated']} repo={fix['repo']} branch={fix['branch']}")
        print(f"session {fix.get('session_id')}  {fix.get('session_url')}")
        t0, last = time.time(), None
        while fix and not is_done(fix) and time.time() - t0 < args.timeout:
            time.sleep(2 if fix["simulated"] else 20)
            fix = fixer.refresh(args.case_id)
            line = f"{fix['status']} {fix.get('status_detail') or ''} pr={fix.get('pr_url')}"
            if line != last:
                print(f"[{int(time.time() - t0):>4}s] {line}")
                last = line
        print(f"result: {fix.get('result')}")
        print(f"error: {fix.get('error') or fix.get('last_error')}" if fix.get("error") or fix.get("last_error") else "")
        return 0 if fix.get("pr_url") else 1

    if args.cmd in ("seed-demo", "reset-demo"):
        store = Store(settings.db_path)
        if args.cmd == "reset-demo" or args.reset:
            print(f"deleted {store.delete_all(demo_only=True)} demo case(s)")
        if args.cmd == "seed-demo":
            from .demo import demo_cases

            for report, user in demo_cases():
                store.add_case(report, user_ref=user)
                print("seeded", report["case_id"], report["status"], report["category"])
        return 0

    import uvicorn

    from .app import create_app

    host = getattr(args, "host", None) or settings.host
    port = getattr(args, "port", None) or settings.port
    for line in settings.generated_secrets:
        print(f"[hcs-backend] no secret configured, generated for this run: {line}")
    print(f"[hcs-backend] db={settings.db_path} dashboard=http://{host}:{port}/dashboard")
    uvicorn.run(create_app(settings), host=host, port=port)
    return 0
