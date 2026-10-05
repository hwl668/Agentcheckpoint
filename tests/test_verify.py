"""`agentck verify`: drift detection, test staleness, confidence, integrity."""

from __future__ import annotations

from agentcheckpoint import store as store_mod
from agentcheckpoint.checkpoint.load import load_manifest


def _latest(git_repo):
    return store_mod.latest_checkpoint(git_repo.root / ".agentcheckpoint")


def test_verify_no_drift_exit_0(run_ck, git_repo):
    run_ck("init")
    git_repo.write("src/util.py", "changed\n")
    run_ck("save", "v1", "--test", "git rev-parse --verify HEAD")
    code, out, _ = run_ck("verify")
    assert code == 0
    assert "Resume confidence: 100%" in out
    assert "no drift since checkpoint" in out


def test_verify_detects_file_drift_and_stale_tests(run_ck, git_repo):
    run_ck("init")
    git_repo.write("src/util.py", "original\n")
    run_ck("save", "v1", "--test", "git rev-parse --verify HEAD")
    git_repo.write("src/util.py", "drifted!\n")

    code, out, _ = run_ck("verify")
    assert code == 1
    assert "src/util.py changed since checkpoint" in out
    assert "STALE" in out
    assert "Resume confidence:" in out
    confidence_line = next(line for line in out.splitlines() if "Resume confidence" in line)
    percentage = int(confidence_line.split(":")[1].strip().rstrip("%"))
    assert 0 <= percentage < 100


def test_verify_detects_head_movement(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "v1", "--goal", "g")
    git_repo.write("new_file.txt", "new\n")
    git_repo.commit_all("move head")
    code, out, _ = run_ck("verify")
    assert code == 1
    assert "HEAD moved" in out


def test_verify_detects_untracked_drift(run_ck, git_repo):
    run_ck("init")
    git_repo.write("scratch.txt", "v1\n")
    run_ck("save", "v1")
    git_repo.write("scratch.txt", "v2\n")
    code, out, _ = run_ck("verify")
    assert code == 1
    assert "scratch.txt changed since checkpoint" in out


def test_verify_tampered_checkpoint_fails_hard(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "v1", "--goal", "g")
    cp_dir = _latest(git_repo)
    handoff = cp_dir / "handoff.md"
    handoff.write_text("tampered\n", encoding="utf-8")
    code, out, _ = run_ck("verify")
    assert code == 2
    assert "handoff.md" in out


def test_verify_missing_ref_is_an_error(run_ck, git_repo):
    run_ck("init")
    code, _, err = run_ck("verify", "cp_19990101_000000")
    assert code == 2
    assert "no checkpoint matches" in err


def test_verify_json_report_structure(run_ck, git_repo):
    import json

    run_ck("init")
    git_repo.write("f.txt", "content\n")
    run_ck("save", "v1", "--goal", "g", "--test", "git log -1")
    code, out, _ = run_ck("verify", "--json")
    assert code == 0
    report = json.loads(out)
    assert report["drift"] is False
    assert report["confidence"] == 100
    assert report["files_summary"]["unchanged"] == 1
    assert report["tests"][0]["verdict"] == "recorded"
    assert report["repository"]["same_path"] is True


def test_verify_without_tests_has_honest_lower_confidence(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "v1", "--goal", "g")
    code, out, _ = run_ck("verify")
    assert code == 0
    assert "-10 no execution evidence recorded" in out
    assert "Resume confidence: 90%" in out


def test_verify_confidence_formula_on_heavy_drift(run_ck, git_repo):
    run_ck("init")
    git_repo.write("a.txt", "a\n")
    git_repo.write("b.txt", "b\n")
    git_repo.write("c.txt", "c\n")
    git_repo.write("d.txt", "d\n")
    git_repo.commit_all("make the files tracked")
    # leave all four modified-but-unstaged at checkpoint time so they are observed
    for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
        git_repo.write(name, f"{name} checkpoint version\n")
    run_ck("save", "v1")
    for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
        git_repo.write(name, "drifted\n")
    code, out, _ = run_ck("verify")
    assert code == 1
    # 100 - 30 (4 tracked files, capped at 3) = 70; no tests recorded -> -10
    assert "Resume confidence: 60%" in out
    m = load_manifest(_latest(git_repo))
    assert m.id  # checkpoint itself remains readable
