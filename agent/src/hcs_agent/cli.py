"""Command line for testing the agent directly on the Mac.

    hcs-agent procedures
    hcs-agent run --procedure odoo_crm_followup_activity --role "new sales rep" \
        --goal "Help me schedule the follow-up on Acme Demo" -p opportunity="Acme Demo" -p due_date=2026-11-14
    hcs-agent serve [--port 8765] [--mock]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from .backend import make_backend
from .contract import AgentEvent, ApproveCommand, InterventionRequest, Mode, NextCommand, State, StopCommand
from .procedures import ProcedureRegistry
from .runner import Intervention


_LAST_LOOKUP_AT = 0.0
_LAST_ACTION: dict = {}  # latest agent action (summary, pointer) for on-screen narration
_MAGNET = {"level": int(os.environ.get("HCS_AUTONOMY", "1")), "widget": None, "current": None}
_VOICE: dict = {"ptt": None, "state": None}  # push-to-talk handle and its last state, visible to the guide loop


def _new_request_pending() -> bool:
    ptt = _VOICE.get("ptt")
    return ptt is not None and not ptt.transcripts.empty()


def _ensure_magnet():
    """Bottom-left autonomy slider; clicks change the running intervention and the default for the next ones."""
    if _MAGNET["widget"] is not None or sys.platform != "darwin":
        return _MAGNET["widget"]
    try:
        from .overlay import AUTONOMY_LABELS, MagnetWidget

        def on_change(level: int) -> None:
            _MAGNET["level"] = level
            print(f"\n  [magnet] {AUTONOMY_LABELS[level]}", flush=True)
            it = _MAGNET["current"]
            if it is not None and not it.state.terminal:
                it.set_autonomy(level)

        _MAGNET["widget"] = MagnetWidget(_MAGNET["level"], on_change)
    except Exception as exc:  # noqa: BLE001
        print(f"(magnet unavailable: {exc})")
    return _MAGNET["widget"]


def _short(text: str, n: int) -> str:
    """One short phrase: cut at the first sentence end, then at n chars."""
    t = (text or "").strip()
    for sep in (". ", " ; ", " : "):
        if sep in t and t.index(sep) < n:
            t = t[: t.index(sep) + (1 if sep == ". " else 0)]
            break
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _print_event(e: AgentEvent) -> None:
    global _LAST_LOOKUP_AT
    if e.type == "knowledge":
        _LAST_LOOKUP_AT = time.time()
    if e.type == "step" and e.data["step"]["kind"] == "action" and e.data["step"].get("detail", {}).get("tools"):
        det = e.data["step"]["detail"]
        _LAST_ACTION.update(summary=e.message, pointer=det.get("pointer"), element=det.get("element"),
                            at=time.time(), id=e.event_id)
    tag = "SIM " if e.simulated else ""
    msg = e.message or ""
    if e.type == "step":
        print(f"  {tag}[{e.data['step']['kind']}] {msg}")
    elif e.type == "guidance":
        s = e.data["step"]
        print(f"\n{tag}>>> STEP {s['index']}: {s['instruction']}\n    where: {s['where']}\n    why: {s['why']}"
              + (f"\n    pointer: {s['pointer']}" if s.get("pointer") else ""))
    elif e.type == "knowledge":
        n = e.data["note"]
        print(f"{tag}[docs:{n['purpose']}] {msg} ({len(n['sources'])} sources)")
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
                                  procedure_id=args.procedure, parameters=params, mode=args.mode)
    # `run` is explicit about the mode: the Magnet follows the flag instead of overriding it.
    _MAGNET["level"] = 2 if args.mode == "act" else min(_MAGNET["level"], 1)
    return _execute(request, make_backend(args.mock), Path(args.runs_dir), auto_approve=args.yes,
                    scope_note=args.scope_note, stop_after=args.stop_after, auto_next=args.auto_next,
                    overlay=not args.no_overlay)


def _execute(request: InterventionRequest, backend, runs_dir: Path, *, auto_approve: bool = False,
             scope_note: str | None = None, stop_after: float | None = None, auto_next: bool = False,
             overlay: bool = True, ov=None) -> int:
    """Run one intervention from the terminal: plan, approval, execution, report."""
    # The Magnet is the authority: 0 = show only, 1 = guide + takeover when stuck, 2 = the agent does it.
    request.autonomy = _MAGNET["level"]
    request.mode = Mode.act if request.autonomy >= 2 else Mode.guide
    it = Intervention(request, backend, ProcedureRegistry(), _print_event, runs_dir)
    _MAGNET["current"] = it
    if ov is not None:
        _ensure_magnet()
    print(f"session {request.session_id} (backend: {'MOCK' if backend.simulated else 'H desktop'}, "
          f"mode: {request.mode.value}, autonomy: {request.autonomy})")
    it.start()
    if it.state.terminal:
        return 1
    if auto_approve:
        print(">> auto-approving (--yes)")
    else:
        print("\nProposed plan:")
        print(json.dumps(it.plan.model_dump(), indent=2))
        answer = input("\nApprove this scope? [y/N] ").strip().lower()
        if answer != "y":
            it.approve(ApproveCommand(approved=False))
            it.wait()
            return 2
    it.approve(ApproveCommand(approved=True, scope_note=scope_note))

    if stop_after:
        def _stopper() -> None:
            time.sleep(stop_after)
            print(f">> requesting stop after {stop_after}s")
            it.stop(StopCommand(reason="cli --stop-after"))
        threading.Thread(target=_stopper, daemon=True).start()

    try:
        if request.mode.value == "guide":
            _guide_loop(it, auto=auto_next, overlay=overlay, ov=ov)
        elif ov is not None:
            it.takeover = True  # act mode: narrate the agent's actions on screen
            _guide_loop(it, auto=True, overlay=overlay, ov=ov)
        else:
            it.wait()
    except KeyboardInterrupt:
        print(">> Ctrl+C: stopping (new commands blocked locally, asking H to cancel)")
        it.stop(StopCommand(reason="Ctrl+C"))
        _wait_stopped(it, ov, timeout=60)
    if it.report:
        print(f"\nreport: {it.runs_dir / 'report.json'}")
        print(json.dumps(it.report.to_support_summary(), indent=2))
        if it.report.timings.stop_latency_s is not None:
            print(f"stop latency: {it.report.timings.stop_latency_s:.2f}s")
        if ov is not None and not _new_request_pending():
            _show_outcome(ov, it)
        return 0 if it.report.status.value == "resolved" else 3
    return 1


def _wait_stopped(it: Intervention, ov, timeout: float) -> None:
    """Wait for the stop to land while keeping the overlay alive (badge "Arrêt…", note cleared)."""
    deadline = time.time() + timeout
    if ov is not None:
        ov.hide()
        ov.badge("Arrêt en cours…", pulsing=True)
        try:
            ov.run_until(lambda: (it.state.terminal and it.report is not None) or time.time() > deadline, None, 0.1,
                         hide_at_end=False)
        except KeyboardInterrupt:
            print(">> second Ctrl+C: not waiting for H any longer")
        ov.badge(None)
    else:
        it.wait(timeout)
    if it.report is None:
        print("(stop requested; the H session did not confirm within the timeout — see runs/hcs-agent.log)")


def _flash(ov, text: str, doodle: str | None = None, why: str = "", seconds: float = 3.5) -> None:
    """Short on-screen note outside of a task (routing feedback), then back to the listening hint."""
    if ov is None:
        return
    from .overlay import Scene

    ov.badge(None)
    ov.show_scene(Scene(text=text, why=why, doodle=doodle))
    t0 = time.time()
    ov.run_until(lambda: time.time() - t0 > seconds, None, 0.1)
    ov.badge("⌘H : nouvelle demande")


def _show_outcome(ov, it: Intervention, seconds: float = 5.0) -> None:
    """Closing note on screen: what happened, in one line, then back to listening."""
    from .overlay import Scene

    r = it.report
    doodle = None
    if r.status.value == "resolved":
        text, why, doodle = "Terminé : résultat vérifié dans le logiciel", "", "check"
    elif r.status.value == "abandoned":
        text, why = "Arrêté. Rien d'autre ne sera modifié.", ""
    else:
        text = "Je n'ai pas pu vérifier le résultat"
        why = (r.escalation.blocked_on if r.escalation else "") or "Dossier transmis au support."
        doodle = "question"
    ov.badge(None)
    ov.show_scene(Scene(text=text, why=why[:120], doodle=doodle))
    t0 = time.time()
    hold = 2.5 if r.status.value == "abandoned" else seconds
    try:
        ov.run_until(lambda: time.time() - t0 > hold, None, 0.1)
    except KeyboardInterrupt:
        ov.hide()


def cmd_talk(args: argparse.Namespace) -> int:
    """Push-to-talk: hold the key, speak, release; the request is routed and run after approval."""
    from .voice import IntentRouter, PushToTalk, intent_to_request

    registry = ProcedureRegistry()
    vocab = sorted({p.software for p in registry.all()} | {
        "Odoo", "CRM", "Acme Demo", "Acme", "relance", "opportunité", "activité", "pipeline", "gagnée", "To Do"})
    ov = None
    if not args.no_overlay and sys.platform == "darwin":
        from .overlay import Overlay

        ov = Overlay()
    voice_state = {"s": None}

    def on_state(s: str) -> None:
        voice_state["s"] = s
        _VOICE["state"] = s
        print(f"  [voice] {s}", flush=True)
        if ov is None:
            return
        if s == "recording":
            ov.badge("Je t'écoute…", pulsing=True)
        elif s == "transcribing":
            ov.badge("Transcription…")
        else:
            ov.badge(None)

    if ov is not None:
        _ensure_magnet()
    backend = make_backend(args.mock)
    if hasattr(backend, "_desktop_channel"):
        # Open the H desktop channel (and its driver) BEFORE any key listener exists: the driver's keyboard
        # setup and a running listener initialising at the same time abort the process on macOS.
        print("  preparing the desktop channel…", flush=True)
        backend._desktop_channel()
    ptt = PushToTalk(key_name=args.key or os.environ.get("HCS_PTT_KEY", "cmd+h"), vocabulary=vocab, on_state=on_state)
    _VOICE["ptt"] = ptt
    router = IntentRouter(registry)
    ptt.start()
    print(f"Hold [{ptt.key_name}] and tell me what you need (e.g. \"montre-moi comment planifier une relance sur "
          f"Acme Demo pour vendredi\"). Release to send. Ctrl+C to quit.")
    if ov is not None:
        ov.badge("Maintiens ⌘H et dis ce que tu veux faire" if "cmd" in ptt.key_name else f"Maintiens {ptt.key_name} et parle")

    def next_transcript() -> str:
        """Wait for a transcript while keeping the overlay (badge) alive on the main thread."""
        box: dict[str, str] = {}

        def tick() -> None:
            t = ptt.wait_transcript(timeout=0)
            if t is not None:
                box["text"] = t

        if ov is not None:
            ov.run_until(lambda: "text" in box, tick, 0.1, hide_at_end=False)
        else:
            while "text" not in box:
                tick()
                time.sleep(0.1)
        return box["text"]

    last_request = None
    try:
        while True:
            text = next_transcript()
            print(f"\nYou said: \"{text}\"")
            if last_request is not None and re.match(r"^\W*(reprends|reprise|continue|recommence|encore)\b", text.strip(), re.I):
                request = InterventionRequest(**last_request.model_dump(exclude={"session_id"}))
                print(f"  -> resuming {request.procedure_id} from the current screen")
                try:
                    _execute(request, backend, Path(args.runs_dir), auto_approve=not args.confirm,
                             overlay=not args.no_overlay, ov=ov)
                except Exception:  # noqa: BLE001
                    import traceback

                    traceback.print_exc()
                print(f"\nHold [{ptt.key_name}] for another request, Ctrl+C to quit.")
                continue
            if ov is not None:
                ov.badge("Je réfléchis…", pulsing=True)
            try:
                intent = router.route(text)
            except Exception as exc:  # noqa: BLE001
                print(f"  could not understand the request ({exc}); try again.")
                _flash(ov, "Je n'ai pas compris, redis-le autrement", "question")
                continue
            if not intent.procedure_id:
                print("  I don't have a procedure for that yet. Known: " + ", ".join(p.id for p in registry.all()))
                _flash(ov, "Je ne sais pas encore faire ça", "question",
                       why="Je sais : créer une opportunité, planifier une relance, mettre une note, qualifier")
                continue
            proc = registry.get(intent.procedure_id)
            for name in list(intent.missing):
                param = next((p for p in proc.parameters if p.name == name), None)
                if param is None or param.default is not None:
                    intent.missing.remove(name)  # the procedure default applies (e.g. due date in one week)
                    continue
                val = input(f"  {param.description}? ").strip()
                if val:
                    intent.parameters[name] = val
            request = intent_to_request(intent)
            last_request = request
            print(f"  -> {request.procedure_id} | mode {request.mode.value} | {request.parameters}")
            try:
                code = _execute(request, backend, Path(args.runs_dir), auto_approve=not args.confirm,
                                overlay=not args.no_overlay, ov=ov)
            except Exception:  # noqa: BLE001 - never die silently between two requests
                import traceback

                traceback.print_exc()
                code = 1
            if args.once:
                return code
            if _new_request_pending():
                continue  # the user spoke during the task: it was stopped, run the new request right away
            if ov is not None:
                ov.badge(f"⌘H : nouvelle demande" if "cmd" in ptt.key_name else f"{ptt.key_name} : nouvelle demande")
            print(f"\nHold [{ptt.key_name}] for another request, Ctrl+C to quit.")
    except KeyboardInterrupt:
        print("\nbye")
        ptt.stop()
        if ov is not None:
            ov.hide()
            ov.badge(None)
        if _MAGNET.get("widget") is not None:
            _MAGNET["widget"].close()
        return 0


class _ScreenWatcher:
    """Detects that the user acted: the screen differs from when the step was shown, then holds still."""

    def __init__(self, min_dwell_s: float = 1.0, settle_s: float = 0.8, threshold: float = 12.0) -> None:
        self.min_dwell_s, self.settle_s, self.threshold = min_dwell_s, settle_s, threshold
        self._base = None
        self._armed_at = 0.0
        self._changed_at: float | None = None
        self._last = None
        self._last_t = 0.0

    def _grab(self):
        try:
            import numpy as np

            from .grounding import grab_screen

            img = grab_screen().convert("L").resize((96, 60))
            return np.asarray(img, dtype=np.float32)
        except Exception:  # noqa: BLE001
            return None

    def arm(self) -> None:
        self._armed_at = time.time()
        self._changed_at = None
        self._base = None  # the baseline is taken on the next tick, once the overlay is drawn (it is not captured)
        self._last_t = 0.0

    def changed_and_settled(self) -> bool:
        import numpy as np

        now = time.time()
        if now - self._last_t < 0.4:
            return False
        self._last_t = now
        frame = self._grab()
        if frame is None:
            return False
        if self._base is None:
            self._base, self._last = frame, frame
            return False
        if now - self._armed_at < self.min_dwell_s:
            self._last = frame
            return False
        # Block-wise: a small dialog or card changing anywhere must count, not just the screen average.
        def block_diff(a, b) -> float:
            d = np.abs(a - b).reshape(6, 10, 8, 12).mean(axis=(1, 3))  # 96x60 -> 6x8 blocks
            return float(d.max())

        diff_base = block_diff(frame, self._base)
        diff_last = block_diff(frame, self._last)
        self._last = frame
        if diff_base > self.threshold:
            if diff_last < self.threshold / 3:
                if self._changed_at is None:
                    self._changed_at = now
                elif now - self._changed_at >= self.settle_s:
                    return True
            else:
                self._changed_at = None
        return False


class _InputWatcher:
    """Knows what the user actually did since the step was shown: clicks, typed keys, Enter/Tab, Escape.
    Reads the process-wide InputHub (one event tap for the whole program)."""

    def __init__(self) -> None:
        self.armed_at = 0.0
        self.last_click = 0.0
        self.typed = 0
        self.last_submit = 0.0  # Enter or Tab
        self.last_key = 0.0  # Escape
        self._hub = None
        try:
            from pynput import keyboard

            from .inputs import InputHub

            self._kb = keyboard
            self._hub = InputHub.get()
            self._hub.subscribe(self._on_event)
        except Exception as exc:  # noqa: BLE001 - no input monitoring: screen watcher only
            print(f"(input watcher unavailable: {exc})")

    def _on_event(self, event: str, payload) -> None:
        now = time.time()
        if event == "click":
            magnet = _MAGNET.get("widget")
            if magnet is not None and payload and magnet.contains(*payload):
                return  # changing the Magnet level is not the user doing the step
            self.last_click = now
        elif event == "key_down":
            if payload in (self._kb.Key.enter, self._kb.Key.tab):
                self.last_submit = now
            elif payload == self._kb.Key.esc:
                self.last_key = now
            elif getattr(payload, "char", None) or payload in (self._kb.Key.space, self._kb.Key.backspace):
                self.typed += 1

    def arm(self) -> None:
        self.armed_at = time.time()
        self.typed = 0

    def acted(self, kind: str, settle_s: float = 0.5) -> bool:
        now = time.time()
        if kind == "wait":  # the agent itself decides when to move on (screen polling)
            return False
        if kind == "key":  # Escape (or a click outside, which also closes menus)
            return (self.last_key > self.armed_at or self.last_click > self.armed_at + 0.3) and \
                now - max(self.last_key, self.last_click) >= settle_s
        if kind == "info":  # read it; any click or Enter moves on, or 9 s pass
            return self.last_click > self.armed_at + 0.3 or self.last_submit > self.armed_at or now - self.armed_at > 9
        if kind == "type":
            if self.last_submit > self.armed_at and now - self.last_submit >= settle_s:
                return True
            return self.typed > 0 and self.last_click > self.armed_at + 0.3 and now - self.last_click >= settle_s
        return self.last_click > self.armed_at + 0.3 and now - self.last_click >= settle_s

    def stop(self) -> None:
        if self._hub is not None:
            self._hub.unsubscribe(self._on_event)


def _guide_loop(it: Intervention, auto: bool, overlay: bool, ov=None) -> None:
    """Main-thread loop for guide mode: draws the pencil overlay and reads Enter / notes / q from stdin."""
    import select

    if ov is None and overlay and sys.platform == "darwin":
        try:
            from .overlay import Overlay

            ov = Overlay()
        except Exception as exc:  # noqa: BLE001
            print(f"(overlay unavailable: {exc})")
    shown_step = 0
    prompted = False
    watcher = _ScreenWatcher()
    inputs = _InputWatcher()

    def advance(done: bool = True, note: str | None = None) -> None:
        if ov:
            ov.hide()
        if it.state is not State.awaiting_user:
            return  # stopped or moved on in the meantime: nothing to answer
        try:
            it.next(NextCommand(done=done, note=note))
        except RuntimeError:
            pass

    def status_badge() -> None:
        if ov is None:
            return
        if _VOICE.get("state") in ("recording", "transcribing"):
            return  # the voice badge is already shown; do not overwrite it mid-sentence
        if it.state is State.awaiting_user:
            ov.badge(None)
        elif time.time() - _LAST_LOOKUP_AT < 4:
            ov.badge("Je cherche sur le web…", pulsing=True)
        elif it.state is State.running:
            ov.badge("Je regarde l'écran…", pulsing=True)
        elif it.state is State.verifying:
            ov.badge("Je vérifie le résultat…", pulsing=True)
        elif it.state.terminal:
            ov.badge(None)

    shown_action = {"id": None}

    def narrate() -> None:
        """Takeover: show what the agent is doing, where, as it does it."""
        if ov is None or not _LAST_ACTION or _LAST_ACTION.get("id") == shown_action["id"]:
            return
        shown_action["id"] = _LAST_ACTION["id"]
        from .overlay import Scene

        ov.badge("Je prends la main…", pulsing=True)
        text = _short(_LAST_ACTION.get("summary") or "", 110)
        why = _LAST_ACTION.get("element") or ""
        ov.show_scene(Scene(text=text, why=why[:60], target=_LAST_ACTION.get("pointer")))

    interrupted = {"done": False}

    def tick() -> None:
        nonlocal shown_step, prompted
        if not interrupted["done"] and _new_request_pending() and not it.state.terminal:
            interrupted["done"] = True
            print("\n>> new voice request: stopping the current task", flush=True)
            if ov:
                ov.hide()
                ov.badge("Nouvelle demande…", pulsing=True)
            it.stop(StopCommand(reason="replaced by a new voice request"))
            return
        status_badge()
        if getattr(it, "takeover", False) and it.state in (State.running, State.verifying):
            narrate()
        if it.state is State.awaiting_user and it.guidance:
            g = it.guidance[-1]
            if g.index != shown_step:
                shown_step = g.index
                prompted = False
                watcher.arm()
                inputs.arm()
                if ov:
                    from .overlay import Mark, Scene

                    verbose = os.environ.get("HCS_GUIDE_VERBOSE", "").lower() in {"1", "true", "yes"}
                    why = g.why if (verbose or g.kind in ("info", "wait")) else ""
                    ov.show_scene(Scene(
                        text=g.instruction, target=g.pointer, target_box=g.box, why=_short(why, 90), step=g.index,
                        doodle="question" if "je ne le vois" in g.instruction else None,
                        marks=[Mark(a.shape, a.pointer, _short(a.text, 28), tuple(a.size) if a.size else (0, 0),
                                    None, a.box)
                               for a in g.annotations if a.pointer]))
            if auto:
                time.sleep(0.3)
                advance()
                return
            if not prompted:
                print(f"\n  step {g.index}: {g.instruction}  [{g.kind}] (I continue when you act; q = stop) ",
                      end="", flush=True)
                prompted = True
            g = it.guidance[-1]
            if g.kind != "wait" and (inputs.acted(g.kind) or (g.kind == "click" and watcher.changed_and_settled())):
                print(f"\n  {'input' if inputs.acted(g.kind) else 'screen'} detected, next…", flush=True)
                advance()
                return
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if ready:
                ans = sys.stdin.readline().strip()
                if ans.lower() == "q":
                    if ov:
                        ov.hide()
                    it.stop(StopCommand(reason="user quit"))
                else:
                    advance(done=ans == "", note=ans or None)
        elif ov and it.state.terminal and it.guidance and it.guidance[-1].last and it.guidance[-1].pointer:
            pass  # keep the last annotation until exit

    def finished() -> bool:
        if it.state.terminal and it.report is not None:
            return True
        if it._thread is not None and not it._thread.is_alive():
            print("\n[worker thread ended without a report — see runs/hcs-agent.log]", flush=True)
            return True
        return False

    try:
        if ov:
            ov.run_until(finished, tick, 0.1)
        else:
            while not finished():
                tick()
                it.wait(0.1)
    finally:
        inputs.stop()


def cmd_cleanup(args: argparse.Namespace) -> int:
    """Close orphaned desktop command channels left by killed runs; they hold concurrency slots."""
    import httpx
    from hai_agents.client import default_api_key

    base = os.environ.get("HAI_BASE_URL", "https://agp.eu.hcompany.ai").rstrip("/")
    headers = {"Authorization": f"Bearer {default_api_key()}"}
    with httpx.Client(headers=headers, timeout=20) as http:
        items = http.get(f"{base}/api/v1/trajectories/", params={"size": 100}).json().get("items", [])
        stale = [t for t in items if t.get("status") in {"pending", "running", "idle"}]
        for t in stale:
            code = http.delete(f"{base}/api/v1/trajectories/{t['id']}").status_code
            print(f"closed {t['id']} ({t.get('type')}, {t.get('status')}) -> {code}")
        quota = http.get(f"{base}/api/v2/sessions/quota").json()
    print(f"{len(stale)} channel(s) closed; quota: {quota.get('active')}/{quota.get('limit')} active")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    serve(host=args.host, port=args.port, mock=args.mock)
    return 0


def _load_env() -> None:
    """Load the nearest .env (current dir, then parents), without overriding the shell environment."""
    from dotenv import find_dotenv, load_dotenv

    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


class _Tee:
    """Mirror a stream into a log file so a silent exit still leaves a trace."""

    def __init__(self, stream, log):
        self._s, self._log = stream, log

    def write(self, data):
        self._s.write(data)
        self._log.write(data)
        self._log.flush()
        return len(data)

    def flush(self):
        self._s.flush()
        self._log.flush()

    def __getattr__(self, name):
        return getattr(self._s, name)


def _setup_logging() -> None:
    import atexit
    import faulthandler
    import logging
    import threading

    log_dir = Path(os.environ.get("HCS_RUNS_DIR", "runs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "hcs-agent.log", "a", encoding="utf-8")
    log.write(f"\n===== start {time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} argv={sys.argv[1:]}\n")
    sys.stdout, sys.stderr = _Tee(sys.stdout, log), _Tee(sys.stderr, log)
    faulthandler.enable(file=log, all_threads=True)  # native crash -> traceback of every thread in the log
    logging.basicConfig(level=logging.INFO, stream=log, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def thread_hook(args):
        import traceback

        print(f"\n[thread {args.thread.name if args.thread else '?'} crashed]", flush=True)
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_hook
    atexit.register(lambda: log.write(f"===== exit {time.strftime('%H:%M:%S')}\n"))
    import signal

    def on_signal(signum, frame):  # noqa: ARG001
        log.write(f"===== signal {signal.Signals(signum).name} at {time.strftime('%H:%M:%S')}\n")
        log.flush()
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, on_signal)
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    _load_env()
    _setup_logging()
    ap = argparse.ArgumentParser(prog="hcs-agent", description="Customer-success assistant agent (H desktop).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("procedures", help="List available procedures").set_defaults(fn=cmd_procedures)

    run = sub.add_parser("run", help="Run one intervention from the terminal")
    run.add_argument("--software", default="odoo")
    run.add_argument("--procedure", required=True)
    run.add_argument("--role")
    run.add_argument("--goal", required=True)
    run.add_argument("--symptom")
    run.add_argument("--mode", choices=["act", "guide"], default="act",
                     help="act: the agent does it; guide: the agent explains and points, you do it")
    run.add_argument("--no-overlay", action="store_true", help="guide mode without the on-screen pencil overlay")
    run.add_argument("--auto-next", action="store_true", help="guide mode: auto-confirm each step (tests only)")
    run.add_argument("-p", "--param", action="append", metavar="KEY=VALUE")
    run.add_argument("--scope-note")
    run.add_argument("-y", "--yes", action="store_true", help="Approve the plan without prompting")
    run.add_argument("--stop-after", type=float, metavar="SECONDS", help="Test the stop button after N seconds")
    run.add_argument("--mock", action="store_true", help="Use the simulated backend (no H, no desktop control)")
    run.add_argument("--runs-dir", default="runs")
    run.set_defaults(fn=cmd_run)

    talk = sub.add_parser("talk", help="Push-to-talk: hold a key, say what you need, release")
    talk.add_argument("--key", help="key or combo, e.g. cmd+h, f9, alt_r (default: HCS_PTT_KEY or cmd+h)")
    talk.add_argument("--confirm", action="store_true", help="Ask for approval before running (default: the spoken request is the approval)")
    talk.add_argument("--once", action="store_true", help="Exit after the first request")
    talk.add_argument("--mock", action="store_true")
    talk.add_argument("--no-overlay", action="store_true")
    talk.add_argument("--runs-dir", default="runs")
    talk.set_defaults(fn=cmd_talk)

    sub.add_parser("cleanup", help="Close orphaned H sessions/channels that hold concurrency slots").set_defaults(fn=cmd_cleanup)

    srv = sub.add_parser("serve", help="Serve the local API for the Electron app")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8765)
    srv.add_argument("--mock", action="store_true")
    srv.set_defaults(fn=cmd_serve)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
