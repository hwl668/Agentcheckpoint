# Changelog

All notable changes to AgentCheckpoint are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/); versioning is SemVer.

## [Unreleased]

### Added

- CI workflow (ruff + pytest across Linux/macOS/Windows, Python 3.10–3.13) and
  a PyPI release workflow (Trusted Publishing, triggered by `v*` tags).
- Animated demo GIF rendered from real `agentck` output (`docs/demo.gif`).

### Changed

- Distribution renamed to **`agentck`** on PyPI (`agentcheckpoint` is taken
  there by an unrelated MCP server). The Python package still imports as
  `agentcheckpoint` and the CLI is still `agentck`.
- Documented the global install flow (`pipx install -e .` + `pipx ensurepath`,
  plus `uv tool install` / plain `pip` alternatives) and verified per-project
  store isolation on a real install.

## [0.2.0] - 2026-10-05

### Added

- `agentck replay [ref]`: re-run the commands recorded via `--test` at
  checkpoint time and compare exit codes — verdicts `consistent`,
  `regression`, `improved`, `error`; exit code 1 on any regression.
- Checkpoint DAG: `agentck save --parent <ref>` records a fork (work
  continuing from an earlier checkpoint instead of the latest one), and
  `agentck log` renders the parent/child history as a tree with orphan
  detection.
- `skills/agent-checkpoint/SKILL.md`: agent-facing skill instructing Claude
  Code / Codex / GLM when and how to checkpoint, including the
  evidence-rules ("never claim tests pass unless recorded via `--test`").
- MIT `LICENSE`.

## [0.1.0] - 2026-10-04

### Added

- `agent-checkpoint/v1` protocol implementation (see
  `spec/agent-checkpoint-v1.md`).
- `agentck init`: creates `.agentcheckpoint/` and excludes it locally via
  `.git/info/exclude`.
- `agentck save [label]`: deterministic git collection (HEAD, branch,
  staged/unstaged/untracked, binary-safe patches), untracked file copies,
  semantic claims via flags or strict `--semantic` JSON, `--test CMD`
  execution recording, sha256 integrity manifest.
- `agentck list` / `show` / `diff`: store inspection and manifest-level
  comparison.
- `agentck verify`: drift detection, test-result staleness, tamper-evidence,
  documented resume-confidence heuristic (exit 1 on drift).
- `agentck resume [plain|claude|codex|glm]`: evidence-tagged handoff documents
  (`[OBSERVED]` / `[VERIFIED]` / `[AGENT-REPORTED]`) with live drift section.
- `agentck restore`: worktree restore by default (never touches the current
  tree), guarded `--in-place --yes` with automatic `pre-restore-` safety
  checkpoint, post-restore hash verification, `core.autocrlf=false` for
  byte-faithful round-trips.
- Best-effort secret redaction for semantic input and recorded output; patch
  secrets warn instead of being rewritten.
- 57 tests on hermetic temporary git repositories.
