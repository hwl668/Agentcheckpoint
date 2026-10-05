"""Compare two checkpoints at the manifest level."""

from __future__ import annotations

from agentcheckpoint.schema import Manifest


def diff_checkpoints(a: Manifest, b: Manifest) -> dict:
    files_a = {f["path"]: f for f in a.observed_files}
    files_b = {f["path"]: f for f in b.observed_files}
    added = sorted(set(files_b) - set(files_a))
    removed = sorted(set(files_a) - set(files_b))
    changed = sorted(
        path for path in set(files_a) & set(files_b)
        if files_a[path].get("sha256") != files_b[path].get("sha256")
    )

    completed_a, completed_b = a.completed, b.completed

    def list_delta(before: list[str], after: list[str]) -> dict:
        return {
            "added": [item for item in after if item not in before],
            "removed": [item for item in before if item not in after],
        }

    return {
        "a": {
            "id": a.id, "created_at": a.created_at,
            "branch": a.branch, "head": a.head, "goal": a.goal,
        },
        "b": {
            "id": b.id, "created_at": b.created_at,
            "branch": b.branch, "head": b.head, "goal": b.goal,
        },
        "branch_changed": a.branch != b.branch,
        "head_changed": a.head != b.head,
        "goal_changed": a.goal != b.goal,
        "files": {"added": added, "removed": removed, "changed": changed},
        "completed": list_delta(completed_a, completed_b),
        "next": list_delta(a.next, b.next),
        "do_not": list_delta(a.do_not, b.do_not),
    }
