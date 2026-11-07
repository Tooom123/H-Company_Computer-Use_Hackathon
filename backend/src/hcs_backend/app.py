"""FastAPI application: ingest from the agent (bearer token), read APIs and dashboard (HTTP Basic)."""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer

from . import dashboard
from .billing import PLANS, BillingNotConfigured, create_checkout
from .config import Settings
from .escalation import build_escalation, escalation_markdown, needs_escalation
from .grouping import Group, group_cases
from .store import Store, StoredCase
from .validation import ContractError, validate

_basic = HTTPBasic(realm="HCS support dashboard", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_secrets()
    store = store or Store(settings.db_path)
    app = FastAPI(title="HCS support backend", version="0.1.0")
    app.state.settings = settings
    app.state.store = store
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
        return {
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

    @app.get("/dashboard/groups/{group_id}", response_class=HTMLResponse, dependencies=[Support])
    def dash_group(group_id: str) -> str:
        for g in groups():
            if g.group_id == group_id:
                return dashboard.group_page(g)
        raise HTTPException(404, f"unknown group {group_id}")

    @app.get("/dashboard/cases/{case_id}", response_class=HTMLResponse, dependencies=[Support])
    def dash_case(case_id: str) -> str:
        return dashboard.case_page(get_case_or_404(case_id), group_of(case_id))

    return app
