"""Store-level behavior: init, ids, references, config."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agentcheckpoint import store as store_mod
from agentcheckpoint.errors import CheckpointError


def test_init_creates_store(run_ck, git_repo):
    code, out, _ = run_ck("init")
    assert code == 0
    store = git_repo.root / ".agentcheckpoint"
    assert (store / "config.toml").is_file()
    assert (store / "checkpoints").is_dir()
    assert "Initialized AgentCheckpoint store" in out
    # .agentcheckpoint must be locally excluded so the tool never pollutes git status
    exclude = (git_repo.root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert ".agentcheckpoint/" in exclude


def test_init_is_idempotent(run_ck, git_repo):
    code1, _, _ = run_ck("init")
    code2, out2, _ = run_ck("init")
    assert (code1, code2) == (0, 0)
    assert "already initialized" in out2


def test_init_outside_repo_fails_safely(run_ck, tmp_path):
    code, _, err = run_ck("init", cwd=tmp_path)
    assert code == 2
    assert "not a git repository" in err


def test_save_without_init_hints_at_init(run_ck, git_repo):
    code, _, err = run_ck("save")
    assert code == 2
    assert "agentck init" in err


def test_new_checkpoint_id_is_unique_within_the_same_second(tmp_path):
    store = tmp_path / ".agentcheckpoint"
    (store / "checkpoints").mkdir(parents=True)
    now = datetime(2026, 10, 4, 23, 15, 1, tzinfo=timezone.utc)
    first = store_mod.new_checkpoint_id(store, now)
    assert first == "cp_20261004_231501"
    # mirror what save_checkpoint does: the returned id becomes a directory on disk
    (store / "checkpoints" / first).mkdir()
    second = store_mod.new_checkpoint_id(store, now)
    assert second == "cp_20261004_231501_1"


def test_resolve_ref_supports_latest_prefix_and_label(run_ck, git_repo, tmp_path):
    # deterministic store with hand-built checkpoints (ids in different months)
    store = tmp_path / "dstore"
    (store / "checkpoints" / "cp_20200101_000001").mkdir(parents=True)
    (store / "checkpoints" / "cp_20200101_000001" / "manifest.json").write_text(
        json.dumps({"id": "cp_20200101_000001", "label": "alpha-label"}), encoding="utf-8"
    )
    (store / "checkpoints" / "cp_20200202_000002").mkdir()
    (store / "checkpoints" / "cp_20200202_000002" / "manifest.json").write_text(
        json.dumps({"id": "cp_20200202_000002", "label": "beta-label"}), encoding="utf-8"
    )

    assert store_mod.resolve_ref(store, "latest").name == "cp_20200202_000002"
    assert store_mod.resolve_ref(store, "cp_20200101_000001").name == "cp_20200101_000001"
    assert store_mod.resolve_ref(store, "cp_20200101").name == "cp_20200101_000001"
    assert store_mod.resolve_ref(store, "alpha-label").name == "cp_20200101_000001"
    assert store_mod.resolve_ref(store, "beta-label").name == "cp_20200202_000002"
    # label collisions resolve to the newest matching checkpoint
    (store / "checkpoints" / "cp_20200303_000003").mkdir()
    (store / "checkpoints" / "cp_20200303_000003" / "manifest.json").write_text(
        json.dumps({"id": "cp_20200303_000003", "label": "alpha-label"}), encoding="utf-8"
    )
    assert store_mod.resolve_ref(store, "alpha-label").name == "cp_20200303_000003"

    with pytest.raises(CheckpointError):
        store_mod.resolve_ref(store, "no-such-ref")
    with pytest.raises(CheckpointError):
        store_mod.resolve_ref(store, "cp_2020")  # ambiguous prefix


def test_resolve_ref_with_same_second_suffix(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "first")
    run_ck("save", "second")
    store = git_repo.root / ".agentcheckpoint"
    dirs = store_mod.existing_checkpoint_dirs(store)
    assert store_mod.resolve_ref(store, "latest") == dirs[-1]


def test_index_jsonl_is_appended(run_ck, git_repo):
    run_ck("init")
    run_ck("save", "idx-test", "--agent", "glm", "--goal", "check index")
    entries = store_mod.read_index(git_repo.root / ".agentcheckpoint")
    assert len(entries) == 1
    assert entries[0]["label"] == "idx-test"
    assert entries[0]["agent"] == "glm"
    assert entries[0]["goal"] == "check index"
