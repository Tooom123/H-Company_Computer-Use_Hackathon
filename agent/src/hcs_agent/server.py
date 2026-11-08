"""Local HTTP + WebSocket server consumed by the Electron app.

    POST /interventions                 -> create + start (preflight, plan proposed)
    POST /interventions/{id}/approve    -> ApproveCommand
    POST /interventions/{id}/stop       -> StopCommand
    POST /interventions/{id}/next       -> NextCommand (guide mode: user did / could not do the step)
    POST /interventions/{id}/autonomy   -> AutonomyCommand (Magnet level 0-2, live)
    POST /interventions/{id}/feedback   -> FeedbackCommand
    GET  /interventions/{id}            -> state, plan, steps so far
    GET  /interventions/{id}/report     -> InterventionReport (once finished)
    GET  /interventions/{id}/events     -> all events so far
    WS   /interventions/{id}/ws         -> live AgentEvent stream (replays history on connect)
    GET  /procedures                    -> available procedures
    GET  /health

Run with `hcs-agent serve` (real H) or `HCS_MOCK=1 hcs-agent serve` (simulated).
Binds to 127.0.0.1 only: this process holds the H API key and drives the machine.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from .backend import Backend, make_backend
from .contract import (AgentEvent, ApproveCommand, AutonomyCommand, FeedbackCommand, InterventionRequest,
                       NextCommand, StopCommand)
from .procedures import ProcedureRegistry
from .runner import Intervention


class Hub:
    """Keeps interventions, their event history and WebSocket subscribers."""

    def __init__(self, backend: Backend, runs_dir: Path) -> None:
        self.backend = backend
        self.registry = ProcedureRegistry()
        self.runs_dir = runs_dir
        self.interventions: dict[str, Intervention] = {}
        self.events: dict[str, list[AgentEvent]] = {}
        self.queues: dict[str, set[asyncio.Queue[AgentEvent]]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def _sink(self, event: AgentEvent) -> None:
        self.events.setdefault(event.session_id, []).append(event)
        if self.loop is None:
            return
        for q in list(self.queues.get(event.session_id, ())):
            self.loop.call_soon_threadsafe(q.put_nowait, event)

    def create(self, request: InterventionRequest) -> Intervention:
        if request.session_id in self.interventions:
            raise HTTPException(409, "session_id already exists")
        it = Intervention(request, self.backend, self.registry, self._sink, self.runs_dir)
        self.interventions[request.session_id] = it
        self.events.setdefault(request.session_id, [])
        it.start()
        return it

    def get(self, session_id: str) -> Intervention:
        try:
            return self.interventions[session_id]
        except KeyError:
            raise HTTPException(404, "unknown intervention") from None

    def subscribe(self, session_id: str) -> asyncio.Queue[AgentEvent]:
        q: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self.queues.setdefault(session_id, set()).add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[AgentEvent]) -> None:
        self.queues.get(session_id, set()).discard(q)


def _snapshot(it: Intervention) -> dict[str, Any]:
    return {
        "session_id": it.request.session_id,
        "state": it.state.value,
        "simulated": it.backend.simulated,
        "request": it.request.model_dump(),
        "plan": it.plan.model_dump() if it.plan else None,
        "steps": [s.model_dump(mode="json") for s in it.steps],
        "declared": it.declared.model_dump(),
        "verification": it.verification.model_dump() if it.verification else None,
        "guidance": [g.model_dump() for g in it.guidance],
        "autonomy": it.autonomy,
        "takeover": it.takeover,
        "mode": it.request.mode.value,
        "knowledge": [k.model_dump() for k in it.knowledge],
        "error": it.error,
        "report_ready": it.report is not None,
    }


def create_app(backend: Backend | None = None, runs_dir: Path | None = None) -> FastAPI:
    backend = backend or make_backend()
    hub = Hub(backend, runs_dir or Path(os.environ.get("HCS_RUNS_DIR", "runs")))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        hub.loop = asyncio.get_running_loop()
        yield

    app = FastAPI(title="HCS Agent", version="0.1.0", lifespan=lifespan)
    app.state.hub = hub

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "simulated": backend.simulated}

    @app.get("/procedures")
    def procedures() -> list[dict[str, Any]]:
        return [p.model_dump(include={"id", "software", "software_version", "title", "reversible",
                                      "max_attempts", "parameters", "preconditions"})
                for p in hub.registry.all()]

    @app.post("/interventions", status_code=201)
    def create(request: InterventionRequest) -> dict[str, Any]:
        return _snapshot(hub.create(request))

    @app.get("/interventions/{session_id}")
    def get(session_id: str) -> dict[str, Any]:
        return _snapshot(hub.get(session_id))

    @app.post("/interventions/{session_id}/approve")
    def approve(session_id: str, cmd: ApproveCommand) -> dict[str, Any]:
        it = hub.get(session_id)
        try:
            it.approve(cmd)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return _snapshot(it)

    @app.post("/interventions/{session_id}/stop")
    def stop(session_id: str, cmd: StopCommand | None = None) -> dict[str, Any]:
        it = hub.get(session_id)
        it.stop(cmd or StopCommand())
        return _snapshot(it)

    @app.post("/interventions/{session_id}/next")
    def next_step(session_id: str, cmd: NextCommand | None = None) -> dict[str, Any]:
        it = hub.get(session_id)
        try:
            it.next(cmd or NextCommand())
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return _snapshot(it)

    @app.post("/interventions/{session_id}/autonomy")
    def autonomy(session_id: str, cmd: AutonomyCommand) -> dict[str, Any]:
        """Magnet: change the help level while the intervention runs (2 while guiding = takeover)."""
        it = hub.get(session_id)
        it.set_autonomy(cmd.level)
        return _snapshot(it)

    @app.post("/interventions/{session_id}/feedback")
    def feedback(session_id: str, cmd: FeedbackCommand) -> dict[str, Any]:
        it = hub.get(session_id)
        it.add_feedback(cmd)
        return _snapshot(it)

    @app.get("/interventions/{session_id}/report")
    def report(session_id: str) -> dict[str, Any]:
        it = hub.get(session_id)
        if it.report is None:
            raise HTTPException(425, "report not ready")
        return it.report.model_dump(mode="json")

    @app.get("/interventions/{session_id}/events")
    def events(session_id: str) -> list[dict[str, Any]]:
        hub.get(session_id)
        return [e.model_dump(mode="json") for e in hub.events.get(session_id, [])]

    @app.websocket("/interventions/{session_id}/ws")
    async def ws(websocket: WebSocket, session_id: str) -> None:
        if session_id not in hub.interventions:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        q = hub.subscribe(session_id)
        try:
            for e in list(hub.events.get(session_id, [])):
                await websocket.send_text(e.model_dump_json())
            while True:
                e = await q.get()
                await websocket.send_text(e.model_dump_json())
                if e.type == "finished":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            hub.unsubscribe(session_id, q)

    return app


def serve(host: str = "127.0.0.1", port: int = 8765, mock: bool | None = None) -> None:
    import uvicorn

    uvicorn.run(create_app(make_backend(mock)), host=host, port=port, log_level="info")
