"""Patch application helpers used by restore."""

from __future__ import annotations

from pathlib import Path

from agentcheckpoint.errors import RestoreError
from agentcheckpoint.git.collector import run_git


def apply_patch(root: Path, patch: bytes, *, cached: bool = False) -> None:
    """Apply a recorded patch to a working tree (and optionally the index).

    core.autocrlf is forced off so restored bytes match the hashes recorded at
    checkpoint time regardless of the user's line-ending configuration, and
    --ignore-whitespace tolerates CRLF/LF noise in the preimage.
    """
    if not patch.strip():
        return
    args = [
        "-c", "core.autocrlf=false",
        "apply", "--ignore-whitespace", "--whitespace=nowarn",
    ]
    if cached:
        args.append("--cached")
    args.append("-")
    proc = run_git(args, root, check=False, input=patch)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        cached_note = " (--cached)" if cached else ""
        raise RestoreError(f"git apply{cached_note} failed: {stderr}")
