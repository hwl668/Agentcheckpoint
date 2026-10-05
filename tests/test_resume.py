"""`agentck resume`: evidence-tagged handoff documents for each target."""

from __future__ import annotations

import json


def _prepare(git_repo, run_ck):
    run_ck("init")
    git_repo.write("src/util.py", "changed\n")
    run_ck(
        "save", "handoff-me", "--agent", "glm",
        "--goal", "Fix CUDA memory leak",
        "--completed", "changed cache eviction policy",
        "--decision", "preserve public Cache API",
        "--blocker", "test_large_batch fails",
        "--next", "inspect Cache.evict()",
        "--do-not", "modify allocator.cpp",
        "--test", "git rev-parse --verify HEAD",
    )


def test_resume_plain_document_structure(run_ck, git_repo):
    _prepare(git_repo, run_ck)
    code, out, _ = run_ck("resume")
    assert code == 0
    assert "# AgentCheckpoint Resume" in out
    assert "## Goal" in out and "Fix CUDA memory leak" in out
    assert "[OBSERVED]" in out and "- src/util.py (unstaged)" in out
    assert "[AGENT-REPORTED]" in out and "changed cache eviction policy" in out
    assert "## Decisions" in out and "preserve public Cache API" in out
    assert "## Do not touch" in out and "modify allocator.cpp" in out
    assert "## Current blocker" in out and "test_large_batch fails" in out
    assert "## Next Action" in out and "inspect Cache.evict()" in out
    assert "PASS" in out  # recorded test evidence
    assert "Resume confidence" in out


def test_resume_targets_change_preamble(run_ck, git_repo):
    _prepare(git_repo, run_ck)
    for target, marker in (("claude", "Claude Code"), ("codex", "Codex"), ("glm", "GLM")):
        code, out, _ = run_ck("resume", target)
        assert code == 0
        assert marker in out
        assert "[AGENT-REPORTED]" in out


def test_resume_by_label_and_prefix(run_ck, git_repo):
    _prepare(git_repo, run_ck)
    code, out, _ = run_ck("resume", "handoff-me")
    assert code == 0
    assert "handoff-me" in out
    code, out, _ = run_ck("resume", "cp_")  # with one checkpoint this prefix resolves
    assert code == 0


def test_resume_output_file(run_ck, git_repo):
    _prepare(git_repo, run_ck)
    target = git_repo.root / "HANDOFF.md"
    code, out, _ = run_ck("resume", "--checkpoint", "latest", "--target", "codex",
                          "--output", str(target))
    assert code == 0
    assert "Wrote handoff document" in out
    text = target.read_text(encoding="utf-8")
    assert "You are Codex" in text
    assert "# AgentCheckpoint Resume" in text


def test_resume_shows_drift(run_ck, git_repo):
    _prepare(git_repo, run_ck)
    git_repo.write("src/util.py", "drifted after checkpoint\n")
    code, out, _ = run_ck("resume", "--target", "plain")
    assert code == 0
    assert "Drift detected since checkpoint" in out
    assert "STALE" in out


def test_show_prints_handoff_and_json(run_ck, git_repo):
    import json

    _prepare(git_repo, run_ck)
    code, out, _ = run_ck("show", "latest")
    assert code == 0
    assert "# AgentCheckpoint Resume" in out

    code, out, _ = run_ck("show", "--json")
    assert code == 0
    manifest = json.loads(out)
    assert manifest["schema"] == "agent-checkpoint/v1"
    assert manifest["label"] == "handoff-me"


def test_list_table_and_json(run_ck, git_repo):
    _prepare(git_repo, run_ck)
    code, out, _ = run_ck("list")
    assert code == 0
    assert "ID" in out and "handoff-me" in out and "glm" in out

    code, out, _ = run_ck("list", "--json")
    assert code == 0
    rows = json.loads(out)
    assert len(rows) == 1
    assert rows[0]["goal"] == "Fix CUDA memory leak"
