"""On-disk store: .agentcheckpoint layout, config, ids, reference resolution.

The store is the single source of truth for where checkpoints live and how
they are named/referenced. It deliberately knows nothing about manifests
beyond a light label read, to avoid import cycles.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from agentcheckpoint import util
from agentcheckpoint.errors import CheckpointError, NotAGitRepository, StoreError
from agentcheckpoint.git.collector import is_git_repo
from agentcheckpoint.schema import SCHEMA_ID

STORE_DIRNAME = util.STORE_DIRNAME
CONFIG_NAME = "config.toml"
INDEX_NAME = "index.jsonl"
CHECKPOINTS_DIRNAME = "checkpoints"

DEFAULT_LIMITS = {
    "max_untracked_file_bytes": 10 * 1024 * 1024,
    "max_test_output_bytes": 64 * 1024,
    "test_timeout_seconds": 600,
}


def config_template() -> str:
    return util.toml_dump(
        {
            "schema": SCHEMA_ID,
            "created_at": util.utc_now_iso(),
            "tool": "agentcheckpoint",
            "limits": dict(DEFAULT_LIMITS),
        }
    )


def load_config(store: Path) -> dict:
    text = (store / CONFIG_NAME).read_text(encoding="utf-8")
    data = util.toml_parse(text)
    limits = dict(DEFAULT_LIMITS)
    raw_limits = data.get("limits", {})
    if isinstance(raw_limits, dict):
        for key in DEFAULT_LIMITS:
            if isinstance(raw_limits.get(key), int) and raw_limits[key] > 0:
                limits[key] = raw_limits[key]
    return {
        "schema": data.get("schema"),
        "created_at": data.get("created_at"),
        "limits": limits,
    }


def find_store(cwd: Path) -> tuple[Path, Path] | None:
    """Walk up from cwd looking for an initialized store; return (repo_root, store)."""
    for candidate in [cwd, *cwd.parents]:
        store = candidate / STORE_DIRNAME
        if store.is_dir() and (store / CONFIG_NAME).is_file():
            return candidate.resolve(), store
    return None


def open_store(cwd: Path) -> tuple[Path, Path]:
    """Return (repo_root, store) for the current location or raise a clear error."""
    found = find_store(cwd)
    if found is not None:
        return found
    if is_git_repo(cwd):
        raise StoreError(
            "AgentCheckpoint is not initialized in this repository — run `agentck init` first."
        )
    raise NotAGitRepository(
        f"not a git repository (and no AgentCheckpoint store in any parent): {cwd}"
    )


def init_store(root: Path) -> tuple[Path, bool, bool]:
    """Create the store if needed. Returns (store, created, exclude_added)."""
    store = root / STORE_DIRNAME
    created = not store.exists()
    (store / CHECKPOINTS_DIRNAME).mkdir(parents=True, exist_ok=True)
    config_path = store / CONFIG_NAME
    if not config_path.exists():
        config_path.write_text(config_template(), encoding="utf-8")
    exclude_added = _add_to_git_exclude(root)
    return store, created, exclude_added


def _add_to_git_exclude(root: Path) -> bool:
    """Add .agentcheckpoint/ to .git/info/exclude (local-only, reversible)."""
    exclude = root / ".git" / "info" / "exclude"
    if not exclude.parent.is_dir():
        return False
    try:
        text = exclude.read_text(encoding="utf-8", errors="replace") if exclude.exists() else ""
        if STORE_DIRNAME in text:
            return False
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write("\n# added by agentck: keep its own checkpoint store out of git status\n")
            fh.write(f"{STORE_DIRNAME}/\n")
    except OSError:
        return False
    return True


def checkpoints_dir(store: Path) -> Path:
    return store / CHECKPOINTS_DIRNAME


def existing_checkpoint_dirs(store: Path) -> list[Path]:
    base = checkpoints_dir(store)
    if not base.is_dir():
        return []
    return sorted(d for d in base.iterdir() if d.is_dir() and d.name.startswith("cp_"))


def new_checkpoint_id(store: Path, now: datetime | None = None) -> str:
    """Timestamp-based id, de-duplicated with a numeric suffix within the same second."""
    taken = {d.name for d in existing_checkpoint_dirs(store)}
    base = util.checkpoint_id_for(now or util.utc_now())
    if base not in taken:
        return base
    index = 1
    while f"{base}_{index}" in taken:
        index += 1
    return f"{base}_{index}"


def latest_checkpoint(store: Path) -> Path | None:
    dirs = existing_checkpoint_dirs(store)
    return dirs[-1] if dirs else None


def _checkpoint_label(cp_dir: Path) -> str | None:
    try:
        data = json.loads((cp_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    label = data.get("label")
    return label if isinstance(label, str) else None


def resolve_ref(store: Path, ref: str) -> Path:
    """Resolve 'latest', an exact id, a unique id prefix, or a label."""
    base = checkpoints_dir(store)
    if ref == "latest":
        latest = latest_checkpoint(store)
        if latest is None:
            raise CheckpointError("no checkpoints exist yet — run `agentck save` first")
        return latest
    exact = base / ref
    if exact.is_dir():
        return exact
    dirs = existing_checkpoint_dirs(store)
    prefixes = [d for d in dirs if d.name.startswith(ref)]
    if len(prefixes) == 1:
        return prefixes[0]
    if len(prefixes) > 1:
        names = ", ".join(d.name for d in prefixes)
        raise CheckpointError(f"reference {ref!r} is ambiguous: {names}")
    label_matches = [d for d in dirs if _checkpoint_label(d) == ref]
    if label_matches:
        return label_matches[-1]
    raise CheckpointError(f"no checkpoint matches {ref!r}")


def append_index(store: Path, entry: dict) -> None:
    """Append one JSON line to index.jsonl (forward-compatible with external tools)."""
    index_path = store / INDEX_NAME
    with index_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_index(store: Path) -> list[dict]:
    index_path = store / INDEX_NAME
    if not index_path.exists():
        return []
    entries = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
