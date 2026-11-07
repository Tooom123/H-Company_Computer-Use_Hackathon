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
    args = parser.parse_args(argv)

    from .config import Settings
    from .store import Store

    settings = Settings.from_env()
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
