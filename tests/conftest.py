"""Shared fixtures: hermetic git repos and an in-process CLI runner."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentcheckpoint import cli


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate git config so tests are hermetic and deterministic (LF, no gpg)."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n"
        "\tname = Test Agent\n"
        "\temail = test@example.com\n"
        "[init]\n"
        "\tdefaultBranch = main\n"
        "[core]\n"
        "\tautocrlf = false\n"
        "[commit]\n"
        "\tgpgsign = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    return tmp_path


class Repo:
    def __init__(self, root: Path):
        self.root = Path(root)

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["git", "-c", "core.autocrlf=false", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}"
            )
        return proc

    def write(self, rel: str, content: str) -> Path:
        path = self.root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        return path

    def write_bytes(self, rel: str, content: bytes) -> Path:
        path = self.root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def commit_all(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-m", message)

    def branch(self) -> str:
        return self.git("branch", "--show-current").stdout.strip()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def status(self) -> str:
        return self.git("status", "--porcelain").stdout


@pytest.fixture
def git_repo(env: Path, tmp_path: Path) -> Repo:
    root = tmp_path / "repo"
    root.mkdir()
    repo = Repo(root)
    repo.git("init", "-q")
    repo.write("README.md", "demo project\n")
    repo.write("src/util.py", "def add(a, b):\n    return a + b\n")
    repo.commit_all("initial commit")
    return repo


@pytest.fixture
def run_ck(git_repo: Repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture):
    def _run(*argv: str, cwd: Path | None = None) -> tuple[int, str, str]:
        monkeypatch.chdir(cwd or git_repo.root)
        code = cli.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run
