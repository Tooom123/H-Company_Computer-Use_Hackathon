"""Build agent/src/hcs_agent/data/hcompany_hub_sitemap.json from hub.hcompany.ai/llms.txt.

The hub lists every documentation page with a one-line description; each page is also served as Markdown
(same URL with .md). Run again when the documentation changes: `uv run python scripts/build_hub_sitemap.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "agent/src/hcs_agent/data/hcompany_hub_sitemap.json"
SRC = "https://hub.hcompany.ai/llms.txt"


def main() -> None:
    text = httpx.get(SRC, timeout=20, follow_redirects=True).text
    pages = []
    for m in re.finditer(r"^- \[(?P<title>[^\]]+)\]\((?P<url>https?://[^)]+)\):\s*(?P<desc>.+)$", text, re.M):
        url = m.group("url")
        pages.append({"title": m.group("title").strip(), "url": url.removesuffix(".md"), "md": url if url.endswith(".md") else url + ".md",
                      "description": m.group("desc").strip()})
    intro = "\n".join(line.strip("> ").strip() for line in text.splitlines() if line.startswith("> ") and "Agent Instructions" not in line)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": SRC, "intro": intro[:2000], "pages": pages}, indent=1, ensure_ascii=False))
    print(f"{len(pages)} pages -> {OUT}")


if __name__ == "__main__":
    main()
