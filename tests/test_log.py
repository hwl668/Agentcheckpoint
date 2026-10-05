"""`agentck log` (checkpoint DAG) and `save --parent` (forks)."""

from __future__ import annotations

import json

from agentcheckpoint import store as store_mod
from agentcheckpoint.checkpoint.load import load_manifest


def test_log_renders_linear_chain(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "one", "--agent", "glm")
    run_ck("save", "two", "--agent", "codex")
    run_ck("save", "three", "--agent", "claude")
    code, out, _ = run_ck("log")
    assert code == 0
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 3
    assert not lines[0].startswith(("├─", "└─"))  # root has no connector
    assert lines[0].startswith("cp_") and "(one, glm" in lines[0]
    assert lines[1].startswith("└─ ")  # single child chain
    assert "(two, codex" in lines[1]


def test_save_with_explicit_parent_creates_fork(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "root")
    run_ck("save", "linear-child")
    code, _, err = run_ck("save", "fork-child", "--parent", "root")
    assert code == 0, err

    dirs = store_mod.existing_checkpoint_dirs(git_repo.root / ".agentcheckpoint")
    manifests = [load_manifest(d) for d in dirs]
    by_label = {m.label: m for m in manifests}
    assert by_label["linear-child"].parent == by_label["root"].id
    assert by_label["fork-child"].parent == by_label["root"].id
    assert by_label["root"].parent is None


def test_log_renders_fork_tree(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "root")
    run_ck("save", "left")
    run_ck("save", "right", "--parent", "root")
    code, out, _ = run_ck("log")
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("cp_") and "(root" in lines[0]
    assert any(line.startswith("├─ ") and "(left" in line for line in lines)
    assert any(line.startswith("└─ ") and "(right" in line for line in lines)


def test_log_flags_broken_parent_chain(run_ck, git_repo, tmp_path):
    run_ck("init")
    run_ck("save", "real")
    store = git_repo.root / ".agentcheckpoint"
    ghost = store / "checkpoints" / "cp_20990101_000000"
    ghost.mkdir()
    (ghost / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "agent-checkpoint/v1",
                "id": "cp_20990101_000001",
                "parent": "cp_20990101_000000",
                "created_at": "2099-01-01T00:00:00Z",
                "repo": {"branch": None, "head": None},
                "task": {},
                "observed": {},
                "agent_claims": {},
                "verification": {"tests": []},
                "next": [],
                "do_not": [],
            }
        ),
        encoding="utf-8",
    )
    code, out, _ = run_ck("log")
    assert code == 0
    assert "parent cp_20990101_000000 not found in this store" in out


def test_save_with_unknown_parent_fails(run_ck, git_repo):
    run_ck("init")
    code, _, err = run_ck("save", "orphan", "--parent", "cp_19990101_000000")
    assert code == 2
    assert "no checkpoint matches" in err
