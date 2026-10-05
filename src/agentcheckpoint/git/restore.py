"""Low-level git restore primitives: worktrees, checkout, untracked write-back.

Orchestration (safety checkpoints, hash verification, reporting) lives in
agentcheckpoint.checkpoint.restore; this module only speaks git.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agentcheckpoint import util
from agentcheckpoint.errors import RestoreError
from agentcheckpoint.git.collector import run_git


def worktree_add(root: Path, path: Path, head: str) -> None:
    # core.autocrlf=false: the base tree must be written byte-identical to the
    # git objects, otherwise recorded patches will not apply against it.
    proc = run_git(
        ["-c", "core.autocrlf=false", "worktree", "add", "--detach", str(path), head],
        root,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RestoreError(f"could not create worktree at {path}: {stderr}")


def force_checkout(root: Path, head: str) -> None:
    proc = run_git(["-c", "core.autocrlf=false", "checkout", "-f", head], root, check=False)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RestoreError(f"could not check out {head}: {stderr}")


def restore_untracked(
    untracked_src: Path,
    meta: list[dict],
    repo_root: Path,
    *,
    overwrite: bool,
) -> tuple[list[str], list[dict]]:
    """Write untracked files recorded in the checkpoint back into a working tree.

    Driven by the checkpoint's untracked.json (not by directory listing) so
    entries that were too large to store are reported, not silently lost.
    Returns (restored_paths, skipped_entries).
    """
    restored: list[str] = []
    skipped: list[dict] = []
    for entry in meta:
        rel = entry.get("path", "")
        if not rel:
            continue
        if not entry.get("stored"):
            skipped.append({"path": rel, "reason": "not stored in checkpoint"})
            continue
        dest = util.join_rel(repo_root, rel)
        if dest.exists() and not overwrite:
            skipped.append({"path": rel, "reason": "already exists in working tree"})
            continue
        src = untracked_src.joinpath(*rel.split("/"))
        if not src.is_file():
            skipped.append({"path": rel, "reason": "stored copy is missing"})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        restored.append(rel)
    return restored, skipped


def verify_restored_hashes(
    repo_root: Path, files: list[dict], skip_paths: set[str]
) -> list[str]:
    """Compare restored file contents against the hashes recorded at checkpoint."""
    mismatches: list[str] = []
    for entry in files:
        rel = entry.get("path", "")
        sha = entry.get("sha256")
        if not sha or rel in skip_paths:
            continue
        current, _ = util.hash_file(util.join_rel(repo_root, rel))
        if current != sha:
            mismatches.append(rel)
    return mismatches
