"""agent-checkpoint/v1 schema: manifest container and semantic-input validation.

The manifest is kept as a plain dict (JSON fidelity matters more than
dataclass ceremony); this module adds typed accessors and validation.
SemanticData is the strict, agent-facing input contract.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from agentcheckpoint.errors import CheckpointError

SCHEMA_ID = "agent-checkpoint/v1"

CHECKPOINT_ID_RE = re.compile(r"^cp_\d{8}_\d{6}(_\d+)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")

SEMANTIC_SCALAR_FIELDS = ("agent", "goal", "status")
SEMANTIC_LIST_FIELDS = (
    "completed",
    "decisions",
    "constraints",
    "blockers",
    "next_steps",
    "do_not",
    "tests",
)
SEMANTIC_FIELDS = SEMANTIC_SCALAR_FIELDS + SEMANTIC_LIST_FIELDS


class SchemaError(ValueError):
    """Invalid schema input (manifest or semantic file)."""


@dataclass
class SemanticData:
    """Agent-provided context for a checkpoint.

    ``tests`` is special: it is not a claim but an instruction for the engine
    to run those commands now and record exit codes as machine-observed facts.
    """

    agent: str | None = None
    goal: str | None = None
    status: str | None = None
    completed: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    do_not: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    source: str = "flags"

    def merge(self, other: SemanticData) -> None:
        """Merge ``other`` into self: its scalars win when set, its lists extend."""
        if other.agent:
            self.agent = other.agent
        if other.goal:
            self.goal = other.goal
        if other.status:
            self.status = other.status
        for name in SEMANTIC_LIST_FIELDS:
            getattr(self, name).extend(getattr(other, name))

    def is_empty(self) -> bool:
        scalars_empty = self.agent is None and self.goal is None and self.status is None
        lists_empty = all(not getattr(self, name) for name in SEMANTIC_LIST_FIELDS)
        return scalars_empty and lists_empty

    def to_claims(self) -> dict:
        return {
            "completed": list(self.completed),
            "decisions": list(self.decisions),
            "constraints": list(self.constraints),
            "blockers": list(self.blockers),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: object, source: str = "file") -> SemanticData:
        if not isinstance(data, dict):
            raise SchemaError("semantic input must be a JSON object")
        unknown = sorted(set(data) - set(SEMANTIC_FIELDS))
        if unknown:
            raise SchemaError(
                f"unknown semantic field(s): {', '.join(unknown)}; allowed: "
                f"{', '.join(SEMANTIC_FIELDS)}"
            )
        for name in SEMANTIC_SCALAR_FIELDS:
            value = data.get(name)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise SchemaError(f"semantic field {name!r} must be a non-empty string")
        instance = cls(
            agent=data.get("agent"),
            goal=data.get("goal"),
            status=data.get("status"),
            source=source,
        )
        for name in SEMANTIC_LIST_FIELDS:
            value = data.get(name, [])
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise SchemaError(
                    f"semantic field {name!r} must be a list of non-empty strings"
                )
            setattr(instance, name, list(value))
        return instance


class Manifest:
    """Typed accessor + validator over a manifest.json dict."""

    def __init__(self, data: dict, path: Path | None = None):
        self.data = data
        self.path = path

    @classmethod
    def from_file(cls, path: Path) -> Manifest:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CheckpointError(f"cannot read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CheckpointError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise CheckpointError(f"{path} must contain a JSON object")
        return cls(data, path=path)

    # -- typed accessors ---------------------------------------------------

    @property
    def id(self) -> str:
        return self.data.get("id", "")

    @property
    def parent(self) -> str | None:
        return self.data.get("parent")

    @property
    def label(self) -> str | None:
        return self.data.get("label")

    @property
    def created_at(self) -> str | None:
        return self.data.get("created_at")

    @property
    def source_agent(self) -> str | None:
        return self.data.get("source_agent")

    @property
    def branch(self) -> str | None:
        return self.data.get("repo", {}).get("branch")

    @property
    def head(self) -> str | None:
        return self.data.get("repo", {}).get("head")

    @property
    def repo_root(self) -> str | None:
        return self.data.get("repo", {}).get("root")

    @property
    def goal(self) -> str | None:
        return self.data.get("task", {}).get("goal")

    @property
    def status(self) -> str | None:
        return self.data.get("task", {}).get("status")

    @property
    def claims(self) -> dict:
        return self.data.get("agent_claims", {})

    @property
    def completed(self) -> list[str]:
        return self.claims.get("completed", []) or []

    @property
    def next(self) -> list[str]:
        return self.data.get("next", []) or []

    @property
    def do_not(self) -> list[str]:
        return self.data.get("do_not", []) or []

    @property
    def tests(self) -> list[dict]:
        return self.data.get("verification", {}).get("tests", []) or []

    @property
    def observed_files(self) -> list[dict]:
        return self.data.get("observed", {}).get("files", []) or []

    @property
    def modified_files(self) -> list[str]:
        return self.data.get("observed", {}).get("modified_files", []) or []

    # -- validation --------------------------------------------------------

    def validate(self) -> list[str]:
        d = self.data
        errors: list[str] = []
        if d.get("schema") != SCHEMA_ID:
            errors.append(f"schema must be {SCHEMA_ID!r}, got {d.get('schema')!r}")
        if not CHECKPOINT_ID_RE.match(str(d.get("id", ""))):
            errors.append(f"id {d.get('id')!r} is not a valid checkpoint id")
        if not ISO_TS_RE.match(str(d.get("created_at", ""))):
            errors.append("created_at is not an ISO-8601 timestamp")
        for key in ("repo", "task", "observed", "agent_claims", "verification"):
            if not isinstance(d.get(key), dict):
                errors.append(f"{key!r} must be an object")
        tests = d.get("verification", {}).get("tests") if isinstance(
            d.get("verification"), dict
        ) else None
        if tests is not None and not isinstance(tests, list):
            errors.append("verification.tests must be a list")
        for key in ("next", "do_not"):
            value = d.get(key)
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                errors.append(f"{key!r} must be a list of strings")
        claims = d.get("agent_claims")
        if isinstance(claims, dict):
            for key in ("completed", "decisions", "constraints", "blockers"):
                value = claims.get(key)
                if value is None:
                    continue
                if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                    errors.append(f"agent_claims.{key} must be a list of strings")
        files = d.get("observed", {}).get("files") if isinstance(d.get("observed"), dict) else None
        if files is not None:
            if not isinstance(files, list):
                errors.append("observed.files must be a list")
            else:
                for entry in files:
                    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                        errors.append("observed.files entries must be objects with a 'path'")
                        break
        return errors
