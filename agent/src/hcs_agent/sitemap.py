"""What the assistant knows about a software's site, beyond the scripted procedures.

Two sources, both cheap and local:
- the **hub site map** (`data/hcompany_hub_sitemap.json`, built by `scripts/build_hub_sitemap.py` from
  hub.hcompany.ai/llms.txt): every documentation page with its one-line description; a page's Markdown can be
  fetched on demand for exact context;
- the **platform memory** (`runs/site-memory/<software>.json`): the pages the user actually visited, with the
  controls seen on each (role + label, from the accessibility tree). The platform is behind a login and cannot
  be crawled from outside, so the assistant learns it as it is used. No values, no secrets: labels only.
Both feed the router (which software, which task) and the general agent (where things are).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).parent / "data"
_MEMORY_DIR = Path("runs") / "site-memory"
_hub_cache: dict | None = None


# --------------------------------------------------------------------------- hub documentation map


def hub_pages() -> list[dict]:
    global _hub_cache
    if _hub_cache is None:
        path = DATA / "hcompany_hub_sitemap.json"
        _hub_cache = json.loads(path.read_text()) if path.exists() else {"pages": [], "intro": ""}
    return _hub_cache["pages"]


def _tokens(text: str) -> set[str]:
    """Lower-cased words, naively singularised (skills -> skill), without the usual filler."""
    out = set()
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if len(t) <= 2 or t in {"the", "and", "for", "with", "how", "your", "you", "what", "can", "does"}:
            continue
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


_REFERENCE_VERBS = {"create", "list", "retrieve", "update", "patch", "delete", "get", "send", "pause", "resume",
                    "cancel", "force", "download", "read", "write", "share", "restore"}
_LIMITS_WORDS = {"many", "limit", "limits", "quota", "plan", "plans", "concurrent", "price", "pricing", "cost",
                 "included", "free", "credits", "allowed", "maximum"}


def find_doc_pages(query: str, k: int = 4, prefer_guides: bool = True) -> list[dict]:
    """Documentation pages whose title/description share the most words with the query.
    Guides rank above API-reference pages (Create/List/Retrieve…) for information questions; questions about
    limits, quotas, plans or prices bring in 'Plans and limits'."""
    q = _tokens(query)
    scored = []
    for p in hub_pages():
        title = _tokens(p["title"])
        desc = _tokens(p["description"])
        score = 3 * len(q & title) + len(q & desc)
        first = p["title"].split()[0].lower() if p["title"] else ""
        if prefer_guides and first in _REFERENCE_VERBS:
            score -= 2
        if q & _LIMITS_WORDS and "limit" in title:
            score += 6
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda t: -t[0])
    return [p for _, p in scored[:k]]


def fetch_doc(page: dict, max_chars: int = 2500) -> str:
    """The page's Markdown, trimmed (the hub serves every page as .md)."""
    import httpx

    try:
        r = httpx.get(page["md"], timeout=10, follow_redirects=True)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return ""
    text = re.sub(r"\n{3,}", "\n\n", r.text)
    return text[:max_chars]


# --------------------------------------------------------------------------- platform memory


@dataclass
class PageMemory:
    path: str
    title: str
    controls: list[str]
    seen: int
    last: float


def _memory_file(software: str) -> Path:
    return _MEMORY_DIR / f"{software.lower()}.json"


def _load(software: str) -> dict:
    f = _memory_file(software)
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _page_key(url: str) -> str:
    """URL without query/fragment and with ids collapsed, so /sessions/abc and /sessions/def are one page."""
    url = re.sub(r"[?#].*$", "", url)
    url = re.sub(r"https?://[^/]+", "", url) or "/"
    return re.sub(r"/[0-9a-f-]{8,}|/\d+", "/<id>", url) or "/"


def software_of(url: str) -> str | None:
    u = url.lower()
    if "hcompany.ai" in u:
        return "hcompany"
    if "odoo" in u:
        return "odoo"
    return None


def remember(info) -> None:
    """Record the page the browser shows (a11y.PageInfo): interactive controls by label. Cheap, idempotent."""
    software = software_of(getattr(info, "url", "") or "")
    if not software or not getattr(info, "elements", None):
        return
    controls = []
    for e in info.elements:
        if e.role in ("AXButton", "AXLink", "AXTextField", "AXTextArea", "AXComboBox", "AXCheckBox", "AXRadioButton",
                      "AXPopUpButton", "AXMenuItem", "AXTab", "AXSearchField", "AXHeading") and 1 < len(e.name) <= 40:
            label = f"{e.role.removeprefix('AX').lower()}:{e.name}"
            if label not in controls:
                controls.append(label)
    if not controls:
        return
    mem = _load(software)
    key = _page_key(info.url)
    page = mem.get(key) or {"title": "", "controls": [], "seen": 0, "last": 0}
    merged = list(dict.fromkeys([*page["controls"], *controls]))[:80]
    mem[key] = {"title": (info.title or "")[:80], "controls": merged, "seen": page["seen"] + 1, "last": time.time()}
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _memory_file(software).write_text(json.dumps(mem, indent=0, ensure_ascii=False))
    except OSError:
        pass


def known_pages(software: str) -> list[PageMemory]:
    mem = _load(software)
    pages = [PageMemory(k, v.get("title", ""), v.get("controls", []), v.get("seen", 0), v.get("last", 0)) for k, v in mem.items()]
    pages.sort(key=lambda p: -p.seen)
    return pages


def platform_summary(software: str, max_pages: int = 12, max_controls: int = 14) -> str:
    """'Known pages and their controls' for prompts: one line per page, labels only."""
    pages = known_pages(software)
    if not pages:
        return ""
    lines = []
    for p in pages[:max_pages]:
        names = [c.split(":", 1)[1] for c in p.controls if not c.startswith("heading:")][:max_controls]
        lines.append(f"- {p.path}{' (' + p.title + ')' if p.title else ''}: {', '.join(names)}")
    return "\n".join(lines)


def context_for(software: str, goal: str, with_doc: bool = True) -> str:
    """Everything local we know that helps with this goal: matching doc pages (and the best one's content),
    plus the platform pages seen so far."""
    parts = []
    if software.lower() == "hcompany":
        pages = find_doc_pages(goal)
        if pages:
            parts.append("Documentation pages that match (hub.hcompany.ai):\n" +
                         "\n".join(f"- {p['title']}: {p['description']} ({p['url']})" for p in pages))
            if with_doc:
                body = fetch_doc(pages[0])
                if body:
                    parts.append(f"Content of '{pages[0]['title']}':\n{body}")
    summary = platform_summary(software)
    if summary:
        parts.append(f"Pages of the {software} site seen on this machine, with their controls:\n{summary}")
    return "\n\n".join(parts)
