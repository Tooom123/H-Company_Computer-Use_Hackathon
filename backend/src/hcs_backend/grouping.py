"""Simple, explainable grouping of similar difficulties (PRD: "Regroupement simple"; docs/TODO-tom.md item 3).

Two cases can only share a group with the same procedure (the same software when a case has no procedure)
and the same category. Inside that partition, a case joins the group whose closest member has a similar
blocker: Jaccard on the words of `escalation.blocked_on` (else the declared blocker, the symptom, the goal),
normalised by dropping quoted names, numbers, accents and case. Deterministic; every group lists its source
cases, the procedures tried, the verified results and the decisions expected from support.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .store import StoredCase

STOPWORDS = set(
    """
    the and for with from that this not are was were has have had can could cannot can't does did
    into onto when then than your you our their there here which what who why how all any its it's
    une des les pour avec dans sur par pas est sont aux ces cette que qui quoi dont mais plus sans
    sous etre avoir fait faire peut peux elle ils nous vous leur leurs son ses mon mes ton tes
    user utilisateur agent the a an of to in on is be by or as at
    """.split()
)

WORD = re.compile(r"[a-z][a-z0-9_]{2,}")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def keywords(text: str) -> set[str]:
    return {w for w in WORD.findall(_fold(text)) if w not in STOPWORDS}


QUOTED = re.compile(r"(['\"«»“”‘’]).*?(['\"«»“”‘’])")
NUMBER = re.compile(r"\b[\w.-]*\d[\w.-]*\b")


def blocked_on_text(report: dict[str, Any]) -> str:
    """The exact blocker (escalation.blocked_on, else the agent's declared blocker); for cases without a
    blocker, the symptom or the goal."""
    esc = report.get("escalation") or {}
    declared = report.get("declared") or {}
    for value in (esc.get("blocked_on"), declared.get("blocker"), report.get("symptom"), report.get("goal")):
        if value:
            return str(value)
    return ""


def normalize(text: str) -> str:
    """Drop what changes between two occurrences of the same problem: quoted names ('Globex Démo' vs
    'Umbrella Démo'), numbers and ids, accents and case."""
    text = QUOTED.sub(" ", text)
    text = NUMBER.sub(" ", text)
    return _fold(text)


def case_keywords(report: dict[str, Any]) -> set[str]:
    return keywords(normalize(blocked_on_text(report)))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def partition_key(report: dict[str, Any]) -> tuple[str, str]:
    """Two cases may only share a group with the same procedure (else the same software) and category."""
    scope = report.get("procedure_id") or f"software:{str(report.get('software', '')).strip().lower()}"
    return (str(scope), str(report.get("category", "unknown")))


@dataclass
class Group:
    group_id: str
    scope: str  # procedure_id, or "software:<name>" when the case has no procedure
    category: str
    cases: list[StoredCase] = field(default_factory=list)
    _kw: list[set[str]] = field(default_factory=list, repr=False)

    def similarity(self, kw: set[str]) -> float:
        return max((jaccard(kw, other) for other in self._kw), default=0.0)

    def add(self, case: StoredCase, kw: set[str]) -> None:
        self.cases.append(case)
        self._kw.append(kw)

    # summary -----------------------------------------------------------------------------------
    @property
    def label(self) -> str:
        first = self.cases[0].report
        esc = first.get("escalation") or {}
        text = (
            esc.get("blocked_on")
            or (first.get("declared") or {}).get("blocker")
            or first.get("suspected_cause")
            or first.get("symptom")
            or first.get("goal")
            or "?"
        )
        return str(text)

    def shared_keywords(self) -> list[str]:
        counts = Counter(w for kw in self._kw for w in kw if not w.startswith("procedure:"))
        min_count = 2 if len(self.cases) > 1 else 1
        return [w for w, c in counts.most_common(8) if c >= min_count]

    def summary(self) -> dict[str, Any]:
        reports = [c.report for c in self.cases]
        statuses = Counter(r.get("status", "unknown") for r in reports)
        verified = sum(1 for r in reports if (r.get("verification") or {}).get("satisfied") is True)
        feedback = [
            {"case_id": c.case_id, "useful": fb.get("useful"), "comment": fb["comment"]}
            for c in self.cases
            if (fb := c.report.get("feedback") or {}).get("comment")
        ]
        return {
            "group_id": self.group_id,
            "label": self.label,
            "software": self.cases[0].report.get("software"),
            "category": self.category,
            "keywords": self.shared_keywords(),
            "n_cases": len(self.cases),
            "n_users": len({c.user_key for c in self.cases}),
            "statuses": dict(statuses),
            "verified_resolved": verified,
            "needs_human": sum(1 for r in reports if r.get("needs_human")),
            "procedures": sorted({r["procedure_id"] for r in reports if r.get("procedure_id")}),
            "decisions_expected": sorted({d for r in reports
                                          if (d := (r.get("escalation") or {}).get("decision_expected"))}),
            "verified": {"observed": verified,
                         "not_observed": sum(1 for r in reports if (r.get("verification") or {}).get("satisfied") is False),
                         "not_checked": sum(1 for r in reports if (r.get("verification") or {}).get("satisfied") is None)},
            "feedback": feedback,
            "case_ids": [c.case_id for c in self.cases],
            "simulated": any(c.simulated for c in self.cases),
            "demo_data": any(c.demo_data for c in self.cases),
            "first_seen": self.cases[0].received_at,
            "last_seen": self.cases[-1].received_at,
        }


def group_cases(cases: list[StoredCase], threshold: float = 0.3) -> list[Group]:
    """Greedy grouping in arrival order; stable for a given set of cases."""
    groups: list[Group] = []
    for case in cases:
        key = partition_key(case.report)
        kw = case_keywords(case.report)
        best: Group | None = None
        best_score = 0.0
        for g in groups:
            if (g.scope, g.category) != key:
                continue
            score = g.similarity(kw)
            if score > best_score:
                best, best_score = g, score
        if best is None or best_score < threshold:
            best = Group(group_id=f"g-{case.case_id}", scope=key[0], category=key[1])
            groups.append(best)
        best.add(case, kw)
    groups.sort(key=lambda g: (-len(g.cases), g.cases[0].received_at))
    return groups
