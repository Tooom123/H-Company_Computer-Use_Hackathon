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
_SPEECH: dict = {"speaker": None, "ready": False}  # ElevenLabs voice reading the on-screen notes aloud
# Notes shown in every session (closing notes, routing feedback): synthesised ahead so they play at once.
_COMMON_LINES = ("Done, checking the result", "Done: result verified in the software",
                 "Stopped. Nothing else will be changed.", "I could not verify the result",
                 "Case handed over to support.", "I did not get that, please rephrase", "I cannot do that yet")


def _speaker():
    """The process voice (created once, on first use); None when muted or unavailable."""
    if not _SPEECH["ready"]:
        _SPEECH["ready"] = True
        try:
            from .speech import make_speaker

            _SPEECH["speaker"] = make_speaker()
        except Exception as exc:  # noqa: BLE001 - speech is a bonus, never a reason to fail
            print(f"(voice unavailable: {exc})")
    return _SPEECH["speaker"]


def _voice_for(ov) -> None:
    """Tie the overlay to the voice: a note is drawn when its sentence starts being heard."""
    sp = _speaker()
    if ov is not None and sp is not None:
        # Through _SPEECH, not a bound method: the app can switch voices, which replaces the speaker.
        ov.hold_reveal = lambda: _SPEECH["speaker"] is not None and _SPEECH["speaker"].holding()


def _say(*segments: str, interrupt: bool = True) -> None:
    """Read aloud what is about to be written on screen. Call it right BEFORE `show_scene`."""
    sp = _SPEECH["speaker"]
    if sp is not None:
        sp.say(*segments, interrupt=interrupt)


def _hush() -> None:
    sp = _SPEECH["speaker"]
    if sp is not None:
        sp.stop()


def _prefetch_voice(request: InterventionRequest) -> None:
    """Synthesise the guide's sentences now, so each step is heard the moment it is drawn."""
    sp = _SPEECH["speaker"]
    if sp is None or request.mode is not Mode.guide or not request.procedure_id:
        return
    try:
        script = ProcedureRegistry().get(request.procedure_id).bound(request).guide_script()
    except Exception:  # noqa: BLE001 - unknown procedure or params: the runner reports it, not us
        return
    verbose = os.environ.get("HCS_GUIDE_VERBOSE", "").lower() in {"1", "true", "yes"}
    texts = []
    for st in script:
        texts.append(st.instruction)
        if st.why and (verbose or st.action in ("info", "wait")):
            texts.append(_short(st.why, 90))
    sp.prefetch(texts + list(_COMMON_LINES))


_CONTROL: dict = {"server": None, "command": None, "backend": None, "since": None}
_TEST_SENTENCE = "Hi, I'm your H Companion. Hold Command H and tell me what you need."


def _set_autonomy(level: int) -> None:
    """One place for every source (Magnet click, desktop app): default for next tasks + the running one."""
    level = max(0, min(2, int(level)))
    _MAGNET["level"] = level
    if _MAGNET.get("widget") is not None:
        _MAGNET["widget"].set_level(level)
    it = _MAGNET["current"]
    if it is not None and not it.state.terminal:
        it.set_autonomy(level)


def _control_status() -> dict:
    it = _MAGNET["current"]
    cur = None
    if it is not None:
        g = it.guidance[-1] if it.guidance else None
        total = None
        try:
            total = len(it._bound.guide_script()) if getattr(it, "_bound", None) else None
        except Exception:  # noqa: BLE001
            pass
        r = it.report
        cur = {
            "session_id": it.request.session_id, "procedure_id": it.request.procedure_id, "goal": it.request.goal,
            "mode": it.request.mode.value, "state": it.state.value, "terminal": it.state.terminal,
            "takeover": bool(getattr(it, "takeover", False)), "autonomy": it.autonomy,
            "step": {"index": g.index, "instruction": g.instruction, "kind": g.kind, "total": total} if g else None,
            "last_action": _LAST_ACTION.get("summary") if getattr(it, "takeover", False) else None,
            "cost_usd": round(float(getattr(it, "cost_usd", 0.0) or 0.0), 4),
            "started_at": it.timings.started_at.isoformat() if it.timings.started_at else None,
            "status": r.status.value if r else None,
            "verified": bool(r and r.verification and r.verification.satisfied),
            "blocked_on": (r.escalation.blocked_on if r and r.escalation else None),
        }
    sp = _SPEECH["speaker"]
    ptt = _VOICE.get("ptt")
    backend = _CONTROL.get("backend")
    return {
        "agent": {"command": _CONTROL["command"], "pid": os.getpid(), "since": _CONTROL["since"],
                  "simulated": bool(getattr(backend, "simulated", False))},
        "autonomy": _MAGNET["level"],
        "voice": {"state": _VOICE.get("state"), "last_text": _VOICE.get("last_text"),
                  "ptt_key": getattr(ptt, "key_name", None)},
        "speech": {"available": sp is not None, "enabled": bool(sp is not None and not sp.muted),
                   "voice": os.environ.get("HCS_TTS_VOICE") or "EXAVITQu4vr4xnSDxMaL",
                   "speed": float(os.environ.get("HCS_TTS_SPEED") or 1.0),
                   "speaking": bool(sp is not None and sp.speaking)},
        "current": cur,
    }


def _control_stop() -> bool:
    _hush()
    it = _MAGNET["current"]
    if it is None or it.state.terminal:
        return False
    print("\n>> stop requested from the desktop app", flush=True)
    it.stop(StopCommand(reason="Stop pressed in the desktop app"))
    return True


def _control_voice(opts: dict) -> dict:
    sp = _SPEECH["speaker"]
    if "voice" in opts or "speed" in opts:
        if "voice" in opts:
            os.environ["HCS_TTS_VOICE"] = opts["voice"]
        if "speed" in opts:
            os.environ["HCS_TTS_SPEED"] = f"{opts['speed']:g}"
        muted = sp.muted if sp is not None else False
        try:
            from .speech import make_speaker

            new = make_speaker()
        except Exception as exc:  # noqa: BLE001
            print(f"(voice unavailable: {exc})")
            new = None
        if new is not None:
            new.muted = muted
            _SPEECH["speaker"], old = new, sp
            if old is not None:
                old.close()
            sp = new
    if "enabled" in opts and sp is not None:
        sp.muted = not opts["enabled"]
        if sp.muted:
            sp.stop()
    return _control_status()["speech"]


def _control_test_voice() -> bool:
    sp = _SPEECH["speaker"]
    if sp is None or sp.muted:
        return False
    sp.say(_TEST_SENTENCE)
    return True


def _app_presence(present: bool) -> None:
    """The desktop app holds the autonomy setting while it is open: the on-screen Magnet steps aside."""
    w = _MAGNET.get("widget")
    if w is not None:
        w.hide() if present else w.show()
    print(f"  [app] desktop app {'connected: Magnet hidden' if present else 'closed: Magnet back on screen'}",
          flush=True)


def _start_control(runs_dir: Path, command: str, backend) -> None:
    """Serve the desktop app's control point (127.0.0.1). A busy port only means no app, never a failed run."""
    if _CONTROL["server"] is not None or os.environ.get("HCS_CONTROL", "1").lower() in {"0", "false", "off"}:
        return
    from .control import DEFAULT_PORT, ControlServer, Controller

    _CONTROL.update(command=command, backend=backend, since=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _speaker()  # the app's Voice page can set and test the voice even before the first note is shown
    ctl = Controller(runs_dir, status=_control_status, set_autonomy=_set_autonomy, stop=_control_stop,
                     set_voice=_control_voice, test_voice=_control_test_voice, on_app_presence=_app_presence)
    try:
        port = int(os.environ.get("HCS_CONTROL_PORT", DEFAULT_PORT))
        _CONTROL["server"] = ControlServer(ctl, port).start()
        print(f"  desktop app control point: http://127.0.0.1:{port}", flush=True)
    except OSError as exc:
        print(f"(desktop app control point unavailable: {exc})", flush=True)


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
            print(f"\n  [magnet] {AUTONOMY_LABELS[level]}", flush=True)
            _set_autonomy(level)

        _MAGNET["widget"] = MagnetWidget(_MAGNET["level"], on_change)
        srv = _CONTROL.get("server")
        if srv is not None and srv.ctl.app_present:
            _MAGNET["widget"].hide()  # the desktop app is already open and holds the setting
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
    elif e.type == "step" and e.data["step"]["kind"] == "observation":
        # The agent took a new screenshot: the page may have changed, marks for the previous action are stale.
        _LAST_ACTION["stale_at"] = time.time()
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
    backend = make_backend(args.mock)
    _start_control(Path(args.runs_dir), "run", backend)
    return _execute(request, backend, Path(args.runs_dir), auto_approve=args.yes,
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
    if ov is not None:
        _prefetch_voice(request)
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
        _hush()
        it.stop(StopCommand(reason="Ctrl+C"))
        _wait_stopped(it, ov, timeout=20)
    if getattr(it, "uplink", None):  # let the support backend receive the report before we move on
        it.uplink.flush(10)
        print(f"support backend: {it.uplink.sent} sent, {it.uplink.failed} failed ({it.uplink.url})")
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
        ov.badge("Stopping…", pulsing=True)
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


def _point_at(ov, backend, element: str, seconds: float = 6.0) -> None:
    """'Where is X?': locate it on the current screen and circle it, no procedure involved."""
    from .overlay import Scene

    if ov is not None:
        ov.badge("Looking at the screen…", pulsing=True)
    loc = backend.locate(element, "Point at what the user asks about on the screen in front of them.") \
        if hasattr(backend, "locate") else None
    if loc is None or not loc.found:
        print(f"  could not find: {element}")
        _say(f"I can't see {element} on this screen.")
        _flash(ov, f"I can't see {element} here", "question", why=(loc.visible[:80] if loc else ""))
        return
    text = f"Here: {element}"
    print(f"  -> pointing at {element} {loc.screen_xy}")
    _say(text)
    if ov is None:
        return
    ov.badge(None)
    ov.show_scene(Scene(text=text, target=loc.screen_xy, target_box=loc.box))
    t0 = time.time()
    try:
        ov.run_until(lambda: time.time() - t0 > seconds or _new_request_pending(), None, 0.1)
    except KeyboardInterrupt:
        ov.hide()
    ov.badge("⌘H: new request")


def _flash(ov, text: str, doodle: str | None = None, why: str = "", seconds: float = 3.5) -> None:
    """Short on-screen note outside of a task (routing feedback), then back to the listening hint."""
    if ov is None:
        return
    from .overlay import Scene

    ov.badge(None)
    _say(text, why)
    ov.show_scene(Scene(text=text, why=why, doodle=doodle))
    t0 = time.time()
    ov.run_until(lambda: time.time() - t0 > seconds, None, 0.1)
    ov.badge("⌘H: new request")


def _show_outcome(ov, it: Intervention, seconds: float = 5.0) -> None:
    """Closing note on screen: what happened, in one line, then back to listening."""
    from .overlay import Scene

    r = it.report
    doodle = None
    if r.status.value == "resolved":
        text, why, doodle = "Done: result verified in the software", "", "check"
    elif r.status.value == "abandoned":
        text, why = "Stopped. Nothing else will be changed.", ""
    else:
        text = "I could not verify the result"
        why = (r.escalation.blocked_on if r.escalation else "") or "Case handed over to support."
        doodle = "question"
    ov.badge(None)
    _say(text, why[:120])
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
    # Proper nouns only: common words in the vocabulary made Gladia swap real words for them.
    vocab = ["Acme Demo", "Acme Corp", "Odoo"]
    ov = None
    if not args.no_overlay and sys.platform == "darwin":
        from .overlay import Overlay

        ov = Overlay()
    voice_state = {"s": None}

    def on_state(s: str) -> None:
        voice_state["s"] = s
        _VOICE["state"] = s
        print(f"  [voice] {s}", flush=True)
        if s == "recording":
            _hush()  # the user speaks: we stop talking (and the mic does not hear us)
        if ov is None:
            return
        if s == "recording":
            ov.badge("Listening…", pulsing=True)
        elif s == "transcribing":
            ov.badge("Transcribing…")
        else:
            ov.badge(None)

    if ov is not None:
        _ensure_magnet()
        _voice_for(ov)
        if _SPEECH["speaker"] is not None:
            _SPEECH["speaker"].prefetch(list(_COMMON_LINES))
    backend = make_backend(args.mock)
    _start_control(Path(args.runs_dir), "talk", backend)
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
        ov.badge("Hold ⌘H and say what you need" if "cmd" in ptt.key_name else f"Hold {ptt.key_name} and speak")

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
    history: list[str] = []  # the current clarification conversation (user turns + assistant questions)
    try:
        while True:
            text = next_transcript()
            _VOICE["last_text"] = text
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
                ov.badge("Thinking…", pulsing=True)
            history.append(f"User: {text}")
            try:
                intent = router.route(text, history[:-1])
            except Exception as exc:  # noqa: BLE001
                print(f"  could not understand the request ({exc}); try again.")
                _flash(ov, "I did not get that, please rephrase", "question")
                continue
            if intent.point_at and not intent.procedure_id:
                _point_at(ov, backend, intent.point_at)
                history.clear()
                continue
            if intent.task and not intent.procedure_id:
                # No script for this: the general agent works from the screen, with the vendor docs as context.
                from .voice import generic_request

                doc = None
                try:
                    ans = backend.knowledge.ask(f"{intent.task} — how is it done, step by step?",
                                                software=intent.software or "hcompany", depth="fast")
                    doc = ans.as_text(2) if ans and ans.answer else None
                    if ans:
                        print(f"  [docs] {ans.answer[:120]}")
                except Exception:  # noqa: BLE001
                    pass
                request = generic_request(intent, doc)
                last_request = request
                history.clear()
                print(f"  -> no script for this; general agent | {request.software} | mode {request.mode.value} | {request.goal}")
                _say("No script for this one, I will work it out from the screen.")
                try:
                    code = _execute(request, backend, Path(args.runs_dir), auto_approve=not args.confirm,
                                    overlay=not args.no_overlay, ov=ov)
                except Exception:  # noqa: BLE001
                    import traceback

                    traceback.print_exc()
                if args.once:
                    return 0
                if ov is not None and not _new_request_pending():
                    ov.badge("⌘H: new request")
                continue
            if not intent.procedure_id or intent.missing:
                # Ask instead of guessing; the answer comes through ⌘H and is merged with this turn.
                q = intent.question or "What exactly should I help with?"
                print(f"  ? {q}")
                history.append(f"Assistant: {q}")
                if len([h for h in history if h.startswith("Assistant:")]) >= 4:
                    history.clear()  # too many rounds: start fresh rather than loop
                _say(q)
                _flash(ov, q, "question", seconds=6.0)
                continue
            history.clear()
            request = intent_to_request(intent)
            last_request = request
            history.append(f"User: {text}")  # kept so a follow-up correction can be merged with this request
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
                ov.badge(f"⌘H: new request" if "cmd" in ptt.key_name else f"{ptt.key_name}: new request")
            print(f"\nHold [{ptt.key_name}] for another request, Ctrl+C to quit.")
    except KeyboardInterrupt:
        print("\nbye")
        ptt.stop()
        if _SPEECH["speaker"] is not None:
            _SPEECH["speaker"].close()
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
    if ov is not None and ov.hold_reveal is None:  # `run`: the overlay (and its voice) start here
        _voice_for(ov)
        _prefetch_voice(it.request)
    shown_step = 0
    prompted = False
    watcher = _ScreenWatcher()
    inputs = _InputWatcher()

    def advance(done: bool = True, note: str | None = None) -> None:
        _hush()  # the user did the step: the sentence about it is over
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
            ov.badge("Searching the web…", pulsing=True)
        elif it.state is State.running:
            ov.badge("Looking at the screen…", pulsing=True)
        elif it.state is State.verifying:
            ov.badge("Checking the result…", pulsing=True)
        elif it.state.terminal:
            ov.badge(None)

    shown_action: dict = {"id": None, "at": None}

    def narrate() -> None:
        """Takeover: show what the agent is doing, where, as it does it; clear it as soon as it is stale."""
        if ov is None or not _LAST_ACTION:
            return
        if _LAST_ACTION.get("id") != shown_action["id"] and _LAST_ACTION.get("id"):
            shown_action["id"] = _LAST_ACTION["id"]
            shown_action["at"] = time.time()
            from .overlay import Scene

            ov.badge("Taking over…", pulsing=True)
            text = _short(_LAST_ACTION.get("summary") or "", 110)
            why = _LAST_ACTION.get("element") or ""
            _say(text, interrupt=False)  # never cut the agent's sentence; the latest one waits its turn
            ov.show_scene(Scene(text=text, why=why[:60], target=_LAST_ACTION.get("pointer")))
            return
        shown_at = shown_action.get("at")
        if shown_at and ov.view.scene is not None:
            stale = _LAST_ACTION.get("stale_at", 0) > shown_at + 0.3  # a screenshot came after this action
            if stale or time.time() - shown_at > 2.0:
                ov.hide()  # the badge stays; only the marks go

    interrupted = {"done": False}

    def tick() -> None:
        nonlocal shown_step, prompted
        if not interrupted["done"] and _new_request_pending() and not it.state.terminal:
            interrupted["done"] = True
            print("\n>> new voice request: stopping the current task", flush=True)
            _hush()
            if ov:
                ov.hide()
                ov.badge("New request…", pulsing=True)
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
                    _say(g.instruction, _short(why, 90))
                    ov.show_scene(Scene(
                        text=g.instruction, target=g.pointer, target_box=g.box, why=_short(why, 90), step=g.index,
                        doodle="question" if "can't see" in g.instruction else None,
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
                    _hush()
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
