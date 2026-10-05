"""`agentck restore`: worktree fidelity, in-place guard, safety checkpoint."""

from __future__ import annotations


def _build_rich_state(git_repo):
    """Committed base + staged new file + unstaged edit + nested untracked file."""
    git_repo.write("a.txt", "a v1\n")
    git_repo.commit_all("base")
    git_repo.write("a.txt", "a v1\na v2 unstaged edit\n")
    git_repo.write("b.txt", "b staged new file\n")
    git_repo.git("add", "b.txt")
    git_repo.write("u/nested.txt", "untracked nested\n")


def test_restore_worktree_reconstructs_exact_state(run_ck, git_repo, tmp_path):
    run_ck("init")
    _build_rich_state(git_repo)
    code, out, _ = run_ck("save", "rich", "--goal", "snapshot")
    assert code == 0
    ref = out.split("Checkpoint saved: ")[1].split()[0]

    # drift: commit everything plus an extra commit
    git_repo.commit_all("drift commit")
    git_repo.write("a.txt", "a drifted far away\n")
    git_repo.commit_all("more drift")

    code, out, _ = run_ck("restore", ref)
    assert code == 0
    assert "mode: worktree" in out
    assert "hash verification: 3/3 matched" in out

    worktree = tmp_path / f"repo-agentck-{ref}"
    assert worktree.is_dir()
    assert (worktree / "a.txt").read_text(encoding="utf-8") == "a v1\na v2 unstaged edit\n"
    assert (worktree / "u" / "nested.txt").read_text(encoding="utf-8") == "untracked nested\n"
    status = git_repo.git("-C", str(worktree), "status", "--porcelain").stdout
    assert "A  b.txt" in status       # staged new file restored into the index
    assert " M a.txt" in status       # unstaged edit restored as unstaged
    assert "?? u/" in status          # untracked file restored as untracked
    # original repo untouched
    assert "a drifted far away" in (git_repo.root / "a.txt").read_text(encoding="utf-8")


def test_restore_worktree_refuses_existing_target(run_ck, git_repo, tmp_path):
    run_ck("init")
    _build_rich_state(git_repo)
    code, out, _ = run_ck("save", "x")
    ref = out.split("Checkpoint saved: ")[1].split()[0]
    clash = tmp_path / f"repo-agentck-{ref}"
    clash.mkdir()
    code, _, err = run_ck("restore", ref)
    assert code == 2
    assert "already exists" in err


def test_restore_in_place_requires_explicit_yes(run_ck, git_repo):
    run_ck("init")
    _build_rich_state(git_repo)
    code, out, _ = run_ck("save", "cp")
    ref = out.split("Checkpoint saved: ")[1].split()[0]
    git_repo.commit_all("drift")
    code, _, err = run_ck("restore", ref, "--in-place")
    assert code == 2
    assert "--yes" in err
    # nothing was rewritten by the refused call
    assert git_repo.branch() == "main"


def test_restore_in_place_creates_safety_checkpoint(run_ck, git_repo):
    run_ck("init")
    _build_rich_state(git_repo)
    code, out, _ = run_ck("save", "cp")
    ref = out.split("Checkpoint saved: ")[1].split()[0]
    git_repo.commit_all("drift commit")

    code, out, _ = run_ck("restore", ref, "--in-place", "--yes")
    assert code == 0
    assert "mode: in_place" in out
    assert "safety checkpoint: cp_" in out

    status = git_repo.status()
    assert "A  b.txt" in status
    assert " M a.txt" in status
    assert "?? u/" in status
    assert (git_repo.root / "a.txt").read_text(encoding="utf-8") == "a v1\na v2 unstaged edit\n"

    # HEAD is detached at the checkpoint commit
    proc = git_repo.git("symbolic-ref", "-q", "HEAD", check=False)
    assert proc.returncode != 0

    # the pre-restore state is itself a checkpoint
    code, out, _ = run_ck("list")
    assert "pre-restore-" in out


def test_restore_refuses_tampered_checkpoint(run_ck, git_repo):
    run_ck("init")
    _build_rich_state(git_repo)
    code, out, _ = run_ck("save", "cp")
    ref = out.split("Checkpoint saved: ")[1].split()[0]
    cp_dir = git_repo.root / ".agentcheckpoint" / "checkpoints" / ref
    (cp_dir / "git" / "tracked.patch").write_bytes(b"tampered\n")
    code, _, err = run_ck("restore", ref)
    assert code == 2
    assert "integrity" in err


def test_restore_worktree_from_unborn_repo_fails_cleanly(run_ck, tmp_path, env, monkeypatch):
    import subprocess

    root = tmp_path / "unborn"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    assert run_ck("init", cwd=root)[0] == 0
    code, out, _ = run_ck("save", "no-head", cwd=root)
    assert code == 0

    from agentcheckpoint import store as store_mod

    ref = store_mod.latest_checkpoint(root / ".agentcheckpoint").name
    code, _, err = run_ck("restore", ref, cwd=root)
    assert code == 2
    assert "no commits" in err
