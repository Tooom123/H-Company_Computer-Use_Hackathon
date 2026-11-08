"""Command line for testing the agent directly on the Mac.

    hcs-agent procedures
    hcs-agent run --procedure odoo_crm_followup_activity --role "new sales rep" \
        --goal "Help me schedule the follow-up on Acme Demo" -p opportunity="Acme Demo" -p due_date=2026-11-14
    hcs-agent serve [--port 8765] [--mock]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

from .backend import make_backend
from .contract import AgentEvent, ApproveCommand, InterventionRequest, Mode, NextCommand, State, StopCommand
from .procedures import ProcedureRegistry
from .runner import Intervention
from .desktop_feedback import DesktopFeedback, RunJournal


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
_FEEDBACK = DesktopFeedback()
_RUN_FINISHED_HOOK = None  # optional launcher callback(directory: Path, report: dict); no automatic H calls
_GUIDE_REPLY_LOCK = threading.Lock()
_REOBSERVE_GUIDANCE_NOTE = "Observation only: target invalidated; reobserve requested."
_TEST_SENTENCE = "Hello, I am H Companion. I can now read the guidance aloud."


def _set_autonomy(level: int) -> None:
    """One place for every source (Magnet click, desktop app): default for next tasks + the running one."""
    level = max(0, min(2, int(level)))
    if os.environ.get("HCS_GUIDE_OBSERVE_ONLY") == "1":
        level = 0
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
                  "simulated": bool(getattr(backend, "simulated", False)),
                  "observe_only": os.environ.get("HCS_GUIDE_OBSERVE_ONLY") == "1"},
        "autonomy": _MAGNET["level"],
        "voice": {"state": _VOICE.get("state"), "last_text": _VOICE.get("last_text"),
                  "ptt_key": getattr(ptt, "key_name", None)},
        "speech": {"available": sp is not None, "enabled": bool(sp is not None and not sp.muted),
                   "provider": getattr(sp, "provider", None),
                   "voice": getattr(sp, "voice", None) or os.environ.get("HCS_TTS_VOICE") or "EXAVITQu4vr4xnSDxMaL",
                   "speed": getattr(sp, "speed", None) or float(os.environ.get("HCS_TTS_SPEED") or 1.0),
                   "speaking": bool(sp is not None and sp.speaking)},
        "current": cur,
        "accessibility": dict(getattr(backend, "last_catalogue_diagnostic", {}) or {}),
    }


def _control_stop(reason: str = "Stop pressed in the desktop app", *, intervention=None) -> bool:
    _hush()
    it = intervention if intervention is not None else _MAGNET["current"]
    if it is None or it.state.terminal:
        return False
    if it.state is State.stopping:
        return True  # already accepted; preserve the original stop timestamp
    print("\n>> stop requested by the user", flush=True)
    it.stop(StopCommand(reason=reason))
    return True



def _is_stop_utterance(text: str) -> bool:
    """Exact local commands only; a question mentioning Stop remains an ordinary request."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    normalized = " ".join(folded.strip(" \t\r\n.!?…").split())
    return normalized in {"stop", "stop task", "stop the task", "arrete", "arrete la tache"}


def _consume_talk_control(text: str, ov=None) -> bool:
    """An explicitly armed feedback dictation wins, including a comment consisting of 'stop'."""
    if _FEEDBACK.consume_transcript(text):
        _flash(ov, "Feedback transcribed. Review it and choose your labels in the app.", "question")
        return True
    if not _is_stop_utterance(text):
        return False
    accepted = _control_stop(reason="Exact spoken Stop command")
    message = "Stop requested. No new task started." if accepted else "Stop received. No new task started."
    print(f"  {message}", flush=True)
    if ov is not None:
        ov.hide()
        ov.badge(message)
    return True


def _submit_guidance(it, step_index: int, *, done: bool, note: str) -> bool:
    """Accept one observation/confirmation for this exact step; never label it successful."""
    with _GUIDE_REPLY_LOCK:
        if (it is None or it.state is not State.awaiting_user or not it.guidance
                or it.guidance[-1].index != step_index
                or getattr(it, "_user_event", None) is not None and it._user_event.is_set()):
            return False
        _hush()
        try:
            it.next(NextCommand(done=done, note=note))
        except RuntimeError:  # Stop or a worker state change won the race.
            return False
        return True


def _control_next(session_id: str, step_index: int, done: bool) -> bool:
    """Explicit desktop response, bound to the currently shown intervention and step."""
    it = _MAGNET.get("current")
    if (it is None or it.request.session_id != session_id or type(step_index) is not int
            or type(done) is not bool):
        return False
    report = "the step was attempted" if done else "being blocked on the step"
    return _submit_guidance(it, step_index, done=done,
                           note=f"User explicitly reported {report} in desktop app; result not verified.")


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


def _key_label(key: str | None) -> str:
    """cmd+h -> ⌘H, alt_r -> Right ⌥, f9 -> F9: what the badge and the app show."""
    if not key:
        return "⌘H"
    names = {"cmd": "⌘", "ctrl": "⌃", "alt": "⌥", "shift": "⇧", "alt_r": "Right ⌥", "cmd_r": "Right ⌘"}
    return "".join(names.get(p, p.upper()) for p in key.lower().split("+"))


def _control_ptt(key: str) -> bool:
    ptt = _VOICE.get("ptt")
    if ptt is None or not hasattr(ptt, "set_key"):
        return False
    ptt.set_key(key)
    print(f"\n  [app] push-to-talk key: {_key_label(key)}", flush=True)
    return True


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
                     set_voice=_control_voice, test_voice=_control_test_voice, set_ptt_key=_control_ptt, on_app_presence=_app_presence,
                     feedback=_FEEDBACK, next_step=_control_next)
    try:
        port = int(os.environ.get("HCS_CONTROL_PORT", DEFAULT_PORT))
        _CONTROL["server"] = ControlServer(ctl, port).start()
        print(f"  desktop app control point: http://127.0.0.1:{port}", flush=True)
    except OSError as exc:
        print(f"(desktop app control point unavailable: {exc})", flush=True)


def _new_request_pending() -> bool:
    ptt = _VOICE.get("ptt")
    return ptt is not None and not ptt.transcripts.empty()


def _ensure_magnet(ov=None):
    """Bottom-left autonomy slider; clicks change the running intervention and the default for the next ones."""
    if _MAGNET["widget"] is not None:
        if ov is not None:
            _MAGNET["widget"].on_compact_changed = ov.set_compact
            ov.set_compact(_MAGNET["widget"].compact)
        return _MAGNET["widget"]
    if sys.platform != "darwin":
        return None
    try:
        from .overlay import AUTONOMY_LABELS, MagnetWidget

        def on_change(level: int) -> None:
            print(f"\n  [magnet] {AUTONOMY_LABELS[level]}", flush=True)
            _set_autonomy(level)

        _MAGNET["widget"] = MagnetWidget(_MAGNET["level"], on_change,
                                         on_compact_changed=ov.set_compact if ov is not None else None,
                                         shortcut=os.environ.get("HCS_PTT_KEY", "ctrl+shift+h"))
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
    request.autonomy = 0 if os.environ.get("HCS_GUIDE_OBSERVE_ONLY") == "1" else _MAGNET["level"]
    request.mode = Mode.act if request.autonomy >= 2 else Mode.guide
    journal = RunJournal(runs_dir, request, _print_event, simulated=backend.simulated)
    it = Intervention(request, backend, ProcedureRegistry(), journal, runs_dir)
    _FEEDBACK.register(it)
    _MAGNET["current"] = it
    if ov is not None:
        _ensure_magnet(ov)
    print(f"session {request.session_id} (backend: {'MOCK' if backend.simulated else 'H desktop'}, "
          f"mode: {request.mode.value}, autonomy: {request.autonomy})")
    if ov is not None:
        _prefetch_voice(request)
    it.start()
    if it.state.terminal:
        _notify_run_finished(it)
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
            _notify_run_finished(it)
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
        _notify_run_finished(it)
        print(f"\nreport: {it.runs_dir / 'report.json'}")
        print(json.dumps(it.report.to_support_summary(), indent=2))
        if it.report.timings.stop_latency_s is not None:
            print(f"stop latency: {it.report.timings.stop_latency_s:.2f}s")
        if ov is not None and not _new_request_pending():
            _show_outcome(ov, it)
        return 0 if it.report.status.value == "resolved" else 3
    return 1


def _notify_run_finished(it) -> None:
    """Allow a private launcher to export completed H archives without delaying the desktop UI."""
    callback = _RUN_FINISHED_HOOK
    if callback is None or it.report is None:
        return
    report = it.report.model_dump(mode="json")
    def call():
        try:
            callback(it.runs_dir, report)
        except Exception:  # an exporter failure must never relaunch or corrupt the intervention
            print("(run archive export failed; local report and events retained)", flush=True)
    threading.Thread(target=call, name=f"run-export-{it.request.session_id}", daemon=True).start()


_COACHING_SOFTWARE = {
    "hcompany": ("h-company", "hcompany_general_guide", ["H Company", "Holo", "H Companion"]),
    "cognition": ("cognition", "cognition_general_guide", ["Cognition", "Devin", "H Companion"]),
    "devin": ("cognition", "cognition_general_guide", ["Cognition", "Devin", "H Companion"]),
}


def _coaching_request(text: str, software: str, context: str = "") -> InterventionRequest:
    """Keep free-form questions verbatim; never route a sponsor question into an Odoo task."""
    if not text.strip():
        raise ValueError("Please say a question")
    site, procedure, _ = _COACHING_SOFTWARE[software]
    return InterventionRequest(software=site, goal=text, procedure_id=procedure,
                               parameters={"question": text, "context": context}, mode=Mode.guide, autonomy=0)


def _hcompany_request(text: str, context: str = "") -> InterventionRequest:
    return _coaching_request(text, "hcompany", context)


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


def _answer_from_docs(ov, backend, question: str, seconds: float = 9.0) -> bool:
    """Information question: answer from the documentation map (hub pages), aloud and on screen, with the source.
    False when the documentation does not contain it (the caller then looks for it in the software)."""
    from . import sitemap

    if ov is not None:
        ov.badge("Reading the documentation…", pulsing=True)
    pages = sitemap.find_doc_pages(question, k=3)
    excerpts = [(p["title"], sitemap.fetch_doc(p, max_chars=2500)) for p in pages]
    excerpts = [(t, b) for t, b in excerpts if b]
    if not excerpts:
        print("  [docs] no matching documentation page")
        return False
    try:
        res = backend._grounding().answer(question, excerpts)
    except Exception as exc:  # noqa: BLE001
        print(f"  [docs] answer unavailable: {exc}")
        return False
    if not res.get("found") or not res.get("answer"):
        print(f"  [docs] not answered by: {', '.join(t for t, _ in excerpts)}")
        return False
    answer, source = res["answer"].strip(), (res.get("source") or excerpts[0][0]).strip()
    print(f"  [docs] {answer}  (source: {source})")
    _say(answer)
    if ov is None:
        return True
    from .overlay import Scene

    ov.badge(None)
    ov.show_scene(Scene(text=_short(answer, 110), why=f"Source: {source}"[:120]))
    t0 = time.time()
    try:
        ov.run_until(lambda: time.time() - t0 > seconds or _new_request_pending(), None, 0.1)
    except KeyboardInterrupt:
        ov.hide()
    ov.badge(f"{_key_label(getattr(_VOICE.get('ptt'), 'key_name', None))}: new request")
    return True


def _point_at(ov, backend, element: str, seconds: float = 6.0) -> bool:
    """'Where is X?': locate it on the current screen and circle it, no procedure involved. False when it is
    not on this screen (the caller may then navigate to it)."""
    from .overlay import Scene

    if ov is not None:
        ov.badge("Looking at the screen…", pulsing=True)
    loc = backend.locate(element, "Point at what the user asks about on the screen in front of them.") \
        if hasattr(backend, "locate") else None
    if loc is None or not loc.found:
        print(f"  not on this screen: {element}")
        return False
    text = f"Here: {element}"
    print(f"  -> pointing at {element} {loc.screen_xy}")
    _say(text)
    if ov is None:
        return True
    ov.badge(None)
    ov.show_scene(Scene(text=text, target=loc.screen_xy, target_box=loc.box))
    t0 = time.time()
    try:
        ov.run_until(lambda: time.time() - t0 > seconds or _new_request_pending(), None, 0.1)
    except KeyboardInterrupt:
        ov.hide()
    ov.badge(f"{_key_label(getattr(_VOICE.get('ptt'), 'key_name', None))}: new request")
    return True


def _inside(point, box, margin: float = 0) -> bool:
    x, y = point
    bx, by, bw, bh = box
    return bx - margin <= x <= bx + bw + margin and by - margin <= y <= by + bh + margin


def _follow_target(ov, shown: dict, tracker: "_TargetTracker") -> None:
    """Apply the tracker's latest measurement to what is drawn: move the frame, hide it, or bring it back."""
    from dataclasses import replace

    new_box = tracker.box
    if new_box is None:
        if not shown["hidden"]:
            ov.hide()  # control gone or covered: no frame on a wrong spot (the note comes back with it)
            shown["hidden"] = True
        return
    moved = shown["box"] is None or any(abs(a - b) > 6 for a, b in zip(new_box, shown["box"]))
    if shown["hidden"] or moved:
        cx, cy = new_box[0] + new_box[2] // 2, new_box[1] + new_box[3] // 2
        scene = replace(shown["scene"], target=(cx, cy), target_box=new_box)
        ov.show_scene(scene, animate=shown["hidden"])  # a comeback is drawn again; a move just slides
        shown.update(scene=scene, box=new_box, hidden=False)


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
    ov.badge(f"{os.environ.get('HCS_PTT_KEY', 'ctrl+shift+h')}: new request")


def _show_outcome(ov, it: Intervention, seconds: float = 5.0) -> None:
    """Show the final guidance with its actual verification status, then resume listening.

    A last=True answer does not enter awaiting_user, so the normal guide loop may
    never draw it. This terminal scene must replace, not preserve, an older mark.
    """
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
    final = (it.guidance[-1] if r.mode is Mode.guide and it.guidance and it.guidance[-1].last
             and r.status.value != "abandoned" else None)
    ov.badge(None)
    if final is not None:
        # The model's explanation is useful even when verification is inconclusive;
        # keep that distinction both visible and spoken. Never change the report.
        _say(text, final.instruction)
        ov.show_scene(Scene(text=final.instruction, target=final.pointer, target_box=final.box,
                            why=text, step=final.index, doodle=doodle))
    else:
        _say(text, why[:120])
        ov.show_scene(Scene(text=text, why=why[:120], doodle=doodle))
    t0 = time.time()
    hold = 2.5 if r.status.value == "abandoned" else seconds
    try:
        def finished():
            if _new_request_pending():
                return True
            elapsed = time.time() - t0
            speaker = _SPEECH["speaker"]
            speaking = final is not None and speaker is not None and speaker.speaking
            return elapsed > hold and (not speaking or elapsed > max(hold, 30))
        ov.run_until(finished, None, 0.1)
    except KeyboardInterrupt:
        ov.hide()


def cmd_talk(args: argparse.Namespace) -> int:
    """Push-to-talk: hold the key, speak, release; the request is routed and run after approval."""
    from .voice import IntentRouter, PushToTalk, intent_to_request

    registry = ProcedureRegistry()
    coaching_software = getattr(args, "software", None)
    coaching = coaching_software in _COACHING_SOFTWARE
    if coaching:
        registry.get(_COACHING_SOFTWARE[coaching_software][1])  # fail before opening devices if the fixture is missing
        _set_autonomy(0)
    # Proper nouns only: common words in the vocabulary made Gladia swap real words for them.
    vocab = _COACHING_SOFTWARE[coaching_software][2] if coaching else ["Acme Demo", "Acme Corp", "Odoo"]
    ov = None
    if not args.no_overlay and sys.platform == "darwin":
        from .overlay import Overlay

        ov = Overlay()
    voice_state = {"s": None}

    def on_state(s: str) -> None:
        if s.startswith("partial: "):
            if ov is not None and voice_state["s"] == "recording":
                ov.badge(_short(s[9:], 70) or "Listening…", pulsing=True)  # live words while speaking
            return
        voice_state["s"] = s
        _VOICE["state"] = s
        print(f"  [voice] {s}", flush=True)
        if s in {"starting", "recording"}:
            _hush()  # the user speaks: we stop talking (and the mic does not hear us)
        if ov is None:
            return
        if s == "starting":
            ov.badge("Opening microphone…", pulsing=True)
        elif s == "recording":
            ov.badge("Listening…", pulsing=True)
        elif s == "transcribing":
            ov.badge("Transcribing…")
        else:
            ov.badge(None)

    if ov is not None:
        _ensure_magnet(ov)
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
    try:
        from . import a11y

        if not args.mock and a11y.available():
            n = a11y.warm_up()
            from . import sitemap

            info = a11y.page()
            if info is not None and os.environ.get("HCS_GUIDE_OBSERVE_ONLY") != "1":
                sitemap.remember(info)
            if a11y.native_target():
                detail = (f"ready, {n} controls in the focused native window" if n > 1 else
                          "waiting for the selected native app in front; no browser or screenshot fallback")
                print(f"  native accessibility tree: {detail}")
            else:
                print(f"  browser accessibility tree: {'ready, ' + str(n) + ' elements on the current page' if n > 1 else 'no browser page yet (Holo will be used until one is open)'}")
    except Exception as exc:  # noqa: BLE001
        print(f"  (accessibility tree unavailable: {exc})")
    ptt = PushToTalk(key_name=args.key or os.environ.get("HCS_PTT_KEY", "cmd+h"), vocabulary=vocab, on_state=on_state)
    _VOICE["ptt"] = ptt
    router = None if coaching else IntentRouter(registry)
    ptt.start()
    print(f"Hold [{ptt.key_name}] and tell me what you need. Release to send. Responses are in English. Ctrl+C to quit.")
    if ov is not None:
        ov.badge(f"Hold {_key_label(ptt.key_name)} and say what you need")

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
            if not text.strip():
                # A short key press, silence or a transcription failure can yield an empty final.
                # Keep the microphone/control server alive; do not consume an armed feedback draft,
                # construct a task, or turn a retry into an implied label.
                message = "I didn't catch a question. Hold the talk key, speak, then release to try again."
                print(f"  {message}", flush=True)
                _flash(ov, message, "question")
                continue
            _VOICE["last_text"] = text
            print(f"\nYou said: \"{text}\"")
            if _consume_talk_control(text, ov):
                history.clear()
                continue
            if not coaching and last_request is not None and re.match(r"^\W*(reprends|reprise|continue|recommence|encore)\b", text.strip(), re.I):
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
            if coaching:
                context = ""
                if last_request is not None:
                    context = "Previous request (historical context, not a new authorization): " + last_request.goal
                    previous = _MAGNET.get("current")
                    if previous is not None and previous.guidance:
                        context += "\nLast guidance shown: " + previous.guidance[-1].instruction
                request = _coaching_request(text, coaching_software, context)
            else:
                history.append(f"User: {text}")
                try:
                    intent = router.route(text, history[:-1])
                except Exception as exc:  # noqa: BLE001
                    print(f"  could not understand the request ({exc}); try again.")
                    _flash(ov, "I did not get that, please rephrase", "question")
                    continue
                if intent.ask and not intent.procedure_id:
                    if _answer_from_docs(ov, backend, intent.ask):
                        history.clear()
                        continue
                    intent.task = f"Show where to see: {intent.ask}"  # not in the docs: look for it in the software
                if intent.point_at and not intent.procedure_id and not intent.task:
                    if not _point_at(ov, backend, intent.point_at):
                        intent.task = f"Show where to find {intent.point_at}"  # not on this screen: navigate to it
                    else:
                        history.clear()
                        continue
                if intent.task and not intent.procedure_id:
                    # No script for this: the general agent works from the screen, with the vendor docs as context.
                    from .voice import generic_request

                    from . import sitemap
                    software = intent.software or "hcompany"
                    doc = sitemap.context_for(software, intent.task) or None
                    try:
                        ans = None if doc else backend.knowledge.ask(f"{intent.task} — how is it done, step by step?",
                                                    software=intent.software or "hcompany", depth="fast")
                        doc = ans.as_text(2) if ans and ans.answer else doc
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
                        ov.badge(f"{os.environ.get('HCS_PTT_KEY', 'ctrl+shift+h')}: new request")
                    continue
                asked_before = any(h.startswith("Assistant:") for h in history)
                if not intent.procedure_id and not intent.missing and asked_before and (intent.goal or text):
                    # One question was already asked: do not keep interrogating, work from the screen instead.
                    intent.task = intent.goal or text
                    from .voice import generic_request

                    request = generic_request(intent, None)
                    last_request = request
                    history.clear()
                    print(f"  -> no script for this; general agent | {request.software} | {request.goal}")
                    _say("I will work it out from the screen.")
                    try:
                        _execute(request, backend, Path(args.runs_dir), auto_approve=not args.confirm,
                                 overlay=not args.no_overlay, ov=ov)
                    except Exception:  # noqa: BLE001
                        import traceback

                        traceback.print_exc()
                    if ov is not None and not _new_request_pending():
                        ov.badge(f"{os.environ.get('HCS_PTT_KEY', 'ctrl+shift+h')}: new request")
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
                if request.procedure_id == "hcompany_hub_find_documentation" and request.parameters.get("topic") \
                        and not request.parameters.get("page_title"):
                    from . import sitemap
                    pages = sitemap.find_doc_pages(request.parameters["topic"], k=1)
                    if pages:
                        request.parameters["page_title"] = pages[0]["title"]
            last_request = request
            if not coaching:
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
                ov.badge(f"{_key_label(ptt.key_name)}: new request")
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


class _TargetTracker:
    """While a step is shown, re-measure its control through the accessibility tree every ~0.5 s so the frame
    follows the control (scroll, layout change) and disappears when the control is gone or covered."""

    def __init__(self) -> None:
        self.description: str | None = None
        self.step: int | None = None
        self.box: tuple[int, int, int, int] | None = None  # latest measured box (None = not visible)
        self.measured_at = 0.0
        # (step, read-start monotonic time, foreground PID, box); never a reused prior read.
        self.measurement = None
        self._expected_app = None
        self._generation = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def follow(self, step: int, description: str | None, box, *, expected_app=None) -> None:
        self._generation += 1
        self.measurement = None
        self._expected_app = expected_app
        self.step, self.description, self.box, self.measured_at = step, description, box, time.time()
        if self._thread is None and description and sys.platform == "darwin":
            self._thread = threading.Thread(target=self._run, daemon=True, name="target-tracker")
            self._thread.start()

    def _run(self) -> None:
        try:
            from . import a11y

            if not a11y.available():
                return
        except Exception:  # noqa: BLE001
            return
        while not self._stop.wait(0.5):
            desc, step = self.description, self.step
            if not desc:
                continue
            generation, expected_app = self._generation, self._expected_app
            # Do not inspect a different app while recovering from focus loss.
            if expected_app is None or _InputWatcher._frontmost_app() != expected_app:
                self.box, self.measurement = None, None
                continue
            started_at = time.monotonic()
            try:
                best, ties, info = a11y.find(desc)
            except Exception:  # noqa: BLE001
                continue
            if self._generation != generation:
                continue  # the step changed meanwhile
            if _InputWatcher._frontmost_app() != expected_app:
                self.box, self.measurement = None, None
                continue
            if info is None or len(info.elements) <= 1:
                continue  # no page to compare with: keep what we have
            self.box = best.box if (best and not ties and info.is_front) else None
            self.measured_at = time.time()
            self.measurement = (step, started_at, expected_app, self.box)

    def stop(self) -> None:
        self._stop.set()


class _InputWatcher:
    """Observe interactions with the suggested target; never infer a completed task from a click.

    Positions are logical screen points, like GuidanceStep.box/pointer. Keyboard contents are not retained.
    The foreground application check is local and optional; it does not request Accessibility permission.
    """

    POINTER_TOLERANCE = 28.0
    BOX_TOLERANCE = 8.0

    def __init__(self, *, hub=None, keyboard=None, clock=None, focus_probe=None) -> None:
        self._clock = clock or time.monotonic
        self._focus_probe = focus_probe or self._frontmost_app
        self.armed_at = 0.0
        self.last_click = 0.0
        self.last_click_xy = None
        self.typed = 0
        self.last_submit = 0.0
        self._kind = "click"
        self._target = None
        self._target_click = False
        self._field_focused = False
        self._expected_app = None
        self.invalidated_at = None
        self._hub, self._kb = None, keyboard
        try:
            if self._kb is None:
                from pynput import keyboard as native_keyboard
                self._kb = native_keyboard
            if hub is None:
                from .inputs import InputHub
                hub = InputHub.get()
            self._hub = hub
            self._hub.subscribe(self._on_event)
        except Exception as exc:  # input unavailable: require explicit confirmation, never a screen-only shortcut
            print(f"(input watcher unavailable: {exc}; explicit confirmation required)")

    @staticmethod
    def _frontmost_app():
        if sys.platform != "darwin":
            return None
        try:
            import AppKit
            app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
            pid = int(app.processIdentifier()) if app is not None else None
            return pid if pid != os.getpid() else None
        except Exception:
            return None

    @staticmethod
    def _finite(values, count):
        import math
        return (isinstance(values, (tuple, list)) and len(values) == count
                and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in values))

    def _inside_target(self, point) -> bool:
        if self._target is None or not self._finite(point, 2):
            return False
        kind, values = self._target
        px, py = point
        if kind == "box":
            x, y, w, h = values
            margin = self.BOX_TOLERANCE
            return x - margin <= px <= x + w + margin and y - margin <= py <= y + h + margin
        x, y = values
        return (px - x) ** 2 + (py - y) ** 2 <= self.POINTER_TOLERANCE ** 2

    def _invalidate(self) -> None:
        # A coordinate from a previous page/focus is no longer evidence. Only a new step re-arms it.
        if self._target is not None and self.invalidated_at is None:
            self.invalidated_at = self._clock()
        self._target = None
        self._target_click = self._field_focused = False
        self.typed, self.last_submit = 0, 0.0

    def _same_app(self) -> bool:
        if self._expected_app is not None and self._focus_probe() != self._expected_app:
            self._invalidate()
            return False
        return True

    def _on_event(self, event: str, payload) -> None:
        now = self._clock()
        if event in ("scroll", "combo_down"):
            self._invalidate()
            return
        if not self._same_app():
            return
        if event == "click":
            if not self._finite(payload, 2):
                return
            magnet = _MAGNET.get("widget")
            if magnet is not None and magnet.contains(*payload):
                return
            server = _CONTROL.get("server")
            if server is not None and server.ctl.app_contains(*payload):
                return  # desktop controls are not interactions with the guided site
            self.last_click, self.last_click_xy = now, tuple(payload)
            if now <= self.armed_at + 0.3:
                return  # ignore the click that may have opened/revealed the step
            relevant = self._inside_target(payload)
            if not relevant:
                self._invalidate()
                return
            self._target_click = True
            self._field_focused = self._kind == "type"
            self.typed, self.last_submit = 0, 0.0
        elif event == "key_down" and self._kb is not None:
            navigation_keys = ("cmd", "cmd_l", "cmd_r", "ctrl", "ctrl_l", "ctrl_r",
                               "alt", "alt_l", "alt_r", "page_up", "page_down", "home", "end", "esc",
                               "up", "down", "left", "right")
            if any(payload == getattr(self._kb.Key, name, None) for name in navigation_keys):
                self._invalidate()
                return
            if not self._field_focused and (getattr(payload, "char", None)
                    or payload in (self._kb.Key.enter, self._kb.Key.tab, self._kb.Key.space, self._kb.Key.backspace)):
                self._invalidate()
                return
            if payload in (self._kb.Key.enter, self._kb.Key.tab):
                if self._field_focused and self.typed:
                    self.last_submit = now
            elif self._field_focused and (getattr(payload, "char", None)
                    or payload in (self._kb.Key.space, self._kb.Key.backspace)):
                self.typed += 1

    def arm(self, guidance) -> None:
        self.armed_at = self._clock()
        self.invalidated_at = None
        self._kind = getattr(guidance, "kind", "click")
        self.typed, self.last_submit = 0, 0.0
        self._target_click = self._field_focused = False
        self._expected_app = self._focus_probe()
        self._target = None
        box, pointer = getattr(guidance, "box", None), getattr(guidance, "pointer", None)
        if self._finite(box, 4) and box[2] > 0 and box[3] > 0:
            self._target = ("box", tuple(box))
        elif self._finite(pointer, 2):
            self._target = ("point", tuple(pointer))

    @property
    def expected_app(self):
        return self._expected_app

    def reobservation_ready(self, measurement, step: int) -> bool:
        """A fresh AX read may request a new plan, never restore or confirm the old target."""
        if self.invalidated_at is None or self._expected_app is None or measurement is None:
            return False
        measured_step, started_at, app, box = measurement
        return (measured_step == step and started_at > self.invalidated_at
                and 0 <= self._clock() - started_at <= 1.5
                and app == self._expected_app and self._focus_probe() == self._expected_app
                and self._finite(box, 4) and box[2] > 0 and box[3] > 0)

    def update_target_box(self, box) -> None:
        """Follow an AX box without resurrecting a target invalidated by scroll/navigation."""
        if self._target is None:
            return
        if self._target_click and (self._kind == "click" or self.last_submit > self.armed_at):
            return  # the control may disappear because a valid interaction just happened; H must check it
        if not self._finite(box, 4) or box[2] <= 0 or box[3] <= 0:
            self._invalidate()
            return
        target = ("box", tuple(box))
        if target != self._target:
            self._target = target
            self._target_click = self._field_focused = False
            self.typed, self.last_submit = 0, 0.0

    def acted(self, kind: str, settle_s: float = 0.5) -> bool:
        if self._target is None or kind not in ("click", "type"):
            return False  # no target, informational text or unspecified key: explicit confirmation only
        if not self._same_app():
            return False
        now = self._clock()
        if kind == "type":
            return bool(self._field_focused and self.typed and self.last_submit > self.armed_at
                        and now - self.last_submit >= settle_s)
        return self._target_click and now - self.last_click >= settle_s

    def observation_note(self, kind: str) -> str:
        if kind == "type":
            detail = "typing and Enter/Tab after a click inside the suggested field"
        else:
            detail = f"click inside the suggested target at screen point {self.last_click_xy}"
        return f"Observed interaction: {detail}. Result not verified; inspect the current screen."

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
    shown_key = None
    shown = {"scene": None, "box": None, "hidden": False, "text": None}
    tracker = _TargetTracker()
    prompted = False
    guidance_scene_shown = False
    reobservations = 0
    # Only the observation-only native pilot has an explicit no-action replan contract in the runner.
    request = getattr(it, "request", None)
    reobserve_allowed = (getattr(request, "software", None) == "cognition"
                         and getattr(request, "autonomy", None) == 0
                         and getattr(request, "mode", None) is Mode.guide
                         and os.environ.get("HCS_AX_NATIVE_BUNDLE_ID") == "com.exafunction.windsurf")
    inputs = _InputWatcher()

    def advance(done: bool = True, note: str = "") -> bool:
        nonlocal guidance_scene_shown
        accepted = _submit_guidance(it, shown_step, done=done, note=note)
        if accepted and ov:
            ov.hide()
            guidance_scene_shown = False
        return accepted

    def status_badge() -> None:
        if ov is None:
            return
        if _VOICE.get("state") in ("recording", "transcribing"):
            return  # the voice badge is already shown; do not overwrite it mid-sentence
        if it.state is State.awaiting_user:
            ov.badge("Target changed. Confirm in H Companion or stop." if inputs.invalidated_at is not None else None)
        elif time.time() - _LAST_LOOKUP_AT < 4:
            ov.badge("Searching the web…", pulsing=True)
        elif it.state is State.running:
            ov.badge("Holo is preparing guidance…", pulsing=True)
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
        nonlocal shown_step, shown_key, prompted, guidance_scene_shown, reobservations
        if not interrupted["done"] and _new_request_pending() and not it.state.terminal:
            interrupted["done"] = True
            print("\n>> voice received: stopping the current task before routing", flush=True)
            if ov:
                ov.hide()
                ov.badge("Voice received…", pulsing=True)
            _control_stop(reason="Voice input received; stopped before routing", intervention=it)
            return
        if interrupted["done"]:
            return
        if guidance_scene_shown and it.state is not State.awaiting_user:
            ov.hide()  # desktop Next runs on another thread; clear its old marker on the UI thread
            guidance_scene_shown = False
        status_badge()
        if getattr(it, "takeover", False) and it.state in (State.running, State.verifying):
            narrate()
        if it.state is State.awaiting_user and it.guidance:
            g = it.guidance[-1]
            if getattr(it, "_user_event", None) is not None and it._user_event.is_set():
                if ov and guidance_scene_shown:
                    ov.hide()
                    guidance_scene_shown = False
                return  # desktop confirmation already consumed this step; do not replay it
            key = (g.index, g.shown_at.isoformat() if g.shown_at else None)
            if key != shown_key:
                same_step = shown_step == g.index and shown["text"] == g.instruction
                shown_step, shown_key = g.index, key
                prompted = False
                inputs.arm(g)
                if ov:
                    from .overlay import Mark, Scene

                    verbose = os.environ.get("HCS_GUIDE_VERBOSE", "").lower() in {"1", "true", "yes"}
                    why = g.why if (verbose or g.kind in ("info", "wait")) else ""
                    if not same_step:
                        _say(g.instruction, _short(why, 90))
                    shown["text"] = g.instruction
                    scene = Scene(
                        text=g.instruction, target=g.pointer, target_box=g.box, why=_short(why, 90), step=g.index,
                        doodle="question" if "can't see" in g.instruction else None,
                        marks=[Mark(a.shape, a.pointer, _short(a.text, 28), tuple(a.size) if a.size else (0, 0),
                                    None, a.box)
                               for a in g.annotations if a.pointer])
                    ov.show_scene(scene)
                    shown.update(scene=scene, box=g.box, hidden=False)
                    guidance_scene_shown = True
                tracker.follow(g.index, g.where if (g.box_exact and g.kind in ("click", "type")) else None,
                               g.box, expected_app=inputs.expected_app)
                speaker = _SPEECH.get("speaker")
                if speaker is not None:
                    speaker.prefetch(list(getattr(g, "prepared_speech", [])), replace=True)
            if ov and shown["scene"] is not None and tracker.step == g.index and tracker.description:
                _follow_target(ov, shown, tracker)
                inputs.update_target_box(tracker.box)
            if auto:
                time.sleep(0.3)
                advance(note="Observed interaction: automated test advance; no human action observed. Result not verified.")
                return
            if not prompted:
                print(f"\n  step {g.index}: {g.instruction}  [{g.kind}] (target interaction or Enter to continue; q = stop) ",
                      end="", flush=True)
                prompted = True
            g = it.guidance[-1]
            if inputs.acted(g.kind):
                print("\n  target interaction observed; asking H to check the result…", flush=True)
                advance(note=inputs.observation_note(g.kind))
                return
            if reobserve_allowed and reobservations < 1 and inputs.reobservation_ready(tracker.measurement, g.index):
                if advance(done=False, note=_REOBSERVE_GUIDANCE_NOTE + " No user action was confirmed."):
                    reobservations += 1
                    print("\n  target invalidated; fresh AX observation requests one new plan, not a completed action",
                          flush=True)
                return
            try:
                ready, _, _ = select.select([sys.stdin], [], [], 0)
            except (OSError, ValueError, io.UnsupportedOperation):
                ready = []
            if ready:
                line = sys.stdin.readline()
                if not line:
                    return  # EOF (normal in the desktop launcher) is not a human pressing Enter
                ans = line.strip()
                if ans.lower() == "q":
                    _hush()
                    if ov:
                        ov.hide()
                    it.stop(StopCommand(reason="user quit"))
                else:
                    advance(done=ans == "", note=ans or "User explicitly requested to continue; verify the outcome on screen.")
        # Final guidance is drawn by _show_outcome after the report is available.
        # It must not reuse the previous step's annotation here.

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
        tracker.stop()


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
    talk.add_argument("--software", choices=list(_COACHING_SOFTWARE), help="Open-ended H Company or Cognition coaching; responses in English")
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
