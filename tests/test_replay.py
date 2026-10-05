"""`agentck replay`: re-run recorded commands and compare with recorded results."""

from __future__ import annotations


def _save_with_test(run_ck, git_repo, command: str, label: str = "cp") -> str:
    code, out, _ = run_ck("save", label, "--test", command)
    assert code == 0, out
    return out.split("Checkpoint saved: ")[1].split()[0]


def test_replay_with_no_recorded_commands(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "empty")
    code, out, _ = run_ck("replay")
    assert code == 0
    assert "no recorded commands" in out


def test_replay_consistent_results(run_ck, git_repo):
    run_ck("init")
    ref = _save_with_test(run_ck, git_repo, "git diff --quiet")  # fixture tree is clean
    code, out, _ = run_ck("replay", ref)
    assert code == 0
    assert "recorded PASS → replayed PASS — consistent" in out
    assert "1/1 consistent" in out


def test_replay_detects_regression(run_ck, git_repo):
    run_ck("init")
    ref = _save_with_test(run_ck, git_repo, "git diff --quiet", "was-clean")
    # drift: the command that passed at checkpoint time now fails
    git_repo.write("src/util.py", "modified after checkpoint\n")
    code, out, _ = run_ck("replay", ref)
    assert code == 1
    assert "REGRESSION since checkpoint" in out
    assert "0/1 consistent, 1 regression(s)" in out


def test_replay_detects_improvement_and_stable_failure(run_ck, git_repo):
    run_ck("init")
    ref = _save_with_test(run_ck, git_repo, "git rev-parse --verify ghost-ref", "was-broken")
    code, out, _ = run_ck("replay", ref)
    assert code == 0  # a stable failure is not a regression
    assert "recorded FAIL" in out and "— consistent" in out

    git_repo.git("branch", "ghost-ref")
    code, out, _ = run_ck("replay", ref)
    assert code == 0
    assert "improved since checkpoint" in out
    assert "0 regressions" in out or "0 regression(s)" in out


def test_replay_json_shape(run_ck, git_repo):
    import json

    run_ck("init")
    ref = _save_with_test(run_ck, git_repo, "git diff --quiet")
    code, out, _ = run_ck("replay", ref, "--json")
    assert code == 0
    report = json.loads(out)
    assert report["id"] == ref
    assert report["commands_total"] == 1
    assert report["results"][0]["verdict"] == "consistent"
    assert report["exit_hint"] == 0


def test_replay_unknown_ref_fails(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "cp")
    code, _, err = run_ck("replay", "cp_19990101_000000")
    assert code == 2
    assert "no checkpoint matches" in err
