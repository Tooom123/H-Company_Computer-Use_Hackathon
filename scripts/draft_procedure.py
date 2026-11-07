#!/usr/bin/env python3
"""Draft a guide procedure (agent/src/hcs_agent/procedures/*.yaml) from a vendor documentation page.

docs/TODO-tom.md item 6: shows that a vendor can scale from 5 hand-written tasks to dozens. The draft is a
STARTING POINT that Matteo / Claude Code validate against the live screen; it is never used as is:
- the page is fetched with Linkup (`LINKUP_API_KEY`, markdown) or, without a key, by plain HTTP (HTML);
- UI steps are extracted deterministically: Odoo "menuselection" paths (A ‣ B ‣ C) become one click per
  level, "guilabel" / bold / quoted labels become the control to frame, the verb decides click vs type;
- every guide step gets an `element` description for grounding and a `done_when` hint (what should be on
  screen after it; ignored by the current engine, meant for the reviewer);
- the YAML is validated against the engine's `Procedure` model when `hcs_agent` is importable.

    python scripts/draft_procedure.py --url https://www.odoo.com/documentation/19.0/applications/sales/crm/optimize/utilize_activities.html \\
        --id odoo_crm_draft_activities --title "Schedule an activity" --objective "Schedule a To Do on {opportunity}" \\
        -o /tmp/draft.yaml
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml

MENU_SEP = re.compile(r"\s*(?:‣|›|>|→)\s*")
CLICK_VERBS = ("click", "select", "choose", "open", "go to", "navigate", "press", "tick", "check", "enable",
               "toggle", "drag")
TYPE_VERBS = ("type", "enter", "fill", "write", "input")
UI_NOUNS = ("button", "field", "menu", "tab", "column", "card", "icon", "link", "checkbox", "dropdown", "smart button")


# ------------------------------------------------------------------------------------------- fetching
class _Text(HTMLParser):
    """HTML -> list items / paragraphs, keeping Odoo's UI markup as markers: [[label]] for guilabel,
    {{A ‣ B}} for menuselection."""

    BLOCK = {"li", "p", "h1", "h2", "h3", "h4", "dd", "dt", "td"}

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._buf: list[str] = []
        self._span: list[str | None] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class") or ""
        if tag in {"script", "style", "nav", "footer", "header"}:
            self._skip += 1
        if tag in self.BLOCK:
            self._flush()
        if tag == "span":
            kind = "gui" if "guilabel" in cls else "menu" if "menuselection" in cls else None
            self._span.append(kind)
            if kind == "gui":
                self._buf.append("[[")
            elif kind == "menu":
                self._buf.append("{{")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer", "header"} and self._skip:
            self._skip -= 1
        if tag == "span" and self._span:
            kind = self._span.pop()
            if kind == "gui":
                self._buf.append("]]")
            elif kind == "menu":
                self._buf.append("}}")
        if tag in self.BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            self.blocks.append(text)
        self._buf = []


def html_to_blocks(page: str) -> list[str]:
    p = _Text()
    p.feed(page)
    p._flush()
    return p.blocks


def markdown_to_blocks(md: str) -> list[str]:
    blocks = []
    for line in md.splitlines():
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()
        if not line:
            continue
        # Linkup markdown: **Label** or `Label` for UI labels; A > B paths stay as text
        line = re.sub(r"\*\*(.+?)\*\*|`(.+?)`", lambda m: f"[[{m.group(1) or m.group(2)}]]", line)
        blocks.append(html.unescape(line))
    return blocks


def fetch(url: str) -> list[str]:
    key = os.environ.get("LINKUP_API_KEY")
    if key:
        from linkup import LinkupClient

        return markdown_to_blocks(LinkupClient(api_key=key).fetch(url=url).markdown)
    req = urllib.request.Request(url, headers={"User-Agent": "hcs-procedure-drafter"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return html_to_blocks(resp.read().decode("utf-8", errors="replace"))


# ------------------------------------------------------------------------------------------- extraction
# "type" is also a noun ("activity type"): an input step needs the verb used as an instruction
TYPE_INSTRUCTION = re.compile(r"\b(type|enter|fill in|fill|write|input)\s+(the|a|an|in|into|your|some|its|it)\b")


def _kind(text: str) -> str | None:
    low = text.lower()
    if TYPE_INSTRUCTION.search(low) and "[[" in text:
        return "type"
    if any(re.search(rf"\b{v}\b", low) for v in CLICK_VERBS):
        return "click"
    return None


NON_ACTION = ("scroll to", "scroll down", "see", "find", "look at", "notice", "locate")


def _acted_labels(text: str, kind: str) -> list[str]:
    """Controls acted on, in order: for each action verb, the first [[label]] after it, unless a non-action
    verb sits in between ("scroll to the [[Chatter]] and click the [[Activities]]" -> Activities)."""
    low = text.lower()
    if kind == "type":
        positions = [m.start() for m in TYPE_INSTRUCTION.finditer(low)]
    else:
        positions = [m.start() for v in CLICK_VERBS for m in re.finditer(rf"\b{v}\b", low)]
    found: list[str] = []
    for pos in sorted(positions):
        for m in re.finditer(r"\[\[(.+?)\]\]", text[pos:]):
            between = low[pos:pos + m.start()]
            if any(n in between for n in NON_ACTION):
                break
            label = m.group(1).strip()
            if label and label not in found:
                found.append(label)
            break
    return found


def _noun_after(text: str, label: str) -> str:
    m = re.search(re.escape(f"[[{label}]]") + r"\s+(\w+(?:\s+button)?)", text)
    if m and any(m.group(1).lower().startswith(n.split()[0]) for n in UI_NOUNS):
        return m.group(1).lower()
    return "control"


def extract_steps(blocks: list[str], max_steps: int = 12) -> list[dict[str, Any]]:
    """Documentation blocks -> ordered UI steps {instruction, element, kind, done_when, source}."""
    steps: list[dict[str, Any]] = []
    for b in blocks:
        menus = re.findall(r"\{\{(.+?)\}\}", b)
        for path in menus:  # each level of a menu path is one click
            levels = [x.strip() for x in MENU_SEP.split(path) if x.strip()]
            for i, lvl in enumerate(levels):
                where = "in the main menu / app switcher" if i == 0 else f"in the {levels[i - 1]} menu"
                steps.append({"instruction": f"Clique sur {lvl}", "element": f"the {lvl} menu entry {where}",
                              "kind": "click", "done_when": f"the {lvl} menu or page is displayed", "source": b})
        kind = _kind(b)
        labels = [x.strip() for x in re.findall(r"\[\[(.+?)\]\]", b) if x.strip()]
        if not kind or not labels:
            continue
        for label in _acted_labels(b, kind) or [labels[-1] if kind == "type" else labels[0]]:
            noun = _noun_after(b, label)
            if kind == "type":
                steps.append({"instruction": f"Renseigne le champ {label}", "element": f"the {label} field",
                              "kind": "type", "done_when": f"the {label} field shows the typed value", "source": b})
            else:
                steps.append({"instruction": f"Clique sur {label}", "element": f"the {label} {noun}",
                              "kind": "click", "done_when": f"what {label} opens is displayed", "source": b})
        if len(steps) >= max_steps:
            break
    # consecutive duplicates (same control mentioned twice in a row) are merged
    out: list[dict[str, Any]] = []
    for s in steps[:max_steps]:
        if not out or out[-1]["element"] != s["element"]:
            out.append(s)
    return out


# ------------------------------------------------------------------------------------------- drafting
def draft(steps: list[dict[str, Any]], *, proc_id: str, title: str, objective: str, software: str,
          version: str | None, url: str) -> dict[str, Any]:
    guide = [{"instruction": s["instruction"], "element": s["element"], "kind": s["kind"],
              "why": f"D'après la documentation : {s['source'][:160]}", "done_when": s["done_when"]} for s in steps]
    numbered = "\n".join(f"  {i}. {s['instruction']} ({s['element']})." for i, s in enumerate(steps, 1))
    return {
        "id": proc_id, "software": software, "software_version": version, "session_type": "onboarding",
        "title": title, "reversible": True, "max_attempts": 2,
        "parameters": [{"name": "opportunity", "description": "Name of the record to work on", "required": False,
                        "default": "Acme Demo"}],
        "preconditions": [f"{software} is open in the browser on the main display and the user is logged in.",
                          "DRAFT: add the record/state this task needs."],
        "objective": objective,
        "planned_changes": ["DRAFT: list exactly what this task changes."],
        "allowed_actions": [f"Navigate inside {software} and follow the documented steps."],
        "forbidden_actions": ["Deleting or archiving any record.", "Sending any email or message.",
                              f"Leaving the {software} browser tab or opening other applications."],
        "agent_instructions": (f"You are assisting a user inside {software} ({version or 'current version'}) in a "
                               f"browser. Work only inside the visible tab.\nProcedure (from {url}):\n{numbered}\n"
                               "If something prevents a step, stop and report it as blocked with the exact message.\n"),
        "guide_steps": guide,
        "expected_screen": "DRAFT: describe the base screen before step 1",
        "postcondition": {
            "description": f"DRAFT: observable result of: {objective}",
            "checks": [{"key": "result_visible", "prompt": f"DRAFT: the result of '{objective}' is visible on screen."}],
            "verification_instructions": ("You are a read-only verifier. Stay inside the visible browser tab; do not "
                                          "reload the page. Do not create, edit or delete anything. Report exactly "
                                          "what you observe."),
        },
        "escalation": {"when": ["The agent reports \"blocked\".",
                                "The postcondition is not satisfied after max_attempts."],
                       "decision_expected": "DRAFT: what support must decide when this task is blocked.",
                       "default_category": "unknown"},
    }


def validate(proc: dict[str, Any]) -> str:
    """Validate against the engine's Procedure model when hcs_agent is importable."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent" / "src"))
        from hcs_agent.procedures import Procedure
    except Exception as e:  # pragma: no cover - environment without the agent package
        return f"not validated (hcs_agent not importable: {e})"
    Procedure.model_validate(proc)
    return "valid for the engine's Procedure model"


def to_yaml(proc: dict[str, Any], url: str, status: str) -> str:
    head = (f"# DRAFT generated by scripts/draft_procedure.py from {url}\n"
            f"# {status}. Validate every step against the live screen before use: element descriptions are\n"
            "# guesses from the documentation, `done_when` is a hint for the reviewer (ignored by the engine),\n"
            "# and every DRAFT field must be written by hand.\n")
    return head + yaml.safe_dump(proc, sort_keys=False, allow_unicode=True, width=110)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="documentation page")
    src.add_argument("--file", help="local HTML or Markdown file (offline)")
    p.add_argument("--id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--software", default="odoo")
    p.add_argument("--version", default="19.0")
    p.add_argument("--max-steps", type=int, default=12)
    p.add_argument("-o", "--output", help="write the YAML here (default: stdout)")
    a = p.parse_args(argv)
    if a.url:
        blocks, origin = fetch(a.url), a.url
    else:
        text = Path(a.file).read_text(encoding="utf-8")
        blocks = html_to_blocks(text) if a.file.endswith((".html", ".htm")) else markdown_to_blocks(text)
        origin = a.file
    steps = extract_steps(blocks, a.max_steps)
    if not steps:
        print("no UI step found in this page", file=sys.stderr)
        return 1
    proc = draft(steps, proc_id=a.id, title=a.title, objective=a.objective, software=a.software,
                 version=a.version, url=origin)
    out = to_yaml(proc, origin, validate(proc))
    if a.output:
        Path(a.output).write_text(out, encoding="utf-8")
        print(f"{len(steps)} steps -> {a.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
