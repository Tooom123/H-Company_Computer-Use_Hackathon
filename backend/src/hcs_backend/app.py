"""FastAPI application: ingest from the agent (bearer token), read APIs and dashboard (HTTP Basic)."""

from __future__ import annotations

import secrets
import threading
import time
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, Form, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer

from . import dashboard
from . import metrics as metrics_mod
from .autofix import AutoFixer, DevinError
from .billing import PLANS, BillingNotConfigured, create_checkout
from .config import Settings
from .escalation import build_escalation, escalation_markdown, needs_escalation
from .grouping import Group, group_cases
from .store import Store, StoredCase
from .validation import ContractError, validate

_basic = HTTPBasic(realm="HCS support dashboard", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def create_app(settings: Settings | None = None, store: Store | None = None, fixer: AutoFixer | None = None,
               start_poller: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_secrets()
    store = store or Store(settings.db_path)
    app = FastAPI(title="HCS support backend", version="0.1.0")
    app.state.settings = settings
    app.state.store = store
    if fixer is None:
        from .announce import make_announcer

        fixer = AutoFixer(settings, store, announcer=make_announcer())
    app.state.fixer = fixer

    # Devin sessions take minutes: a background thread refreshes the open ones
    if start_poller and settings.fix_poll_s > 0:
        def _poll() -> None:
            while True:
                time.sleep(settings.fix_poll_s if fixer.provider and not fixer.provider.simulated else 2)
                try:
                    fixer.poll_open()
                except Exception as e:  # never kill the thread
                    print(f"[autofix] poll failed: {e}")
        threading.Thread(target=_poll, name="autofix-poll", daemon=True).start()

    def _auto_fix(case: StoredCase) -> bool:
        if not fixer.auto_eligible(case) or store.get_fix(case.case_id):
            return False
        threading.Thread(target=lambda: fixer.request(case, trigger="auto"), daemon=True).start()
        return True
    # the landing page (another origin) may call /billing/* only
    landing_origins = {settings.landing_url.rstrip("/"), "http://localhost:5173", "http://127.0.0.1:5173"}
    app.add_middleware(CORSMiddleware, allow_origins=sorted(landing_origins), allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])

    # auth ----------------------------------------------------------------------------------------
    def require_agent(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> None:
        if creds is None or not secrets.compare_digest(creds.credentials, settings.ingest_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid ingest token",
                                headers={"WWW-Authenticate": "Bearer"})

    def require_support(creds: Annotated[HTTPBasicCredentials | None, Depends(_basic)]) -> str:
        ok = (
            creds is not None
            and secrets.compare_digest(creds.username, settings.dashboard_user)
            and secrets.compare_digest(creds.password, settings.dashboard_password)
        )
        if not ok:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required",
                                headers={"WWW-Authenticate": 'Basic realm="HCS support dashboard"'})
        return creds.username  # type: ignore[union-attr]

    Agent = Depends(require_agent)
    Support = Depends(require_support)
    from .live_demo import mount as mount_live_demo
    mount_live_demo(app, store, settings, require_support)

    # helpers -------------------------------------------------------------------------------------
    def groups() -> list[Group]:
        return group_cases(store.list_cases(), settings.group_threshold)

    def group_of(case_id: str, gs: list[Group] | None = None) -> str | None:
        for g in gs if gs is not None else groups():
            if any(c.case_id == case_id for c in g.cases):
                return g.group_id
        return None

    def get_case_or_404(case_id: str) -> StoredCase:
        case = store.get_case(case_id)
        if case is None:
            raise HTTPException(404, f"unknown case {case_id}")
        return case

    def case_view(case: StoredCase, gid: str | None) -> dict[str, Any]:
        return {
            "case_id": case.case_id,
            "session_id": case.session_id,
            "received_at": case.received_at,
            "user_ref": case.user_ref,
            "simulated": case.simulated,
            "demo_data": case.demo_data,
            "group_id": gid,
            "needs_escalation": needs_escalation(case.report),
            "report": case.report,
        }

    # ingest (agent) ------------------------------------------------------------------------------
    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.post("/cases", status_code=201, dependencies=[Agent])
    def post_case(
        report: Annotated[dict[str, Any], Body()],
        x_hcs_user: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        """Receive an InterventionReport. Optional X-HCS-User header: pseudonymous user reference used for
        'distinct users' counts (the report itself carries no user identity)."""
        try:
            validate(settings.contracts_dir, "InterventionReport", report)
        except ContractError as e:
            raise HTTPException(422, {"schema": e.schema, "errors": e.errors}) from e
        case, created = store.add_case(report, user_ref=x_hcs_user)
        fix_started = _auto_fix(case)
        return {
            "fix_requested": fix_started,
            "case_id": case.case_id,
            "created": created,
            "group_id": group_of(case.case_id),
            "needs_escalation": needs_escalation(case.report),
            "dashboard_url": f"/dashboard/cases/{case.case_id}",
        }

    @app.post("/events", status_code=202, dependencies=[Agent])
    def post_event(event: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        try:
            validate(settings.contracts_dir, "AgentEvent", event)
        except ContractError as e:
            raise HTTPException(422, {"schema": e.schema, "errors": e.errors}) from e
        store.add_event(event)
        return {"accepted": True}

    # billing (public: called by the landing page) -------------------------------------------------
    @app.get("/billing/plans")
    def billing_plans() -> dict[str, Any]:
        return {
            "configured": settings.stripe_secret_key.startswith(("sk_test_", "rk_test_")),
            "plans": {k: {"name": v["name"], "amount_eur": v["unit_amount"] / 100, "mode": v["mode"]} for k, v in PLANS.items()},
        }

    @app.post("/billing/checkout")
    def billing_checkout(body: Annotated[dict[str, Any], Body()]) -> dict[str, str]:
        plan = body.get("plan")
        if plan not in PLANS:
            raise HTTPException(422, f"unknown plan {plan!r}")
        try:
            return {"url": create_checkout(plan, settings.stripe_secret_key, settings.landing_url)}
        except BillingNotConfigured as e:
            raise HTTPException(503, str(e)) from e

    # read APIs (support) -------------------------------------------------------------------------
    @app.get("/cases", dependencies=[Support])
    def list_cases() -> list[dict[str, Any]]:
        gs = groups()
        return [case_view(c, group_of(c.case_id, gs)) for c in store.list_cases()]

    @app.get("/cases/{case_id}", dependencies=[Support])
    def get_case(case_id: str) -> dict[str, Any]:
        return case_view(get_case_or_404(case_id), group_of(case_id))

    @app.get("/cases/{case_id}/escalation", dependencies=[Support])
    def get_escalation(case_id: str) -> dict[str, Any]:
        return build_escalation(get_case_or_404(case_id))

    @app.get("/cases/{case_id}/escalation.md", dependencies=[Support], response_class=PlainTextResponse)
    def get_escalation_md(case_id: str) -> str:
        return escalation_markdown(get_case_or_404(case_id))

    @app.get("/groups", dependencies=[Support])
    def list_groups() -> list[dict[str, Any]]:
        return [g.summary() for g in groups()]

    @app.get("/groups/{group_id}", dependencies=[Support])
    def get_group(group_id: str) -> dict[str, Any]:
        for g in groups():
            if g.group_id == group_id:
                return g.summary() | {"cases": [case_view(c, group_id) for c in g.cases]}
        raise HTTPException(404, f"unknown group {group_id}")

    @app.get("/sessions/{session_id}/events", dependencies=[Support])
    def session_events(session_id: str) -> list[dict[str, Any]]:
        return store.list_events(session_id)

    # dashboard (support) -------------------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/dashboard")

    @app.get("/dashboard", response_class=HTMLResponse, dependencies=[Support])
    def dash_index() -> str:
        return dashboard.index_page(groups(), store.list_cases())

    @app.get("/metrics", dependencies=[Support])
    def get_metrics() -> dict[str, Any]:
        """Reliability per scenario, real sessions only (simulated ones are counted apart)."""
        return metrics_mod.compute(store.list_cases())

    @app.get("/dashboard/metrics", response_class=HTMLResponse, dependencies=[Support])
    def dash_metrics() -> str:
        return dashboard.metrics_page(metrics_mod.compute(store.list_cases()))

    @app.get("/dashboard/groups/{group_id}", response_class=HTMLResponse, dependencies=[Support])
    def dash_group(group_id: str) -> str:
        for g in groups():
            if g.group_id == group_id:
                return dashboard.group_page(g)
        raise HTTPException(404, f"unknown group {group_id}")

    @app.get("/dashboard/cases/{case_id}", response_class=HTMLResponse, dependencies=[Support])
    def dash_case(case_id: str) -> str:
        case = get_case_or_404(case_id)
        return dashboard.case_page(case, group_of(case_id), fix=fixer.refresh(case_id),
                                   fix_repo=fixer.repo_for(case))

    @app.get("/dashboard/cases/{case_id}/dossier", response_class=HTMLResponse, dependencies=[Support])
    def dash_dossier(case_id: str) -> str:
        return dashboard.dossier_page(get_case_or_404(case_id))

    @app.post("/dashboard/cases/{case_id}/fix", dependencies=[Support], include_in_schema=False)
    def dash_case_fix(case_id: str) -> RedirectResponse:
        request_fix(case_id)
        return RedirectResponse(f"/dashboard/cases/{case_id}", status_code=303)

    # auto-fix (support) ------------------------------------------------------------------------
    @app.post("/cases/{case_id}/fix", dependencies=[Support])
    def request_fix(case_id: str) -> dict[str, Any]:
        """Ask Devin to fix the defect behind this case and open a PR (software must be on the allowlist)."""
        case = get_case_or_404(case_id)
        try:
            return fixer.request(case, trigger="manual")
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except DevinError as e:
            raise HTTPException(503, str(e)) from e

    @app.post("/cases/{case_id}/fix/message", dependencies=[Support])
    def reply_fix(case_id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        """Answer the Devin session of this case (it waits for us: access granted, a clarification...)."""
        get_case_or_404(case_id)
        message = str(body.get("message") or "").strip()
        if not message:
            raise HTTPException(422, "empty message")
        try:
            return fixer.reply(case_id, message)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        except DevinError as e:
            raise HTTPException(503, str(e)) from e

    @app.post("/dashboard/cases/{case_id}/fix/message", dependencies=[Support], include_in_schema=False)
    def dash_reply_fix(case_id: str, message: Annotated[str, Form()]) -> RedirectResponse:
        reply_fix(case_id, {"message": message})
        return RedirectResponse(f"/dashboard/cases/{case_id}", status_code=303)

    @app.get("/cases/{case_id}/fix", dependencies=[Support])
    def get_fix(case_id: str) -> dict[str, Any]:
        get_case_or_404(case_id)
        fix = fixer.refresh(case_id)
        if fix is None:
            raise HTTPException(404, "no fix requested for this case")
        return fix

    @app.get("/fixes", dependencies=[Support])
    def list_fixes() -> list[dict[str, Any]]:
        return store.list_fixes()

    return app
