"""Verify a checkpoint against the current repository: drift, staleness, confidence."""

from __future__ import annotations

import os
from pathlib import Path

from agentcheckpoint import util
from agentcheckpoint.checkpoint.load import integrity_check
from agentcheckpoint.git import collector
from agentcheckpoint.schema import Manifest


def normalize_root(path: str | Path | None) -> str | None:
    if not path:
        return None
    try:
        resolved = Path(path).resolve()
    except OSError:
        return None
    return os.path.normcase(resolved.as_posix())


def current_repo_root(manifest: Manifest, cwd: Path) -> Path | None:
    """Prefer the repo the user is standing in; fall back to the recorded root."""
    if collector.is_git_repo(cwd):
        try:
            return collector.repo_root(cwd)
        except Exception:  # noqa: BLE001 - any failure means "not accessible"
            pass
    recorded = manifest.repo_root
    if recorded and Path(recorded).is_dir():
        return Path(recorded)
    return None


def verify_checkpoint(cp_dir: Path, manifest: Manifest, current_root: Path | None) -> dict:
    m = manifest.data
    repo = m.get("repo", {})
    observed = m.get("observed", {})
    files = observed.get("files", []) or []
    tests = manifest.tests

    integrity = integrity_check(cp_dir)

    report: dict = {
        "id": manifest.id,
        "label": manifest.label,
        "created_at": manifest.created_at,
        "source_agent": manifest.source_agent,
        "integrity": integrity,
        "repository": {
            "accessible": current_root is not None,
            "same_path": None,
            "recorded_root": repo.get("root"),
            "branch": {"recorded": repo.get("branch"), "current": None, "same": None},
            "head": {"recorded": repo.get("head"), "current": None, "same": None, "exists": None},
            "notes": [],
        },
        "files": [],
        "files_summary": {"unchanged": 0, "changed": 0, "missing": 0},
        "new_changes": {"count": 0, "paths": []},
        "tests": [],
        "claims": [{"claim": claim, "status": "agent-reported"} for claim in manifest.completed],
        "drift": None,
    }

    head_same = branch_same = head_exists = None
    file_rows: list[dict] = []

    if current_root is None:
        report["repository"]["notes"].append(
            "repository state could not be inspected from the current location"
        )
    else:
        same_path = normalize_root(repo.get("root")) == normalize_root(current_root)
        report["repository"]["same_path"] = same_path
        if not same_path:
            report["repository"]["notes"].append(
                "current directory is a different repository "
                "than the one recorded in this checkpoint"
            )
        else:
            snap = collector.collect(current_root)
            recorded_head = repo.get("head")
            head_same = snap.head == recorded_head
            branch_same = (snap.branch or None) == (repo.get("branch") or None)
            head_exists = recorded_head is None or _head_exists(current_root, recorded_head)

            observed_paths = {f.get("path") for f in files}
            for entry in files:
                rel = entry["path"]
                current_sha, _ = util.hash_file(util.join_rel(current_root, rel))
                recorded_sha = entry.get("sha256")
                if current_sha is None and recorded_sha is None:
                    verdict = "unchanged"  # deleted then, deleted now
                elif current_sha is None:
                    verdict = "missing"
                elif current_sha == recorded_sha:
                    verdict = "unchanged"
                else:
                    verdict = "changed"
                file_rows.append(
                    {"path": rel, "states": entry.get("states", []), "verdict": verdict}
                )
            new_paths = [f["path"] for f in snap.files if f["path"] not in observed_paths]
            report["new_changes"] = {"count": len(new_paths), "paths": new_paths[:20]}

            report["repository"]["branch"].update(current=snap.branch, same=branch_same)
            report["repository"]["head"].update(
                current=snap.head, same=head_same, exists=head_exists
            )

    drift = None
    if head_same is not None or file_rows:
        drift = (head_same is False) or any(
            row["verdict"] in ("changed", "missing") for row in file_rows
        )
    report["drift"] = drift
    report["files"] = file_rows
    for row in file_rows:
        report["files_summary"][row["verdict"]] = report["files_summary"].get(row["verdict"], 0) + 1

    for test in tests:
        verdict = "stale" if drift else "recorded"
        reason = (
            "repository drifted after this command ran"
            if drift
            else "no drift since checkpoint; not re-run"
        )
        report["tests"].append({
            "command": test.get("command"),
            "exit_code": test.get("exit_code"),
            "verdict": verdict,
            "reason": reason,
        })

    confidence, breakdown = _confidence(
        integrity_ok=integrity["ok"],
        accessible=current_root is not None,
        same_path=report["repository"]["same_path"],
        head_same=head_same,
        head_exists=head_exists,
        branch_same=branch_same,
        file_rows=file_rows,
        tests_present=bool(tests),
        drift=drift,
    )
    report["confidence"] = confidence
    report["confidence_breakdown"] = breakdown
    return report


def _head_exists(root: Path, head: str) -> bool:
    proc = collector.run_git(["cat-file", "-e", f"{head}^{{commit}}"], root, check=False)
    return proc.returncode == 0


def _confidence(
    *,
    integrity_ok: bool,
    accessible: bool,
    same_path: bool | None,
    head_same: bool | None,
    head_exists: bool | None,
    branch_same: bool | None,
    file_rows: list[dict],
    tests_present: bool,
    drift: bool | None,
) -> tuple[int, list[str]]:
    """Deterministic resume-confidence heuristic. The exact formula is documented
    in spec/agent-checkpoint-v1.md; it is a triage signal, not a proof."""
    if not integrity_ok:
        return 0, ["checkpoint integrity verification failed"]
    if not accessible:
        return 10, ["repository state could not be inspected"]
    if same_path is False:
        return 20, ["current directory is a different repository than the checkpoint's"]

    score = 100
    breakdown: list[str] = []
    if head_exists is False:
        score -= 50
        breakdown.append("-50 recorded HEAD commit not found (history rewritten?)")
    elif head_same is False:
        score -= 20
        breakdown.append("-20 HEAD moved since checkpoint")
    if branch_same is False:
        score -= 10
        breakdown.append("-10 branch changed since checkpoint")

    tracked_bad = [
        row
        for row in file_rows
        if row["verdict"] in ("changed", "missing")
        and ({"staged", "unstaged", "conflict"} & set(row["states"]))
    ]
    untracked_bad = [
        row
        for row in file_rows
        if row["verdict"] in ("changed", "missing") and set(row["states"]) == {"untracked"}
    ]
    for row in tracked_bad[:3]:
        breakdown.append(f"-10 tracked file {row['verdict']}: {row['path']}")
    if len(tracked_bad) > 3:
        breakdown.append(f"    (+{len(tracked_bad) - 3} more tracked files affected)")
    for row in untracked_bad[:2]:
        breakdown.append(f"-10 untracked file {row['verdict']}: {row['path']}")
    if len(untracked_bad) > 2:
        breakdown.append(f"    (+{len(untracked_bad) - 2} more untracked files affected)")
    score -= 10 * min(len(tracked_bad), 3)
    score -= 10 * min(len(untracked_bad), 2)

    if drift and tests_present:
        score -= 15
        breakdown.append("-15 recorded test results are stale (repository drifted after they ran)")
    if not tests_present:
        score -= 10
        breakdown.append("-10 no execution evidence recorded (no tests were run at checkpoint)")

    return max(0, min(100, score)), breakdown
