"""Small shared helpers: timestamps, ids, hashing, safe IO, tiny TOML subset.

Kept dependency-free so every other module can import it without cycles.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

STORE_DIRNAME = ".agentcheckpoint"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def checkpoint_id_for(now: datetime) -> str:
    return "cp_" + now.strftime("%Y%m%d_%H%M%S")


def dump_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> tuple[str | None, int | None]:
    """Return (sha256, size) of a file, or (None, None) if it cannot be read."""
    try:
        data = path.read_bytes()
    except OSError:
        return None, None
    return sha256_hex(data), len(data)


def decode_tail(data: bytes | None, limit: int) -> tuple[str, bool]:
    """Decode bytes to text, keeping the *last* ``limit`` bytes (tail semantics)."""
    data = data or b""
    truncated = len(data) > limit
    if truncated:
        data = data[-limit:]
    return data.decode("utf-8", errors="replace"), truncated


def join_rel(root: Path, rel_posix: str) -> Path:
    """Join a git-style forward-slash relative path onto a repo root."""
    return root.joinpath(*rel_posix.split("/"))


def is_in_store(rel_posix: str) -> bool:
    """True if a repo-relative path belongs to AgentCheckpoint's own store."""
    return rel_posix == STORE_DIRNAME or rel_posix.startswith(STORE_DIRNAME + "/")


def toml_dump(data: dict) -> str:
    """Serialize one level of sections with string/int/bool scalars."""
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        lines.append(_toml_pair(key, value))
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        lines.append("")
        lines.append(f"[{key}]")
        for sub_key, sub_value in value.items():
            lines.append(_toml_pair(sub_key, sub_value))
    return "\n".join(lines) + "\n"


def toml_parse(text: str) -> dict:
    """Parse the tiny TOML subset produced by :func:`toml_dump`."""
    data: dict = {}
    section: dict = data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = data.setdefault(line[1:-1].strip(), {})
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            parsed: object = value[1:-1]
        elif value in ("true", "false"):
            parsed = value == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                parsed = value
        section[key] = parsed
    return data


def _toml_pair(key: str, value: object) -> str:
    if isinstance(value, bool):
        return f"{key} = {'true' if value else 'false'}"
    if isinstance(value, int):
        return f"{key} = {value}"
    return f'{key} = "{value}"'
