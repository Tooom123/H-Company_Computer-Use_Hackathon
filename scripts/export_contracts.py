"""Regenerate contracts/*.schema.json from the pydantic models in agent/src/hcs_agent/contract.py.

Usage (repo root): uv run --package hcs-agent python scripts/export_contracts.py
"""

from __future__ import annotations

import json
from pathlib import Path

from hcs_agent import contract

MODELS = [
    "InterventionRequest",
    "ApproveCommand",
    "StopCommand",
    "FeedbackCommand",
    "ProposedPlan",
    "AgentEvent",
    "InterventionReport",
]

out = Path(__file__).resolve().parent.parent / "contracts"
out.mkdir(exist_ok=True)
for name in MODELS:
    schema = getattr(contract, name).model_json_schema()
    (out / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print("wrote", name)
