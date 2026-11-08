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

from .coach_v2 import CoachClient, CoachDecision, CoachProtocolError, allowed_page, sensitive_key_creation
from .coach_v2_journal import CoachRun


@dataclass
class Observation:
    data: dict
    targets: dict
    captured_at: float
    app: str = ""
    viewport: tuple | None = None


def observe() -> Observation:
    from .coach_v2_screen import read_page
    page = read_page()
    if not page or not page.is_front or not allowed_page(page.url):
        raise CoachProtocolError("Bring H Platform or its documentation to the front, then ask me again.")
    controls, targets, texts = [], {}, []
    roles = {"AXButton", "AXLink", "AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXPopUpButton",
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


TOUR_SECTIONS = {"Agents", "Sessions", "Skills"}


def sidebar_target(original, original_viewport, fresh: Observation):
    """Resolve a read-only section within its sidebar rail, never a body namesake."""
    if (original.name not in TOUR_SECTIONS or original.role not in {"AXButton", "AXLink", "AXTab"}
            or not original_viewport or not fresh.viewport):
        return None
    ox, _, ow, _ = original_viewport
    fx, _, fw, _ = fresh.viewport
    if min(ow, fw) <= 0:
        return None
    rail = (original.box[0] - ox) / ow
    if not 0 <= rail <= .3 or original.box[2] > ow * .33:
        return None
    matches = [c for c in fresh.targets.values()
               if c.name == original.name and c.role == original.role and c.enabled is not False
               and abs((c.box[0] - fx) / fw - rail) <= .035
               and 0 < c.box[2] <= fw * .33 and c.box[3] > 0]
    return matches[0] if len(matches) == 1 else None


def tour_destination_ready(target, fresh: Observation) -> bool:
    if getattr(target, "selected", None) is True:
        return True
    # A label in the sidebar isn't evidence that the corresponding page loaded.
    return any(c.role == "AXHeading" and c.name.strip() == target.name
               and c.box[0] > target.box[0] + target.box[2]
               for c in fresh.targets.values())


def same_platform_origin(first, second) -> bool:
    a, b = urlsplit(first), urlsplit(second)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc) and b.hostname == "platform.hcompany.ai" and allowed_page(second)


def make_tour_cache(runs_dir):
    from .coach_v2 import SYSTEM_PROMPT_PATH, PRODUCT_KNOWLEDGE_PATH
    from .coach_v2_tour_cache import TourCache
    fingerprint = "holo4-35b-a3b\n" + SYSTEM_PROMPT_PATH.read_text() + PRODUCT_KNOWLEDGE_PATH.read_text()
    return TourCache(Path(runs_dir).parent / "tour-cache.json", fingerprint)


def inside(point, box) -> bool:
    x, y = point
    bx, by, width, height = box
    return bx <= x <= bx + width and by <= y <= by + height


def failure_message(exc: Exception, stage: str) -> str:
    """Explain the actual failure stage; a rejected reply is not a screen failure."""
    if isinstance(exc, CoachProtocolError):
        kind = getattr(exc, "kind", "response")
        if kind == "provider":
            return "I couldn't reach Holo just now. Please try again in a moment."
        if kind == "configuration":
            return "My connection isn't configured correctly. Please check H Companion's setup."
        if kind == "policy":
            if getattr(exc, "reason", None) == "guide_open_docs":
                return 'Switch to "Do it, I watch" if you want me to open the documentation for you.'
            return "I can explain this area, but I can't perform that action in this version."
        if kind == "observation" and stage == "model":
            return "I couldn't prepare the page information correctly. Please try again."
        if stage == "model":
            return "I could read the page, but couldn't use the reply I received. Please try your question again."
        if stage in {"observation", "refresh"}:
            return "Bring H Platform or its documentation to the front, then ask me again."
    return "I ran into a problem while preparing your guidance. Please try again."


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


def set_literal_text(target, text: str, desktop) -> None:
    """Set the exact field, with Unicode/newlines and no pasted keyboard shortcuts.

    AX's acknowledged set-value avoids the system clipboard when supported.
    The fallback preserves all pasteboard formats and restores them only if no
    one has since copied something else. Never read field values into a trace.
    """
    from . import a11y
    import ApplicationServices as AS
    from AppKit import NSWorkspace, NSPasteboard, NSPasteboardItem, NSPasteboardTypeString
    from Foundation import NSData, NSDate, NSRunLoop
    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    app = AS.AXUIElementCreateApplication(front.processIdentifier()) if front else None
    focused = a11y._attr(app, "AXFocusedUIElement") if app is not None else None
    ref = getattr(target, "ref", None)
    if (ref is None or focused is None or not AS.CFEqual(ref, focused)
            or target.role not in {"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"}):
        raise CoachProtocolError("Please click directly inside the text field and ask again.")
    result = AS.AXUIElementSetAttributeValue(ref, "AXValue", text)
    if result == 0:
        return
    board = NSPasteboard.generalPasteboard()
    previous = []
    for item in board.pasteboardItems() or []:
        contents = {}
        for kind in item.types() or []:
            data = item.dataForType_(kind)
            if data is not None:
                contents[str(kind)] = bytes(data)
        previous.append(contents)
    board.clearContents()
    board.setString_forType_(text, NSPasteboardTypeString)
    owned_count = board.changeCount()
    try:
        desktop.hotkey("command", "a")
        desktop.hotkey("command", "v")
        # Pump AppKit until the application acknowledges the value, bounded to
        # avoid a long blocked main loop. This is local evidence, never logged.
        deadline = time.monotonic() + .65
        while time.monotonic() < deadline:
            if str(a11y._attr(ref, "AXValue") or "") == text:
                return
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.025))
        raise CoachProtocolError("The text was pasted, but I couldn't confirm the field. Please check it before continuing.")
    finally:
        if board.changeCount() == owned_count:
            board.clearContents()
            restored = []
            for contents in previous:
                item = NSPasteboardItem.alloc().init()
                for kind, data in contents.items():
                    item.setData_forType_(NSData.dataWithBytes_length_(data, len(data)), kind)
                restored.append(item)
            if restored:
                board.writeObjects_(restored)


def perform(decision: CoachDecision, target, expected_url: str, desktop, viewport=None) -> None:
    """One effect on the page just checked, never an unattended script."""
    if not allowed_page(expected_url) or foreground_url() != expected_url:
        raise CoachProtocolError("The page changed. Ask me again on the page you want help with.")
    if decision.action in {"click", "type"}:
        from .a11y import visible_at_point
        if target is None or not visible_at_point(target):
            raise CoachProtocolError("I can't see that control clearly. Bring the page forward and ask again.")
        desktop.click(*target.center)
        if decision.action == "type":
            set_literal_text(target, decision.text, desktop)
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
    MAX_STEPS = 12

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
        self.tour_cache = make_tour_cache(runs_dir)
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
        self.tour = None
        self.requires_confirmation = False
        self.confirmation_pending = False
        self.approved_step = None
        self.due = None
        self.dismiss_notice = None
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
        if self.confirmation_pending:
            return False
        if self.requires_confirmation:
            self.confirmation_pending = True
        self.events.put(("next", sid, index, done))
        return True

    def status(self):
        run = self.current
        current = None
        if run:
            current = {"session_id": run.session_id, "procedure_id": "h-platform-coach-v2",
                       "goal": run.request.goal, "mode": run.request.mode, "state": run.state.value,
                       "terminal": run.state.terminal, "takeover": run.request.mode == "act", "autonomy": self.autonomy,
                       "step": {"index": self.step, "instruction": (
                           "Create this API key? Confirm in H Companion to continue." if self.requires_confirmation
                           else self.pending[0].speech),
                                "kind": "confirm" if self.requires_confirmation else self.pending[0].action,
                                "total": None} if self.pending else None,
                       "cost_usd": None, "started_at": self.started_at,
                       "status": (run.report or {}).get("status"), "verified": False}
        speaker = self.speaker
        return {"engine": "coach-v2", "agent": {"command": "coach-v2", "pid": os.getpid(),
                "since": self.started_at, "simulated": False, "observe_only": False, "engine": "coach-v2"},
                "autonomy": self.autonomy, "voice": {"state": self.voice_state, "last_text": self.last_text,
                                                      "ptt_key": self.ptt.key_name,
                                                      "provider": getattr(self.ptt, "stt_provider", "gladia")},
                "speech": {"available": speaker is not None, "enabled": self.response_mode != "text",
                           "response_mode": self.response_mode, "provider": getattr(speaker, "provider", ""),
                           "voice": getattr(speaker, "voice", ""), "speed": getattr(speaker, "speed", 1.0),
                           "speaking": bool(speaker and speaker.speaking)}, "current": current,
                "context": {"mode": "h-only", "software": "h-company", "label": "H Platform · V2",
                            "sources": ["H official documentation + current accessibility tree"]},
                "accessibility": {}}

    def show(self, speech, target=None, *, speak=True):
        from .overlay import Scene
        self.dismiss_notice = None
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
        self.tour, self.requires_confirmation, self.confirmation_pending = None, False, False
        self.approved_step = None
        self.last_text, self.voice_state = question, "ready"
        self.dismiss_notice = None
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
        stage = "observation"
        try:
            observed = observe()
            if generation != self.generation:
                return
            from .coach_v2_screen import attach_quota
            observed.data = attach_quota(observed.data, run.request.goal)
            run.record("observation", observed.data)
            observation_ms = round((time.monotonic() - started) * 1000)
            stage = "model"
            cache = getattr(self, "tour_cache", None)
            decision = cache.get(run.request.goal, {**observed.data, "viewport": observed.viewport},
                                 run.request.mode) if cache and not history else None
            if decision:
                run.record("tour_cache_hit", {"decision": decision.model_dump(), "observation_ms": observation_ms,
                                              "model_call": False, "source": "completed_tour_cache"})
            else:
                client = CoachClient(self.api_key)
                model_started = time.monotonic()
                decision = client.decide(run.request.goal, observed.data, run.request.mode, history)
                run.record("model", {"decision": decision.model_dump(), "raw": client.last_raw,
                                     "usage": client.last_usage, "latency_ms": round((time.monotonic() - started) * 1000),
                                     "observation_ms": observation_ms,
                                     "model_ms": round((time.monotonic() - model_started) * 1000),
                                     "superseded": generation != self.generation})
            if generation != self.generation:
                return
            stage = "refresh"
            refresh_started = time.monotonic()
            fresh = observe()
            run.record("refresh", {"latency_ms": round((time.monotonic() - refresh_started) * 1000)})
            if fresh.data["url"] != observed.data["url"]:
                self.events.put(("changed", generation))
                return
            target = None
            if decision.target is not None:
                target = matching_target(observed.targets[decision.target], fresh)
                if target is None:
                    self.events.put(("changed", generation))
                    return
            if decision.action == "tour":
                tour_targets = {}
                for point in decision.points:
                    rebound = matching_target(observed.targets[point.target], fresh)
                    if rebound is None:
                        self.events.put(("changed", generation))
                        return
                    tour_targets[point.target] = rebound
                self.events.put(("decision", generation, decision, fresh, target, tour_targets))
            else:
                self.events.put(("decision", generation, decision, fresh, target))
        except Exception as exc:
            diagnostic = {"type": type(exc).__name__, "stage": stage,
                          "category": getattr(exc, "kind", "internal"),
                          "reason": getattr(exc, "reason", None),
                          "validation_errors": getattr(exc, "validation_errors", None)}
            if client and stage == "model":
                run.record("model_error", {"type": type(exc).__name__, "raw": client.last_raw,
                                           "usage": client.last_usage, **diagnostic})
            # Preserve safe diagnostics, never echo HTTP bodies or arbitrary exception text.
            run.record("error", diagnostic)
            self.events.put(("error", generation, failure_message(exc, stage)))
        finally:
            if client:
                client.close()

    def accept_decision(self, generation, decision, observation, target, tour_targets=None):
        if generation != self.generation or not self.current or self.current.state.terminal:
            return
        self.busy = False
        # A switch after worker observation must not paint or click another app.
        if foreground_url() != observation.data["url"]:
            self.finish("blocked", "Bring H Platform forward, then ask me again.")
            return
        self.step += 1
        # The decision's IDs belong to its original frame. Use the freshly
        # rebound label for the final-action guard, not a reused numeric ID.
        guard_observation = dict(observation.data)
        guard_decision = decision
        if target is not None:
            # Keep current form/list evidence while avoiding an old frame's ID
            # accidentally referring to another current control.
            controls = list(observation.data.get("controls", []))
            guard_id = max((c["id"] for c in controls), default=0) + 1
            controls.append({"id": guard_id, "label": target.name, "role": target.role})
            guard_observation["controls"] = controls
            guard_decision = decision.model_copy(update={"target": guard_id})
        needs_confirmation = (self.current.request.mode == "act"
                              and sensitive_key_creation(guard_decision, guard_observation))
        if not needs_confirmation:
            self.show(decision.speech, target)
        if decision.action == "tour":
            targets = tour_targets or observation.targets
            cache_observation = {**observation.data, "viewport": observation.viewport,
                                 "controls": [{"id": p.target, "label": targets[p.target].name,
                                               "role": targets[p.target].role, "box": targets[p.target].box,
                                               "enabled": targets[p.target].enabled} for p in decision.points]}
            self.tour = {"points": [(point, (tour_targets or observation.targets)[point.target])
                                    for point in decision.points],
                         "url": observation.data["url"], "index": 0, "last_text": decision.speech,
                         "visit": self.current.request.mode == "act", "viewport": observation.viewport,
                         "phase": "presenting", "cache_entry": (decision, cache_observation)}
            self.current.set_running()
            if self.speaker and self.response_mode != "text":
                self.speaker.prefetch([p.speech for p in decision.points])
            self.schedule_tour_advance(decision.speech)
            return
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
        self.requires_confirmation = needs_confirmation
        self.confirmation_pending = False
        if self.requires_confirmation:
            self.current.set_waiting()
            self.show("Create this API key? Confirm in H Companion to continue.", target)
        elif self.current.request.mode == "act":
            self.current.set_running()
            self.due = (time.monotonic() + 0.25, "act", action)
        else:
            self.current.set_waiting()

    def finish(self, status, speech, *, show=True):
        self.busy, self.pending, self.due = False, None, None
        self.tour, self.requires_confirmation, self.confirmation_pending = None, False, False
        self.approved_step = None
        if self.current:
            self.current.finish(status, speech)
        self.overlay.badge(None)
        if show:
            self.show(speech)
        # Keep a short reading interval and let a normal spoken reply finish.
        # The upper bound also clears a notice if audio gets stuck as speaking.
        now = time.monotonic()
        self.dismiss_notice = (self.generation, now + 8, now + 25)

    def schedule_tour_advance(self, speech):
        # With voice, playback completion gates every point; text-only gets a
        # bounded reading interval. No new model call for the next explanation.
        delay = .25 if self.speaker and self.response_mode != "text" else max(2.0, len(speech.split()) / 3.0)
        self.due = (time.monotonic() + delay, "tour", None)

    def tour_worker(self, run, generation, point, original, url, *, visit=False, viewport=None, index=0):
        try:
            fresh = observe()
            target = sidebar_target(original, viewport, fresh) if visit else matching_target(original, fresh)
            if fresh.data["url"] != url or target is None:
                raise CoachProtocolError("The page changed during the tour.")
            if generation == self.generation:
                if visit:
                    self.events.put(("tour_ready", generation, index, point, fresh, target))
                else:
                    self.events.put(("tour_point", generation, point, target, url))
        except Exception as exc:
            run.record("tour_error", {"type": type(exc).__name__})
            self.events.put(("error", generation,
                             "The page changed during the tour. Ask me again on the page you'd like to explore."))

    def arrival_worker(self, run, generation, payload):
        try:
            fresh = observe()
            target = sidebar_target(payload["target"], payload["viewport"], fresh)
            if not same_platform_origin(payload["url"], fresh.data["url"]):
                raise CoachProtocolError("The tour left H Platform.")
            ready = target is not None and tour_destination_ready(target, fresh)
            if generation == self.generation:
                self.events.put(("tour_arrival", generation, payload, fresh, target, ready))
        except Exception as exc:
            run.record("tour_error", {"type": type(exc).__name__})
            self.events.put(("error", generation, "I couldn't confirm that page opened. Let's pause the tour here."))

    def present_tour_point(self, point, target, url, *, visited=False):
        self.busy = False
        self.tour.update(index=self.tour["index"] + 1, last_text=point.speech,
                         url=url, phase="presenting")
        self.current.record("tour_point", {"index": self.tour["index"], "speech": point.speech,
                                          "target_label": target.name, "url": url,
                                          "navigation_verified": visited, "verified": False})
        self.show(point.speech, target)
        self.schedule_tour_advance(point.speech)

    def approved_action_worker(self, run, generation, step, decision, original, url):
        try:
            fresh = observe()
            target = matching_target(original, fresh) if original else None
            if fresh.data["url"] != url or (original is not None and target is None):
                raise CoachProtocolError("The key form changed before confirmation.")
            if generation == self.generation:
                self.events.put(("approved_action", generation, step, decision, fresh, target))
        except Exception as exc:
            run.record("confirmation_error", {"type": type(exc).__name__})
            self.events.put(("error", generation,
                             "The key form changed. Please review it before trying again."))

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
        self.requires_confirmation, self.confirmation_pending = False, False
        self.approved_step = None
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
                self.tour, self.requires_confirmation, self.confirmation_pending = None, False, False
                self.approved_step = None
                self.dismiss_notice = None
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
            elif kind == "tour_point" and args[0] == self.generation and self.tour:
                _, point, target, url = args
                if foreground_url() != url:
                    self.finish("blocked", "Bring H Platform forward, then ask me for the tour again.")
                    continue
                self.present_tour_point(point, target, url)
            elif (kind == "tour_ready" and args[0] == self.generation and self.tour
                  and self.tour["visit"] and self.tour["phase"] == "preparing" and args[1] == self.tour["index"]):
                _, index, point, fresh, target = args
                try:
                    if (foreground_url() != fresh.data["url"] or fresh.data["url"] != self.tour["url"]
                            or time.monotonic() - fresh.captured_at > 3):
                        raise CoachProtocolError("The tour page changed.")
                    if tour_destination_ready(target, fresh):
                        self.present_tour_point(point, target, fresh.data["url"], visited=True)
                        continue
                    perform(CoachDecision(action="click", target=point.target, speech=point.speech), target,
                            fresh.data["url"], self.desktop, fresh.viewport)
                    self.current.record("tour_navigation", {"index": index + 1, "target_label": target.name,
                                                            "from_url": fresh.data["url"]})
                    self.tour["phase"] = "navigating"
                    payload = {"point": point, "target": target, "viewport": fresh.viewport,
                               "index": index, "url": fresh.data["url"], "deadline": time.monotonic() + 8}
                    self.due = (time.monotonic() + .15, "tour_arrival", payload)
                except Exception:
                    self.finish("blocked", "I couldn't open that section safely. Let's pause the tour here.")
            elif (kind == "tour_arrival" and args[0] == self.generation and self.tour
                  and self.tour["phase"] == "navigating" and args[1]["index"] == self.tour["index"]):
                _, payload, fresh, target, ready = args
                if foreground_url() != fresh.data["url"] or time.monotonic() - fresh.captured_at > 3:
                    self.finish("blocked", "Bring H Platform forward, then ask me for the tour again.")
                elif ready:
                    self.present_tour_point(payload["point"], target, fresh.data["url"], visited=True)
                elif time.monotonic() >= payload["deadline"]:
                    self.finish("blocked", "That section hasn't appeared yet. Let's pause the tour here.")
                else:
                    self.due = (time.monotonic() + .25, "tour_arrival", payload)
            elif (kind == "approved_action" and args[0] == self.generation and self.pending
                  and self.step == args[1] and self.confirmation_pending):
                _, _, decision, fresh, target = args
                if self.approved_step != self.step:
                    self.current.record("human_confirmation", {"step": self.step, "action": "create_api_key",
                                                                "source": "desktop_confirm_button"})
                self.approved_step = self.step
                self.pending = (decision, target, fresh)
                self.requires_confirmation = self.confirmation_pending = False
                self.current.set_running()
                self.due = (time.monotonic() + .25, "act", None)
            elif kind == "error" and args[0] == self.generation:
                self.finish("failed", args[1])
            elif kind == "changed" and args[0] == self.generation:
                self.step += 1
                self.request_decision()
            elif kind == "input":
                self.user_input(*args)
            elif kind == "next" and self.current and self.current.session_id == args[0] and self.step == args[1]:
                if args[2] and self.requires_confirmation and self.pending:
                    decision, target, observed = self.pending
                    self.pool.submit(self.approved_action_worker, self.current, self.active_generation,
                                     self.step, decision, target, observed.data["url"])
                elif args[2]:
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
            elif kind == "tour" and self.tour:
                if self.speaker and self.response_mode != "text" and self.speaker.speaking:
                    return
                if self.tour["index"] >= len(self.tour["points"]):
                    cache = getattr(self, "tour_cache", None)
                    if cache:
                        decision, cache_observation = self.tour["cache_entry"]
                        saved = cache.put(self.current.request.goal, decision, cache_observation,
                                          self.current.request.mode)
                        self.current.record("tour_cache_saved", {"saved": saved})
                    self.finish("completed", self.tour["last_text"], show=False)
                else:
                    point, original = self.tour["points"][self.tour["index"]]
                    self.due, self.busy = None, True
                    self.tour["phase"] = "preparing"
                    if self.tour["visit"]:
                        self.pool.submit(self.tour_worker, self.current, self.active_generation,
                                         point, original, self.tour["url"], visit=True,
                                         viewport=self.tour["viewport"], index=self.tour["index"])
                    else:
                        self.pool.submit(self.tour_worker, self.current, self.active_generation,
                                         point, original, self.tour["url"])
            elif kind == "tour_arrival" and self.tour and self.tour["phase"] == "navigating":
                self.due = None
                self.pool.submit(self.arrival_worker, self.current, self.active_generation, payload)
            elif kind == "act" and self.pending:
                # Let this short phrase finish before the next one, never queue a narrated report.
                if self.speaker and self.speaker.speaking:
                    return
                decision, target, observed = self.pending
                try:
                    # Refresh a stale target before actions; old model output is not a license to click later.
                    if time.monotonic() - observed.captured_at > 12:
                        if self.approved_step == self.step:
                            # Keep this single approval across a slow voice
                            # response, but recheck the exact same form/control.
                            self.confirmation_pending, self.busy, self.due = True, True, None
                            self.pool.submit(self.approved_action_worker, self.current, self.active_generation,
                                             self.step, decision, target, observed.data["url"])
                        else:
                            self.request_decision()
                    else:
                        perform(decision, target, observed.data["url"], self.desktop, observed.viewport)
                        self.schedule_observation("agent_action_executed")
                except CoachProtocolError as exc:
                    self.finish("blocked", str(exc))
                except Exception as exc:
                    self.current.record("action_error", {"type": type(exc).__name__})
                    self.finish("failed", "I couldn't complete that action. You can stop here and try another request.")
        notice = getattr(self, "dismiss_notice", None)
        if notice:
            generation, earliest, latest = notice
            now = time.monotonic()
            if generation != self.generation:
                self.dismiss_notice = None
            elif (self.current and self.current.state.terminal and now >= earliest
                  and (not self.speaker or not self.speaker.speaking or now >= latest)):
                self.dismiss_notice = None
                self.overlay.hide()
                self.overlay.badge(None)
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
