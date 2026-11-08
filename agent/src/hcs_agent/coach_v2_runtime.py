"""Small H-only coaching loop. Physical I/O is reused; the legacy harness is not.

Main thread owns AppKit and actions. Workers only read AX and ask Holo. A new
utterance invalidates in-flight results immediately. Local traces are never
human success labels; DesktopFeedback supplies those separately.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import queue
import re
import signal
import threading
import time
from urllib.parse import urlsplit

from .coach_v2 import CoachClient, CoachDecision, CoachProtocolError, allowed_page
from .coach_v2_journal import CoachRun


@dataclass
class Observation:
    data: dict
    targets: dict
    captured_at: float
    app: str = ""
    viewport: tuple | None = None


def observe() -> Observation:
    from . import a11y
    page = a11y.foreground_page()
    if not page or not page.is_front or not allowed_page(page.url):
        raise CoachProtocolError("Bring H Platform or its documentation to the front, then ask me again.")
    controls, targets, texts = [], {}, []
    roles = {"AXButton", "AXLink", "AXTextField", "AXSearchField", "AXComboBox", "AXPopUpButton",
             "AXMenuItem", "AXCheckBox", "AXRadioButton", "AXTab", "AXDisclosureTriangle"}
    seen = set()
    # Action controls first; headings and text can then be highlighted for answers.
    ordered = sorted(page.elements, key=lambda c: c.role not in roles)
    for c in ordered:
        name = c.name.strip()
        if not name:
            continue
        if c.role in {"AXStaticText", "AXHeading"}:
            texts.append(name[:700])
        if (c.role not in roles | {"AXStaticText", "AXHeading"} or len(name) > 700
                or c.frame[2] <= 0 or c.frame[3] <= 0 or min(c.frame[:2]) < 0):
            continue
        key = (c.role, name, c.box)
        if key in seen or len(controls) >= 160:
            continue
        seen.add(key)
        ident = len(controls) + 1
        controls.append({"id": ident, "role": c.role, "label": name[:180], "box": list(c.box), "enabled": c.enabled})
        targets[ident] = c
    texts.extend(page.readable_text)
    return Observation({"url": page.url, "title": page.title, "controls": controls,
                        "text": list(dict.fromkeys(texts))[:100]}, targets, time.monotonic(), page.app, page.viewport)


def matching_target(original, fresh: Observation):
    """IDs are local to a frame; never reuse them in a new observation."""
    matches = [c for c in fresh.targets.values() if c.role == original.role and c.name == original.name
               and c.enabled is not False]
    if len(matches) == 1:
        return matches[0]
    # Duplicate labels only remain usable when the exact prior box is present.
    exact = [c for c in matches if c.box == original.box]
    return exact[0] if len(exact) == 1 else None


def inside(point, box) -> bool:
    x, y = point
    bx, by, width, height = box
    return bx <= x <= bx + width and by <= y <= by + height


def foreground_url() -> str:
    """Fast identity check immediately before any desktop effect, no content walk."""
    from . import a11y
    bw = a11y._browser_window(front_only=True)
    if bw is None:
        return ""
    web = a11y._web_area(bw[0])
    return str(a11y._attr(web, "AXURL") or "") if web is not None else ""


def focused_search() -> bool:
    """Enter may submit a search, never an arbitrary form or agent job."""
    from . import a11y
    import ApplicationServices as AS
    from AppKit import NSWorkspace
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None:
        return False
    app = AS.AXUIElementCreateApplication(front.processIdentifier())
    field = a11y._attr(app, "AXFocusedUIElement")
    if field is None:
        return False
    role = str(a11y._attr(field, "AXRole") or "")
    label = " ".join(str(a11y._attr(field, k) or "") for k in ("AXTitle", "AXDescription", "AXPlaceholderValue"))
    return role == "AXSearchField" or (role in {"AXTextField", "AXComboBox"} and bool(re.search(r"\bsearch\b", label, re.I)))


def perform(decision: CoachDecision, target, expected_url: str, desktop, viewport=None) -> None:
    """One effect on the page just checked, never an unattended script."""
    if not allowed_page(expected_url) or foreground_url() != expected_url:
        raise CoachProtocolError("The page changed. Ask me again on the page you want help with.")
    if decision.action in {"click", "type"}:
        from .a11y import visible_at_point
        if target is None or not visible_at_point(target):
            raise CoachProtocolError("I can't see that control clearly. Bring the page forward and ask again.")
        if decision.action == "type":
            # This runner only types literal ASCII; no clipboard or shell access.
            if not decision.text or not decision.text.isascii():
                raise CoachProtocolError("Please enter that text yourself, then press Enter.")
        desktop.click(*target.center)
        if decision.action == "type":
            desktop.write(decision.text, interval=0)
    elif decision.action == "scroll":
        if viewport is None:
            raise CoachProtocolError("Please scroll this page a little, then ask me again.")
        x, y, width, height = viewport
        desktop.moveTo(x + width * .8, y + height * .6)
        desktop.scroll(-4 if decision.direction == "down" else 4)
    elif decision.action == "key":
        if decision.key == "enter" and not focused_search():
            raise CoachProtocolError("Please press Enter yourself here; I only submit searches automatically.")
        desktop.press(decision.key)
    elif decision.action == "open_docs":
        # URL has already passed CoachDecision's strict official-docs allowlist.
        desktop.hotkey("command", "t")
        desktop.write(decision.url, interval=0.001)
        desktop.press("enter")


class Runtime:
    MAX_STEPS = 8

    def __init__(self, runs_dir: Path, api_key: str, overlay, speaker, desktop, *, port=8792, ptt_key="alt_r"):
        from .control import Controller, ControlServer
        from .desktop_feedback import DesktopFeedback
        from .inputs import InputHub
        from .voice import PushToTalk
        class LocalController(Controller):
            def handle(self, method, path, body):
                if path.split("?", 1)[0].rstrip("/") == "/rate":
                    return 409, {"error": "Use the explicit session feedback form for V2."}
                return super().handle(method, path, body)

            def status(self):
                result = super().status()
                result["autonomy_labels"] = ["Show me", "Show me", "Do it, I watch"]
                result["autonomy_hints"] = ["I explain and point; you click.",
                                             "V2 keeps this position in guided mode.",
                                             "I navigate and explain, one step at a time."]
                return result
        self.runs_dir, self.api_key = runs_dir, api_key
        self.overlay, self.speaker, self.desktop = overlay, speaker, desktop
        self.events = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="h-coach-v2")
        self.lock = threading.RLock()
        self.generation = 0
        self.active_generation = 0
        self.closed = False
        self.current = None
        self.history = []
        self.step = 0
        self.pending = None
        self.due = None
        self.busy = False
        self.autonomy = 0
        self.response_mode = "both"
        self.voice_state, self.last_text = "ready", ""
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.feedback = DesktopFeedback()
        self.ptt = PushToTalk(key_name=ptt_key, on_state=self.voice_event,
                              vocabulary=["H Company", "H Platform", "Holo", "H Companion"])
        self.hub = InputHub.get()
        self.control = LocalController(runs_dir, status=self.status, set_autonomy=self.set_autonomy,
                                  stop=lambda: self.cancel("Stopped by you."), set_voice=self.set_voice,
                                  test_voice=self.test_voice, set_ptt_key=self.set_ptt,
                                  feedback=self.feedback, next_step=self.next_step)
        self.server = ControlServer(self.control, port=port)
        self.hub.subscribe(self.input_event)
        self.ptt.start()
        self.server.start()

    def cancel(self, message="Stopped by you."):
        with self.lock:
            self.generation += 1
            self.events.put(("cancel", self.generation, message))
        if self.speaker:
            self.speaker.stop()
        return True

    def voice_event(self, state):
        if state == "starting":
            self.cancel("Interrupted by a new request.")
        self.events.put(("voice", state))

    def input_event(self, event, payload):
        if event in {"click", "scroll", "key_down"}:
            self.events.put(("input", event, payload))

    def set_autonomy(self, level):
        # V2 has two explicit modes: the intermediate position remains guide.
        self.cancel("Mode changed.")
        self.autonomy = level

    def set_ptt(self, key):
        self.ptt.set_key(key)
        return True

    def set_voice(self, body):
        self.events.put(("voice_settings", body))
        return self.status()["speech"]

    def test_voice(self):
        if self.speaker:
            self.speaker.say("Hi, I'm here to help you explore H Platform.")
            return True
        return False

    def next_step(self, sid, index, done):
        if not self.current or self.current.session_id != sid or self.step != index or not self.pending:
            return False
        self.events.put(("next", sid, index, done))
        return True

    def status(self):
        run = self.current
        current = None
        if run:
            current = {"session_id": run.session_id, "procedure_id": "h-platform-coach-v2",
                       "goal": run.request.goal, "mode": run.request.mode, "state": run.state.value,
                       "terminal": run.state.terminal, "takeover": run.request.mode == "act", "autonomy": self.autonomy,
                       "step": {"index": self.step, "instruction": self.pending[0].speech,
                                "kind": self.pending[0].action, "total": None} if self.pending else None,
                       "cost_usd": None, "started_at": self.started_at,
                       "status": (run.report or {}).get("status"), "verified": False}
        speaker = self.speaker
        return {"engine": "coach-v2", "agent": {"command": "coach-v2", "pid": os.getpid(),
                "since": self.started_at, "simulated": False, "observe_only": False, "engine": "coach-v2"},
                "autonomy": self.autonomy, "voice": {"state": self.voice_state, "last_text": self.last_text,
                                                      "ptt_key": self.ptt.key_name},
                "speech": {"available": speaker is not None, "enabled": self.response_mode != "text",
                           "response_mode": self.response_mode, "provider": getattr(speaker, "provider", ""),
                           "voice": getattr(speaker, "voice", ""), "speed": getattr(speaker, "speed", 1.0),
                           "speaking": bool(speaker and speaker.speaking)}, "current": current,
                "context": {"mode": "h-only", "software": "h-company", "label": "H Platform · V2",
                            "sources": ["H official documentation + current accessibility tree"]},
                "accessibility": {}}

    def show(self, speech, target=None, *, speak=True):
        from .overlay import Scene
        self.overlay.badge(None)
        self.overlay.show_scene(Scene(text=speech, target=target.center if target else None,
                                      target_box=target.box if target else None, why=""), animate=False)
        if speak and speech and self.speaker and self.response_mode != "text":
            self.speaker.say(speech)

    def start_request(self, question):
        if self.feedback.consume_transcript(question):
            self.voice_state = "ready"
            return
        if re.fullmatch(r"(?:stop(?: task)?|cancel|arrête(?: la tâche)?)[.! ]*", question, re.I):
            self.cancel()
            return
        if self.current and not self.current.state.terminal:
            self.current.finish("stopped", "Interrupted by a new request.")
        self.generation += 1
        self.active_generation = self.generation
        self.current = CoachRun(self.runs_dir, question, "act" if self.autonomy == 2 else "guide")
        self.feedback.register(self.current)
        self.history, self.step, self.pending, self.due = [], 0, None, None
        self.last_text, self.voice_state = question, "ready"
        self.overlay.hide()
        self.request_decision()

    def request_decision(self):
        run, generation = self.current, self.active_generation
        if not run or run.state.terminal or generation != self.generation:
            return
        if self.step >= self.MAX_STEPS:
            self.finish("blocked", "Let's pause here. Tell me what you'd like to explore next.")
            return
        run.set_running()
        self.busy, self.pending, self.due = True, None, None
        self.overlay.badge("Checking the page…", pulsing=True)
        history = [{"speech": item["decision"]["speech"], "action": item["decision"]["action"],
                    "observation": {"target": item["decision"]["target_label"],
                                    "url": item["decision"]["url"], "event": item["event"],
                                    "verified": False}}
                   for item in self.history]
        self.pool.submit(self.decide_worker, run, generation, history)

    def decide_worker(self, run, generation, history):
        client = None
        started = time.monotonic()
        try:
            observed = observe()
            if generation != self.generation:
                return
            run.record("observation", observed.data)
            client = CoachClient(self.api_key)
            decision = client.decide(run.request.goal, observed.data, run.request.mode, history)
            run.record("model", {"decision": decision.model_dump(), "raw": client.last_raw,
                                 "usage": client.last_usage, "latency_ms": round((time.monotonic() - started) * 1000),
                                 "superseded": generation != self.generation})
            if generation != self.generation:
                return
            fresh = observe()
            if fresh.data["url"] != observed.data["url"]:
                self.events.put(("changed", generation))
                return
            target = None
            if decision.target is not None:
                target = matching_target(observed.targets[decision.target], fresh)
                if target is None:
                    self.events.put(("changed", generation))
                    return
            self.events.put(("decision", generation, decision, fresh, target))
        except Exception as exc:
            if client:
                run.record("model_error", {"type": type(exc).__name__, "raw": client.last_raw,
                                           "usage": client.last_usage})
            # Exception text can contain HTTP request data; do not echo/log it wholesale.
            message = str(exc) if isinstance(exc, CoachProtocolError) and str(exc).startswith("Bring H") else (
                "I couldn't read this page clearly. Keep H Platform visible and try that question again.")
            run.record("error", {"type": type(exc).__name__})
            self.events.put(("error", generation, message))
        finally:
            if client:
                client.close()

    def accept_decision(self, generation, decision, observation, target):
        if generation != self.generation or not self.current or self.current.state.terminal:
            return
        self.busy = False
        # A switch after worker observation must not paint or click another app.
        if foreground_url() != observation.data["url"]:
            self.finish("blocked", "Bring H Platform forward, then ask me again.")
            return
        self.step += 1
        self.show(decision.speech, target)
        if decision.action in {"done", "explain"}:
            self.finish("completed", decision.speech, show=False)
            return
        action = {"action": decision.action, "target_label": target.name if target else None,
                  "speech": decision.speech, "url": observation.data["url"], "text": decision.text}
        if self.history and all(self.history[-1]["decision"].get(k) == action.get(k)
                                for k in ("action", "target_label", "url", "text")):
            self.finish("blocked", "That control hasn't changed the page yet. Tell me what you see now.")
            return
        self.pending = (decision, target, observation)
        if self.current.request.mode == "act":
            self.current.set_running()
            self.due = (time.monotonic() + 0.25, "act", action)
        else:
            self.current.set_waiting()

    def finish(self, status, speech, *, show=True):
        self.busy, self.pending, self.due = False, None, None
        if self.current:
            self.current.finish(status, speech)
        self.overlay.badge(None)
        if show:
            self.show(speech)

    def user_input(self, event, payload):
        if not self.pending or self.due or self.current.request.mode != "guide":
            return
        decision, target, observation = self.pending
        matched = False
        if event == "click":
            if self.control.app_contains(*payload):
                return
            matched = bool(target and inside(payload, target.box))
        elif event == "scroll":
            matched = decision.action == "scroll"
        elif event == "key_down":
            name = getattr(payload, "name", "")
            matched = ((decision.action == "type" and name == "enter") or
                       (decision.action == "key" and name == decision.key))
        # A click into a text field is not evidence that the requested text was entered.
        if decision.action == "type" and event == "click":
            matched = False
        if matched:
            self.schedule_observation("user_input")

    def schedule_observation(self, source):
        if not self.pending:
            return
        decision, target, observation = self.pending
        entry = {"decision": {"action": decision.action, "target_label": target.name if target else None,
                              "speech": decision.speech, "url": observation.data["url"], "text": decision.text},
                 "event": source, "verified": False}
        self.history.append(entry)
        self.current.record("interaction", entry)
        self.pending = None
        self.overlay.hide()
        self.due = (time.monotonic() + 0.45, "observe", None)

    def tick(self):
        for _ in range(50):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind, *args = event
            if kind == "cancel":
                if self.active_generation >= args[0]:
                    continue
                if self.current and not self.current.state.terminal and self.active_generation < args[0]:
                    self.current.finish("stopped", args[1])
                self.pending, self.due, self.busy = None, None, False
                self.overlay.hide()
                self.overlay.badge(None)
            elif kind == "voice":
                self.voice_state = args[0]
                if args[0] in {"starting", "recording", "transcribing"}:
                    self.overlay.badge({"starting": "Listening…", "recording": "Listening…",
                                        "transcribing": "Understanding…"}[args[0]], pulsing=True)
            elif kind == "voice_settings":
                body = args[0]
                self.response_mode = body.get("response_mode", ("both" if body["enabled"] else "text")
                                              if "enabled" in body else self.response_mode)
                if "voice" in body or "speed" in body:
                    from .speech import make_speaker
                    if self.speaker:
                        self.speaker.close()
                    if "voice" in body:
                        os.environ["HCS_TTS_VOICE"] = body["voice"]
                        os.environ["HCS_TTS_PROVIDER"] = "elevenlabs"
                    if "speed" in body:
                        os.environ["HCS_TTS_SPEED"] = str(body["speed"])
                    self.speaker = make_speaker()
                self.overlay.set_text_enabled(self.response_mode != "voice")
                if self.speaker:
                    self.speaker.muted = self.response_mode == "text"
                    if self.speaker.muted:
                        self.speaker.stop()
            elif kind == "decision":
                self.accept_decision(*args)
            elif kind == "error" and args[0] == self.generation:
                self.finish("failed", args[1])
            elif kind == "changed" and args[0] == self.generation:
                self.step += 1
                self.request_decision()
            elif kind == "input":
                self.user_input(*args)
            elif kind == "next" and self.current and self.current.session_id == args[0] and self.step == args[1]:
                if args[2]:
                    self.schedule_observation("user_reported_done")
                else:
                    self.finish("blocked", "Let's try another way. Tell me what you see on the page.")
        transcript = self.ptt.wait_transcript(timeout=0)
        if transcript:
            self.start_request(transcript)
        if self.due and self.active_generation == self.generation and time.monotonic() >= self.due[0]:
            _, kind, payload = self.due
            if kind == "observe":
                self.request_decision()
            elif kind == "act" and self.pending:
                # Let this short phrase finish before the next one, never queue a narrated report.
                if self.speaker and self.speaker.speaking:
                    return
                decision, target, observed = self.pending
                try:
                    # Refresh a stale target before actions; old model output is not a license to click later.
                    if time.monotonic() - observed.captured_at > 12:
                        self.request_decision()
                    else:
                        perform(decision, target, observed.data["url"], self.desktop, observed.viewport)
                        self.schedule_observation("agent_action_executed")
                except CoachProtocolError as exc:
                    self.finish("blocked", str(exc))
                except Exception as exc:
                    self.current.record("action_error", {"type": type(exc).__name__})
                    self.finish("failed", "I couldn't complete that action. You can stop here and try another request.")
        self.control.check_presence()

    def close(self):
        self.cancel("App closed.")
        if self.current and not self.current.state.terminal:
            self.current.finish("stopped", "App closed.")
        self.closed = True
        self.ptt.stop()
        self.hub.unsubscribe(self.input_event)
        self.server.close()
        self.pool.shutdown(wait=False, cancel_futures=True)
        if self.speaker:
            self.speaker.close()
        self.overlay.hide()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--ptt-key", default="alt_r")
    args = parser.parse_args()
    key = os.environ.get("HAI_API_KEY") or os.environ.get("H_API_KEY")
    if not key:
        raise SystemExit("H API key is missing; use the V2 launcher.")
    # Initialize physical I/O on the main thread before the shared event tap.
    import pyautogui
    pyautogui.PAUSE = 0.03
    from .overlay import Overlay
    from .speech import make_speaker
    overlay, speaker = Overlay(), make_speaker()
    runtime = Runtime(args.runs_dir, key, overlay, speaker, pyautogui, port=args.port, ptt_key=args.ptt_key)
    signal.signal(signal.SIGINT, lambda *_: setattr(runtime, "closed", True))
    signal.signal(signal.SIGTERM, lambda *_: setattr(runtime, "closed", True))
    print(f"H Platform coach V2 ready on 127.0.0.1:{args.port}", flush=True)
    overlay.badge("Hold right Option to ask about H Platform")
    hint_until = time.monotonic() + 10
    def tick():
        nonlocal hint_until
        if hint_until and time.monotonic() > hint_until:
            overlay.badge(None)
            hint_until = 0
        runtime.tick()
    try:
        overlay.run_until(lambda: runtime.closed, tick=tick, interval=0.05, hide_at_end=True)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
