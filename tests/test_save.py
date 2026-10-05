"""`agentck save`: manifest content, artifacts, integrity, semantic inputs."""

from __future__ import annotations

import json

from agentcheckpoint import store as store_mod
from agentcheckpoint.checkpoint.load import integrity_check, load_manifest


def _latest(git_repo):
    return store_mod.latest_checkpoint(git_repo.root / ".agentcheckpoint")


def test_save_records_full_state(run_ck, git_repo):
    run_ck("init")
    git_repo.write("src/util.py", "modified\n")
    git_repo.write("staged.txt", "staged\n")
    git_repo.git("add", "staged.txt")
    git_repo.write("untracked.txt", "untracked\n")

    code, out, _ = run_ck("save", "before-refactor", "--agent", "glm", "--goal", "Fix cache leak")
    assert code == 0
    assert "Checkpoint saved:" in out
    assert "1 staged, 1 unstaged, 1 untracked" in out

    cp_dir = _latest(git_repo)
    m = load_manifest(cp_dir)
    assert m.label == "before-refactor"
    assert m.source_agent == "glm"
    assert m.goal == "Fix cache leak"
    assert m.status == "in_progress"
    assert m.parent is None
    assert m.branch == "main"
    assert m.head == git_repo.head()

    obs = m.data["observed"]
    assert obs["staged_files"] == ["staged.txt"]
    assert obs["unstaged_files"] == ["src/util.py"]
    assert obs["untracked_files"] == ["untracked.txt"]
    assert sorted(obs["modified_files"]) == ["src/util.py", "staged.txt", "untracked.txt"]

    assert (cp_dir / "git" / "staged.patch").read_bytes()
    assert (cp_dir / "git" / "tracked.patch").read_bytes()
    assert (cp_dir / "git" / "status.json").is_file()
    stored = (cp_dir / "git" / "untracked" / "untracked.txt").read_text(encoding="utf-8")
    assert stored == "untracked\n"
    assert (cp_dir / "handoff.md").is_file()
    assert (cp_dir / "semantic" / "next-steps.md").is_file()


def test_save_integrity_covers_all_artifacts(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "integ", "--goal", "g")
    cp_dir = _latest(git_repo)
    report = integrity_check(cp_dir)
    assert report["ok"] is True
    assert report["checked"] >= 4  # manifest, handoff, status.json, patches, ...

    # any tampering must be detected
    status_path = cp_dir / "git" / "status.json"
    data = json.loads(status_path.read_text(encoding="utf-8"))
    data["tampered"] = True
    status_path.write_text(json.dumps(data), encoding="utf-8")
    tampered = integrity_check(cp_dir)
    assert tampered["ok"] is False
    assert any("status.json" in p for p in tampered["problems"])


def test_save_parent_chain(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "first")
    run_ck("save", "second")
    first, second = [
        load_manifest(d) for d in store_mod.existing_checkpoint_dirs(
            git_repo.root / ".agentcheckpoint"
        )
    ]
    assert first.parent is None
    assert second.parent == first.id


def test_save_semantic_flags_populate_claims(run_ck, git_repo):
    run_ck("init")
    code, _, _ = run_ck(
        "save", "claims",
        "--goal", "Fix CUDA memory leak",
        "--completed", "changed eviction policy",
        "--decision", "preserve public Cache API",
        "--constraint", "python 3.10 only",
        "--blocker", "test_large_batch fails",
        "--next", "investigate test_large_batch",
        "--do-not", "modify allocator.cpp",
    )
    assert code == 0
    m = load_manifest(_latest(git_repo))
    assert m.completed == ["changed eviction policy"]
    assert m.data["agent_claims"]["decisions"] == ["preserve public Cache API"]
    assert m.data["agent_claims"]["constraints"] == ["python 3.10 only"]
    assert m.data["agent_claims"]["blockers"] == ["test_large_batch fails"]
    assert m.next == ["investigate test_large_batch"]
    assert m.do_not == ["modify allocator.cpp"]


def test_save_semantic_file_and_flag_merge(run_ck, git_repo, tmp_path):
    semantic = tmp_path / "handoff.json"
    semantic.write_text(
        json.dumps(
            {
                "agent": "claude",
                "goal": "file goal",
                "completed": ["file completed item"],
                "next_steps": ["file next step"],
                "tests": ["git rev-parse --verify HEAD"],
            }
        ),
        encoding="utf-8",
    )
    run_ck("init")
    code, _, _ = run_ck(
        "save", "semfile", "--semantic", str(semantic),
        "--goal", "flag goal", "--next", "flag next step",
    )
    assert code == 0
    m = load_manifest(_latest(git_repo))
    # scalar: flag wins; lists: merged, file first
    assert m.goal == "flag goal"
    assert m.source_agent == "claude"
    assert m.completed == ["file completed item"]
    assert m.next == ["file next step", "flag next step"]
    # tests from the semantic file are executed and recorded as machine-observed facts
    tests = m.tests
    assert len(tests) == 1
    assert tests[0]["command"] == "git rev-parse --verify HEAD"
    assert tests[0]["exit_code"] == 0
    assert (m.path.parent / "execution" / "tests.json").is_file()


def test_save_records_failing_test_exit_code(run_ck, git_repo):
    run_ck("init")
    code, _, _ = run_ck(
        "save", "failing",
        "--test", "git rev-parse --verify definitely-not-a-real-ref",
    )
    assert code == 0
    m = load_manifest(_latest(git_repo))
    assert m.tests[0]["exit_code"] != 0


def test_save_rejects_unknown_semantic_fields(run_ck, git_repo, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"goal": "x", "summery": "typo"}), encoding="utf-8")
    run_ck("init")
    code, _, err = run_ck("save", "--semantic", str(bad))
    assert code == 2
    assert "unknown semantic field" in err


def test_save_redacts_secrets_in_semantic_input(run_ck, git_repo):
    run_ck("init")
    code, _, _ = run_ck("save", "secret", "--goal", "use key sk-abcdefghijklmnopqrstuvwx")
    assert code == 0
    m = load_manifest(_latest(git_repo))
    assert m.goal == "use key [REDACTED:openai-style-key]"
    assert "sk-abcdefghijklmnopqrstuvwx" not in json.dumps(m.data)


def test_save_fails_safely_outside_repo(run_ck, tmp_path):
    code, _, err = run_ck("save", "nope", cwd=tmp_path)
    assert code == 2
    assert "not a git repository" in err


def test_save_works_in_subdirectory(run_ck, git_repo):
    run_ck("init")
    deep = git_repo.root / "src" / "nested"
    deep.mkdir(parents=True)
    code, _, _ = run_ck("save", "from-subdir", cwd=deep)
    assert code == 0
    m = load_manifest(_latest(git_repo))
    assert m.repo_root.endswith("repo")


def test_save_on_unborn_repo(run_ck, tmp_path, env):
    import subprocess

    root = tmp_path / "unborn"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    monkey_code, out, err = run_ck("init", cwd=root)
    assert monkey_code == 0
    monkey_code, out, err = run_ck("save", "no-commits-yet", cwd=root)
    assert monkey_code == 0, err
