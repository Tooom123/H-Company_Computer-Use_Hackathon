"""Validate incoming payloads against the shared JSON Schemas in contracts/.

The schemas are generated from the agent's pydantic models; validating against them (rather than
re-declaring models here) keeps one source of truth for the contract.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


class ContractError(ValueError):
    def __init__(self, schema: str, errors: list[str]):
        super().__init__(f"{schema}: " + "; ".join(errors))
        self.schema = schema
        self.errors = errors


@lru_cache(maxsize=None)
def _validator(contracts_dir: str, name: str) -> Draft202012Validator:
    schema = json.loads((Path(contracts_dir) / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate(contracts_dir: Path, name: str, payload: object) -> None:
    errors = sorted(_validator(str(contracts_dir), name).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        raise ContractError(
            name, [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors[:20]]
        )
