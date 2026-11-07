"""Software knowledge through Linkup: sourced answers from the vendor's documentation.

Used in three places:
- before the plan, to ground the explanation given to the user (`explain`);
- during the H session, as the custom tool `lookup_docs` the agent can call when stuck;
- at escalation, to attach documentation about the blocker to the support case (`explain_blocker`).

Every answer keeps its sources: the product distinguishes provided information from observation.
"""

from __future__ import annotations

import os
from typing import Protocol

from pydantic import BaseModel, Field

DOC_DOMAINS: dict[str, list[str]] = {
    "odoo": ["odoo.com"],
}


class Source(BaseModel):
    name: str
    url: str
    snippet: str = ""


class DocAnswer(BaseModel):
    query: str
    answer: str
    sources: list[Source] = Field(default_factory=list)
    simulated: bool = False

    def as_text(self, max_sources: int = 3) -> str:
        refs = "\n".join(f"- {s.name}: {s.url}" for s in self.sources[:max_sources])
        return f"{self.answer}\n\nSources:\n{refs}" if refs else self.answer


class Knowledge(Protocol):
    simulated: bool

    def ask(self, query: str, software: str | None = None, depth: str = "standard") -> DocAnswer | None: ...


class LinkupKnowledge:
    """Linkup-backed documentation search, restricted to the vendor's domains when known."""

    simulated = False

    def __init__(self, api_key: str | None = None, timeout: float = 25.0) -> None:
        from linkup import LinkupClient

        self._client = LinkupClient(api_key=api_key) if api_key else LinkupClient()
        self.timeout = timeout

    def ask(self, query: str, software: str | None = None, depth: str = "standard") -> DocAnswer | None:
        domains = DOC_DOMAINS.get((software or "").lower())
        try:
            res = self._client.search(
                query=query,
                depth=depth,  # type: ignore[arg-type]
                output_type="sourcedAnswer",
                include_domains=domains,
                timeout=self.timeout,
            )
        except Exception:  # noqa: BLE001 - knowledge is optional, never blocks the intervention
            return None
        sources = [Source(name=s.name, url=s.url, snippet=s.snippet or "") for s in getattr(res, "sources", [])]
        return DocAnswer(query=query, answer=getattr(res, "answer", ""), sources=sources)


class MockKnowledge:
    simulated = True

    def ask(self, query: str, software: str | None = None, depth: str = "standard") -> DocAnswer | None:
        return DocAnswer(
            query=query,
            answer=f"[simulated] Documentation summary for: {query}",
            sources=[Source(name="Odoo docs (simulated)", url="https://www.odoo.com/documentation/19.0/", snippet="")],
            simulated=True,
        )


class NoKnowledge:
    simulated = False

    def ask(self, query: str, software: str | None = None, depth: str = "standard") -> DocAnswer | None:
        return None


def make_knowledge(mock: bool = False) -> Knowledge:
    if mock:
        return MockKnowledge()
    if os.environ.get("LINKUP_API_KEY"):
        return LinkupKnowledge()
    return NoKnowledge()


# --------------------------------------------------------------------------- queries


def explain_query(software: str, version: str | None, objective: str, role: str | None) -> str:
    v = f" {version}" if version else ""
    who = f" for a {role}" if role else ""
    return (f"In {software}{v}, how do you {objective[0].lower() + objective[1:].rstrip('.')}? "
            f"Give the exact menu path and button names{who}, and what the feature is for.")


def blocker_query(software: str, version: str | None, blocker: str) -> str:
    v = f" {version}" if version else ""
    return f"In {software}{v}, what causes this message and which access right or setting fixes it: \"{blocker}\""
