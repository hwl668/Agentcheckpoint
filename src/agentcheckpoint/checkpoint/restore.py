"""Restore orchestration: safe worktree restore (default) and guarded in-place restore.

Safety rules:
- worktree mode (default) never touches the current working tree at all.
- in-place mode refuses to run without an explicit --yes, and always writes an
  automatic safety checkpoint of the current state before rewriting anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agentcheckpoint.checkpoint.create import save_checkpoint
from agentcheckpoint.checkpoint.load import integrity_check
from agentcheckpoint.errors import RestoreError
from agentcheckpoint.git import patch as git_patch
from agentcheckpoint.git import restore as git_restore
from agentcheckpoint.schema import Manifest, SemanticData


@dataclass
class RestoreResult:
    checkpoint_id: str
    mode: str
    path: Path
    restored_untracked: list[str] = field(default_factory=list)
    skipped_untracked: list[dict] = field(default_factory=list)
    hash_mismatches: list[str] = field(default_factory=list)
    hash_checked: int = 0
    safety_checkpoint_id: str | None = None
    notes: list[str] = field(default_factory=list)


def restore_checkpoint(
    root: Path,
    store_path: Path,
    cp_dir: Path,
    manifest: Manifest,
    *,
    mode: str,
    target_path: Path | None,
    config: dict,
    overwrite_untracked: bool = False,
) -> RestoreResult:
    integrity = integrity_check(cp_dir)
    if not integrity["ok"]:
        problems = "; ".join(integrity["problems"][:5])
        raise RestoreError(
            f"checkpoint {manifest.id} failed integrity verification "
            f"({problems}) — refusing to restore"
        )

    head = manifest.head
    if head is None:
        raise RestoreError(
            f"checkpoint {manifest.id} was taken in a repository with no commits; "
            "there is no base commit to restore onto"
        )

    if mode == "worktree":
        path = target_path or root.parent / f"{root.name}-agentck-{manifest.id}"
        if path.exists():
            raise RestoreError(
                f"target path already exists: {path} — choose another with --path"
            )
        git_restore.worktree_add(root, path, head)
        restore_root = path
        safety_id = None
        overwrite = True
    elif mode == "in_place":
        safety_id, _, _, _ = save_checkpoint(
            root,
            store_path,
            label=f"pre-restore-{manifest.id}",
            semantic=SemanticData(
                goal=f"automatic safety checkpoint before in-place restore of {manifest.id}"
            ),
            config=config,
        )
        git_restore.force_checkout(root, head)
        restore_root = root
        overwrite = overwrite_untracked
    else:  # pragma: no cover - guarded by the CLI
        raise RestoreError(f"unknown restore mode: {mode}")

    staged_patch = (cp_dir / "git" / "staged.patch").read_bytes()
    tracked_patch = (cp_dir / "git" / "tracked.patch").read_bytes()
    # Order matters: staged patch onto the worktree (base == HEAD), then into the
    # index, then the unstaged patch (its preimage is the staged content).
    if staged_patch.strip():
        git_patch.apply_patch(restore_root, staged_patch)
        git_patch.apply_patch(restore_root, staged_patch, cached=True)
    if tracked_patch.strip():
        git_patch.apply_patch(restore_root, tracked_patch)

    untracked_meta = _load_untracked_meta(cp_dir)
    untracked_src = cp_dir / "git" / "untracked"
    restored, skipped = git_restore.restore_untracked(
        untracked_src, untracked_meta, restore_root, overwrite=overwrite
    )

    skip_paths = {entry["path"] for entry in skipped}
    mismatches = git_restore.verify_restored_hashes(
        restore_root, manifest.observed_files, skip_paths
    )
    hash_checked = sum(
        1
        for entry in manifest.observed_files
        if entry.get("sha256") and entry["path"] not in skip_paths
    )

    notes = [
        "HEAD is detached at the checkpoint's commit; re-stage or branch as needed",
        "staged/unstaged split was reconstructed from patches; conflicts were not restorable",
    ]
    if mode == "in_place":
        notes.append(
            f"safety checkpoint {safety_id} captured the state this restore replaced"
        )
    return RestoreResult(
        checkpoint_id=manifest.id,
        mode=mode,
        path=restore_root,
        restored_untracked=restored,
        skipped_untracked=skipped,
        hash_mismatches=mismatches,
        hash_checked=hash_checked,
        safety_checkpoint_id=safety_id,
        notes=notes,
    )


def _load_untracked_meta(cp_dir: Path) -> list[dict]:
    import json

    path = cp_dir / "git" / "untracked.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    files = data.get("files", [])
    return files if isinstance(files, list) else []
