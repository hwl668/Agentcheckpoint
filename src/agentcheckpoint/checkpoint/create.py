"""Create checkpoints: collect git state, run tests, persist artifacts + manifest."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

from agentcheckpoint import __version__, util
from agentcheckpoint import store as store_mod
from agentcheckpoint.checkpoint.load import build_integrity
from agentcheckpoint.git import collector
from agentcheckpoint.render.markdown import handoff_document
from agentcheckpoint.schema import SCHEMA_ID, SemanticData
from agentcheckpoint.security.redact import redact, scan_for_secrets


def save_checkpoint(
    root: Path,
    store_path: Path,
    *,
    label: str | None,
    semantic: SemanticData,
    config: dict,
    now: datetime | None = None,
    parent_id: str | None = None,
) -> tuple[str, Path, dict, list[str]]:
    """Write one checkpoint. Returns (id, checkpoint_dir, manifest_dict, warnings).

    ``parent_id`` records the checkpoint this work grew from; by default it is
    the latest checkpoint in the store. Passing an earlier checkpoint's id
    creates a fork (checkpoint DAG).
    """
    now = now or util.utc_now()
    cp_id = store_mod.new_checkpoint_id(store_path, now)
    if parent_id is None:
        parent_dir = store_mod.latest_checkpoint(store_path)
        parent_id = _read_id(parent_dir) if parent_dir else None
    limits = config["limits"]

    snap = collector.collect(root)
    semantic = _redact_semantic(semantic)

    cp_dir = store_mod.checkpoints_dir(store_path) / cp_id
    (cp_dir / "git").mkdir(parents=True, exist_ok=True)
    (cp_dir / "execution").mkdir(parents=True, exist_ok=True)
    (cp_dir / "semantic").mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []

    # --- git layer (machine-observed, never LLM-generated) -----------------
    util.write_bytes(cp_dir / "git" / "staged.patch", snap.staged_patch)
    util.write_bytes(cp_dir / "git" / "tracked.patch", snap.tracked_patch)
    for name, patch in (("staged.patch", snap.staged_patch), ("tracked.patch", snap.tracked_patch)):
        secret_names = scan_for_secrets(patch.decode("utf-8", errors="replace"))
        for secret_name in secret_names:
            warnings.append(
                f"{name} looks like it contains a {secret_name}; "
                "patches are stored verbatim — check before sharing this checkpoint"
            )
    util.write_text(
        cp_dir / "git" / "status.json",
        util.dump_json(
            {
                "branch": snap.branch,
                "detached": snap.detached,
                "head": snap.head,
                "head_subject": snap.head_subject,
                "head_committed_at": snap.head_committed_at,
                "staged": [c.to_dict() for c in snap.staged],
                "unstaged": [c.to_dict() for c in snap.unstaged],
                "untracked": list(snap.untracked),
                "conflicts": list(snap.conflicts),
                "clean": snap.is_clean,
            }
        ),
    )
    untracked_meta = _store_untracked(root, cp_dir, snap, limits)
    util.write_text(cp_dir / "git" / "untracked.json", util.dump_json({"files": untracked_meta}))

    # --- execution layer (machine-observed) --------------------------------
    test_records = [_run_test_command(cmd, root, limits) for cmd in semantic.tests]
    if test_records:
        util.write_text(
            cp_dir / "execution" / "tests.json", util.dump_json({"tests": test_records})
        )

    # --- semantic layer (agent-reported) ------------------------------------
    _write_semantic_markdown(cp_dir, semantic)

    # --- manifest ------------------------------------------------------------
    manifest = {
        "schema": SCHEMA_ID,
        "id": cp_id,
        "parent": parent_id,
        "label": label,
        "created_at": util.utc_now_iso(),
        "tool": {"name": "agentcheckpoint", "version": __version__},
        "source_agent": semantic.agent or "unknown",
        "repo": {
            "root": snap.root.as_posix(),
            "branch": snap.branch,
            "detached": snap.detached,
            "head": snap.head,
            "head_subject": snap.head_subject,
            "head_committed_at": snap.head_committed_at,
        },
        "task": {"goal": semantic.goal, "status": semantic.status or "in_progress"},
        "observed": {
            "clean": snap.is_clean,
            "files": snap.files,
            "modified_files": sorted(f["path"] for f in snap.files),
            "staged_files": [c.path for c in snap.staged],
            "unstaged_files": [c.path for c in snap.unstaged],
            "untracked_files": list(snap.untracked),
            "conflicts": list(snap.conflicts),
        },
        "agent_claims": semantic.to_claims(),
        "verification": {"tests": test_records},
        "next": list(semantic.next_steps),
        "do_not": list(semantic.do_not),
    }

    handoff = handoff_document(manifest, report=None, target="plain")
    util.write_text(cp_dir / "handoff.md", handoff)
    util.write_text(cp_dir / "manifest.json", util.dump_json(manifest))
    util.write_text(cp_dir / "integrity.json", util.dump_json(build_integrity(cp_dir)))

    store_mod.append_index(
        store_path,
        {
            "id": cp_id,
            "created_at": manifest["created_at"],
            "label": label,
            "agent": manifest["source_agent"],
            "status": manifest["task"]["status"],
            "goal": manifest["task"]["goal"],
            "branch": snap.branch,
            "head": snap.head,
        },
    )
    return cp_id, cp_dir, manifest, warnings


def _read_id(cp_dir: Path) -> str | None:
    import json

    try:
        data = json.loads((cp_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("id")
    return value if isinstance(value, str) else None


def _redact_semantic(semantic: SemanticData) -> SemanticData:
    def clean(value: str | None) -> str | None:
        return redact(value) if value else value

    return SemanticData(
        agent=clean(semantic.agent),
        goal=clean(semantic.goal),
        status=clean(semantic.status),
        completed=[redact(x) for x in semantic.completed],
        decisions=[redact(x) for x in semantic.decisions],
        constraints=[redact(x) for x in semantic.constraints],
        blockers=[redact(x) for x in semantic.blockers],
        next_steps=[redact(x) for x in semantic.next_steps],
        do_not=[redact(x) for x in semantic.do_not],
        tests=list(semantic.tests),  # commands are executed, not treated as secrets
        source=semantic.source,
    )


def _store_untracked(
    root: Path, cp_dir: Path, snap: collector.GitSnapshot, limits: dict
) -> list[dict]:
    """Copy untracked files into the checkpoint; record metadata for restore."""
    untracked_dir = cp_dir / "git" / "untracked"
    meta: list[dict] = []
    limit = limits["max_untracked_file_bytes"]
    by_path = {f["path"]: f for f in snap.files}
    for rel in snap.untracked:
        entry: dict = {"path": rel}
        file_info = by_path.get(rel, {})
        entry["bytes"], entry["sha256"] = file_info.get("bytes"), file_info.get("sha256")
        if entry["bytes"] is not None and entry["bytes"] > limit:
            entry.update(stored=False, note=f"skipped: exceeds max_untracked_file_bytes ({limit})")
            meta.append(entry)
            continue
        src = util.join_rel(root, rel)
        try:
            data = src.read_bytes()
        except OSError:
            entry.update(stored=False, note="unreadable at checkpoint time")
            meta.append(entry)
            continue
        dest = untracked_dir.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        entry.update(stored=True, bytes=len(data), sha256=util.sha256_hex(data))
        meta.append(entry)
    return meta


def _run_test_command(command: str, root: Path, limits: dict) -> dict:
    """Run one verification command now; record its exit code as machine-observed fact."""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            timeout=limits["test_timeout_seconds"],
        )
        exit_code: int | None = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
    duration_ms = int((time.monotonic() - started) * 1000)
    limit = limits["max_test_output_bytes"]
    stdout_tail, tail_out = util.decode_tail(stdout, limit)
    stderr_tail, tail_err = util.decode_tail(stderr, limit)
    return {
        "command": command,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout_tail": redact(stdout_tail),
        "stderr_tail": redact(stderr_tail),
        "truncated": tail_out or tail_err,
        "recorded_at": util.utc_now_iso(),
    }


def _write_semantic_markdown(cp_dir: Path, semantic: SemanticData) -> None:
    def bullets(items: list[str]) -> str:
        if not items:
            return "(none recorded)\n"
        return "".join(f"- {item}\n" for item in items)

    util.write_text(cp_dir / "semantic" / "decisions.md", bullets(semantic.decisions))
    util.write_text(cp_dir / "semantic" / "constraints.md", bullets(semantic.constraints))
    util.write_text(cp_dir / "semantic" / "next-steps.md", bullets(semantic.next_steps))
