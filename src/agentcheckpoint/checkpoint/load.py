"""Load and integrity-check checkpoints from disk."""

from __future__ import annotations

import json
from pathlib import Path

from agentcheckpoint import util
from agentcheckpoint.errors import CheckpointError
from agentcheckpoint.schema import Manifest


def load_manifest(cp_dir: Path) -> Manifest:
    manifest = Manifest.from_file(cp_dir / "manifest.json")
    errors = manifest.validate()
    if errors:
        details = "; ".join(errors)
        raise CheckpointError(f"checkpoint {cp_dir.name} has an invalid manifest: {details}")
    return manifest


def build_integrity(cp_dir: Path) -> dict:
    """Hash every artifact in the checkpoint (except integrity.json itself)."""
    artifacts: dict[str, dict] = {}
    for path in sorted(cp_dir.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(cp_dir).as_posix()
        if rel == "integrity.json":
            continue
        data = path.read_bytes()
        artifacts[rel] = {"sha256": util.sha256_hex(data), "bytes": len(data)}
    return {
        "schema": "agent-checkpoint/integrity/v1",
        "algorithm": "sha256",
        "created_at": util.utc_now_iso(),
        "artifacts": artifacts,
    }


def integrity_check(cp_dir: Path) -> dict:
    """Re-hash all recorded artifacts and flag any drift inside the checkpoint itself."""
    integ_path = cp_dir / "integrity.json"
    if not integ_path.exists():
        return {"ok": False, "checked": 0, "problems": ["integrity.json is missing"]}
    try:
        data = json.loads(integ_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "checked": 0, "problems": [f"integrity.json unreadable: {exc}"]}
    recorded: dict = data.get("artifacts", {})
    if not isinstance(recorded, dict):
        return {
            "ok": False, "checked": 0,
            "problems": ["integrity.json artifacts must be an object"],
        }

    problems: list[str] = []
    checked = 0
    for rel, meta in sorted(recorded.items()):
        path = util.join_rel(cp_dir, rel)
        if not path.is_file():
            problems.append(f"missing artifact: {rel}")
            continue
        sha, size = util.hash_file(path)
        checked += 1
        if sha != meta.get("sha256"):
            problems.append(f"hash mismatch: {rel}")
        elif size != meta.get("bytes"):
            problems.append(f"size mismatch: {rel}")
    recorded_set = set(recorded)
    for path in sorted(cp_dir.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(cp_dir).as_posix()
        if rel == "integrity.json" or rel in recorded_set:
            continue
        problems.append(f"unrecorded artifact: {rel}")
    return {"ok": not problems, "checked": checked, "problems": problems}


def list_checkpoints(store: Path) -> list[Manifest]:
    """All checkpoints in chronological order (by id, which embeds a timestamp)."""
    from agentcheckpoint import store as store_mod

    manifests: list[Manifest] = []
    for cp_dir in store_mod.existing_checkpoint_dirs(store):
        try:
            manifests.append(load_manifest(cp_dir))
        except CheckpointError:
            continue  # unreadable checkpoints are skipped by `list`; verify surfaces them
    return manifests
