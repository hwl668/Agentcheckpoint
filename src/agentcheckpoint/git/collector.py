"""Collect git state by running git directly.

Nothing in this module asks an LLM what the repository looks like — every
value comes from a git invocation. A checkpoint's ground truth starts here.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from agentcheckpoint import util
from agentcheckpoint.errors import GitError, NotAGitRepository

# Object name of the empty tree; used as the diff base for repos with no commits yet.
EMPTY_TREE_SHA1 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@dataclass
class PathChange:
    path: str
    code: str  # git name-status letter, e.g. M / A / D / R100
    orig_path: str | None = None

    def to_dict(self) -> dict:
        return {"path": self.path, "code": self.code, "orig_path": self.orig_path}


@dataclass
class GitSnapshot:
    root: Path
    branch: str | None
    detached: bool
    head: str | None
    head_subject: str | None
    head_committed_at: str | None
    staged: list[PathChange] = field(default_factory=list)
    unstaged: list[PathChange] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    staged_patch: bytes = b""
    tracked_patch: bytes = b""
    files: list[dict] = field(default_factory=list)  # {path, states, codes, sha256, bytes}

    @property
    def is_clean(self) -> bool:
        return not (self.staged or self.unstaged or self.untracked or self.conflicts)


def run_git(
    args: list[str],
    cwd: Path,
    check: bool = True,
    input: bytes | None = None,
) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, input=input
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    if check and proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git {' '.join(args)} failed (exit {proc.returncode}): {stderr}")
    return proc


def git_text(args: list[str], cwd: Path, check: bool = True) -> str:
    proc = run_git(args, cwd, check=check)
    return proc.stdout.decode("utf-8", errors="replace").strip()


def is_git_repo(cwd: Path) -> bool:
    if not Path(cwd).exists():
        return False
    proc = run_git(["rev-parse", "--is-inside-work-tree"], Path(cwd), check=False)
    return proc.returncode == 0 and proc.stdout.decode("utf-8", errors="replace").strip() == "true"


def repo_root(cwd: Path) -> Path:
    if not is_git_repo(cwd):
        raise NotAGitRepository(f"not a git repository: {cwd}")
    out = git_text(["rev-parse", "--show-toplevel"], Path(cwd))
    return Path(out).resolve()


def _parse_name_status_z(raw: bytes) -> list[PathChange]:
    """Parse ``git diff --name-status -z`` output (rename entries carry two paths)."""
    tokens = [t.decode("utf-8", errors="replace") for t in raw.split(b"\0") if t]
    changes: list[PathChange] = []
    i = 0
    while i < len(tokens):
        code = tokens[i]
        i += 1
        if i >= len(tokens):
            break
        path = tokens[i]
        i += 1
        orig: str | None = None
        if code[0] in "RC" and len(code) > 1 and i < len(tokens):
            orig = tokens[i]
            i += 1
        changes.append(PathChange(path=path, code=code, orig_path=orig))
    return changes


def _split_nul(raw: bytes) -> list[str]:
    return [t.decode("utf-8", errors="replace") for t in raw.split(b"\0") if t]


def collect(root: Path) -> GitSnapshot:
    """Snapshot the full working-tree state of the repository at ``root``."""
    root = Path(root)
    if not is_git_repo(root):
        raise NotAGitRepository(f"not a git repository: {root}")

    branch_text = git_text(["branch", "--show-current"], root)
    detached = branch_text == ""
    head: str | None = None
    head_proc = run_git(["rev-parse", "--verify", "HEAD"], root, check=False)
    if head_proc.returncode == 0:
        head = head_proc.stdout.decode("utf-8", errors="replace").strip()
    head_subject = head_committed_at = None
    if head:
        meta = git_text(["log", "-1", "--pretty=%s%x1f%cI"], root)
        if "\x1f" in meta:
            head_subject, head_committed_at = meta.split("\x1f", 1)
        else:
            head_subject = meta

    # Against an unborn HEAD, diff against the empty tree instead.
    base: list[str] = [] if head else [EMPTY_TREE_SHA1]
    staged: list[PathChange] = []
    staged_patch = b""
    try:
        staged = _parse_name_status_z(
            run_git(["diff", "--cached", "--name-status", "-z", *base], root).stdout
        )
        staged_patch = run_git(["diff", "--cached", "--binary", *base], root).stdout
    except GitError:
        pass  # e.g. sha256-object repos where the sha1 empty-tree name does not exist
    unstaged = _parse_name_status_z(run_git(["diff", "--name-status", "-z"], root).stdout)
    conflicts = _split_nul(
        run_git(["diff", "--name-only", "--diff-filter=U", "-z"], root).stdout
    )
    untracked = [
        p
        for p in _split_nul(
            run_git(["ls-files", "--others", "--exclude-standard", "-z"], root).stdout
        )
        if not util.is_in_store(p)
    ]
    tracked_patch = run_git(["diff", "--binary"], root).stdout

    snapshot = GitSnapshot(
        root=root,
        branch=branch_text or None,
        detached=detached,
        head=head,
        head_subject=head_subject,
        head_committed_at=head_committed_at or None,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        conflicts=conflicts,
        staged_patch=staged_patch,
        tracked_patch=tracked_patch,
    )
    snapshot.files = _observed_files(snapshot)
    return snapshot


def _observed_files(snap: GitSnapshot) -> list[dict]:
    """Union of all changed/untracked paths with per-file state and content hashes."""
    registry: dict[str, dict] = {}

    def register(path: str, state: str, code: str | None = None) -> None:
        entry = registry.setdefault(path, {"path": path, "states": [], "codes": {}})
        if state not in entry["states"]:
            entry["states"].append(state)
        if code:
            entry["codes"][state] = code

    for change in snap.staged:
        register(change.path, "staged", change.code)
    for change in snap.unstaged:
        register(change.path, "unstaged", change.code)
    for path in snap.untracked:
        register(path, "untracked")
    for path in snap.conflicts:
        register(path, "conflict")

    files: list[dict] = []
    for path in sorted(registry):
        if util.is_in_store(path):
            continue
        entry = registry[path]
        sha, size = util.hash_file(util.join_rel(snap.root, path))
        files.append(
            {
                "path": path,
                "states": entry["states"],
                "codes": entry["codes"],
                "sha256": sha,
                "bytes": size,
            }
        )
    return files
