"""`agentck diff` between checkpoints."""

from __future__ import annotations

import json

from agentcheckpoint import store as store_mod


def _latest(git_repo):
    return store_mod.latest_checkpoint(git_repo.root / ".agentcheckpoint")


def test_diff_reports_file_and_claim_changes(run_ck, git_repo):
    run_ck("init")
    git_repo.write("src/util.py", "v1\n")
    run_ck("save", "cp-a", "--goal", "phase one", "--completed", "set up tests")

    # leave both changes uncommitted so they are part of cp-b's observed set
    git_repo.write("src/util.py", "v2\n")
    git_repo.write("new_module.py", "fresh\n")
    run_ck("save", "cp-b", "--goal", "phase two", "--next", "write docs")

    code, out, _ = run_ck("diff", "cp-a", "cp-b")
    assert code == 0
    first_line = out.splitlines()[0]
    assert " → " in first_line  # "<id-a> → <id-b>"
    assert "goal: phase one → phase two (changed)" in out
    assert "+ new_module.py" in out
    assert "~ src/util.py (content changed)" in out
    assert '+ "write docs"' in out
    assert '- "set up tests"' in out


def test_diff_json_shape(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "one")
    git_repo.write("x.txt", "x\n")
    git_repo.commit_all("add x")
    run_ck("save", "two")
    # diff has no --json flag; use the library directly
    from agentcheckpoint.checkpoint.diff import diff_checkpoints
    from agentcheckpoint.checkpoint.load import load_manifest

    dirs = store_mod.existing_checkpoint_dirs(git_repo.root / ".agentcheckpoint")
    diff = diff_checkpoints(load_manifest(dirs[0]), load_manifest(dirs[1]))
    assert diff["head_changed"] is True
    # both checkpoints were taken on clean trees, so no observed-file delta
    assert diff["files"] == {"added": [], "removed": [], "changed": []}
    json.dumps(diff)  # must be JSON-serializable


def test_diff_with_unresolvable_ref_fails(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "only")
    code, _, err = run_ck("diff", "only", "ghost")
    assert code == 2
    assert "no checkpoint matches" in err
