"""Git collector: machine-observed state must match reality exactly."""

from __future__ import annotations

from agentcheckpoint.git import collector


def test_collect_captures_staged_unstaged_untracked(git_repo):
    git_repo.write("src/util.py", "def add(a, b):\n    return a + b  # changed\n")
    git_repo.write("staged_new.txt", "staged content\n")
    git_repo.git("add", "staged_new.txt")
    git_repo.write("notes/untouched.txt", "untracked\n")

    snap = collector.collect(git_repo.root)
    assert snap.branch == "main"
    assert [c.path for c in snap.staged] == ["staged_new.txt"]
    assert [c.path for c in snap.unstaged] == ["src/util.py"]
    assert "notes/untouched.txt" in snap.untracked

    paths = {f["path"]: f for f in snap.files}
    assert set(paths) == {"notes/untouched.txt", "src/util.py", "staged_new.txt"}
    assert set(paths["staged_new.txt"]["states"]) == {"staged"}
    assert set(paths["src/util.py"]["states"]) == {"unstaged"}
    assert set(paths["notes/untouched.txt"]["states"]) == {"untracked"}

    recorded = paths["src/util.py"]["sha256"]
    actual = __import__("hashlib").sha256(
        (git_repo.root / "src" / "util.py").read_bytes()
    ).hexdigest()
    assert recorded == actual

    assert b"staged content" in snap.staged_patch
    assert b"# changed" in snap.tracked_patch


def test_collect_clean_tree(git_repo):
    snap = collector.collect(git_repo.root)
    assert snap.is_clean
    assert snap.files == []
    assert snap.staged_patch == b""
    assert snap.tracked_patch == b""


def test_collect_unborn_repo(tmp_path, env):
    import subprocess

    root = tmp_path / "fresh"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=root, check=True, capture_output=True)
    snap = collector.collect(root)
    assert snap.head is None
    assert snap.branch == "main"
    # staged content diffs against the empty tree when HEAD does not exist yet
    assert [c.path for c in snap.staged] == ["seed.txt"]
    assert b"seed" in snap.staged_patch
    assert snap.untracked == []


def test_collect_rename_staged_records_new_path(git_repo):
    """Regression: git emits R entries as ORIGINAL path first, NEW path second
    (R100\\0a.txt\\0b.txt). The live (new) path must be the primary one."""
    git_repo.write("a.txt", "rename me\n")
    git_repo.commit_all("add a")
    git_repo.git("mv", "a.txt", "b.txt")

    snap = collector.collect(git_repo.root)
    assert [(c.path, c.code, c.orig_path) for c in snap.staged] == [
        ("b.txt", "R100", "a.txt")
    ]
    by_path = {f["path"]: f for f in snap.files}
    assert "b.txt" in by_path and "a.txt" not in by_path
    assert by_path["b.txt"]["sha256"] is not None


def test_collect_rename_with_further_edit(git_repo):
    git_repo.write("a.txt", "rename me\n")
    git_repo.commit_all("add a")
    git_repo.git("mv", "a.txt", "b.txt")
    git_repo.write("b.txt", "rename me\nplus an unstaged edit\n")

    snap = collector.collect(git_repo.root)
    assert [(c.path, c.code, c.orig_path) for c in snap.staged] == [
        ("b.txt", "R100", "a.txt")
    ]
    assert [c.path for c in snap.unstaged] == ["b.txt"]
    by_path = {f["path"]: f for f in snap.files}
    assert set(by_path) == {"b.txt"}
    assert set(by_path["b.txt"]["states"]) == {"staged", "unstaged"}


def test_collect_detects_binary_changes(git_repo):
    git_repo.write_bytes("blob.bin", b"\x00\x01\x02original")
    git_repo.commit_all("add binary")
    git_repo.write_bytes("blob.bin", b"\x00\x01\x02changed version")
    snap = collector.collect(git_repo.root)
    assert b"binary patch" in snap.tracked_patch or b"GIT binary patch" in snap.tracked_patch


def test_collect_reports_conflicts(git_repo):
    git_repo.write("conflict.txt", "base line\n")
    git_repo.commit_all("base")
    git_repo.git("checkout", "-q", "-b", "feature")
    git_repo.write("conflict.txt", "feature line\n")
    git_repo.commit_all("feature change")
    git_repo.git("checkout", "-q", "main")
    git_repo.write("conflict.txt", "main line\n")
    git_repo.commit_all("main change")
    git_repo.git("merge", "feature", check=False)

    snap = collector.collect(git_repo.root)
    assert "conflict.txt" in snap.conflicts
    git_repo.git("merge", "--abort")


def test_collect_handles_spaces_in_filenames(git_repo):
    git_repo.write("my file with space.txt", "content\n")
    git_repo.git("add", "my file with space.txt")
    snap = collector.collect(git_repo.root)
    assert [c.path for c in snap.staged] == ["my file with space.txt"]


def test_collect_excludes_agentcheckpoint_store(git_repo):
    store = git_repo.root / ".agentcheckpoint"
    store.mkdir()
    (store / "stray.txt").write_text("x", encoding="utf-8")
    snap = collector.collect(git_repo.root)
    assert snap.untracked == []
