# AgentCheckpoint

**A verifiable, restorable execution checkpoint protocol for coding agents.**

![agentck demo](docs/demo.gif)

`agentck` freezes the real working state of a coding-agent session — git
state, executed test evidence, and the agent's own claims, stored
*separately* — and proves to the next agent (Claude, Codex, GLM, …) whether
that state is still valid before it builds on it.

```text
Agent summary  ≠  Ground truth
```

Handoff tools summarize. AgentCheckpoint also answers the questions a summary
cannot: *did the code drift since those tests passed?*, *is that "done"
claim backed by anything?*, *can I put the repo back exactly the way it was?*

## Install

Install **once, globally** — after that `agentck` works from any directory,
and checkpoint data always stays inside whatever repo you are standing in.

From a source checkout (recommended while the project is pre-PyPI):

```bash
git clone <repo> AgentCheckpoint
cd AgentCheckpoint

# one-time helper, if you do not have pipx yet:
py -3 -m pip install --user pipx        # POSIX: python3 -m pip install --user pipx

# install the CLI globally (editable: source changes take effect immediately):
py -3 -m pipx install -e .
py -3 -m pipx ensurepath                # add ~/.local/bin to PATH, once
```

Open a new terminal (or `source ~/.bashrc`), then:

```bash
cd ~/projects/any-project
agentck --version
agentck init
agentck save my-first-checkpoint --goal "..."
```

Alternatives:

```bash
pipx install agentck                # once published to PyPI (distribution name)
uv tool install agentck             # uv users
py -3 -m pip install --user .       # plain pip, no venv isolation
```

> Naming note: the PyPI distribution is **`agentck`** (`agentcheckpoint` is
> taken by an unrelated MCP server); the Python package still imports as
> `agentcheckpoint`, and the command is `agentck`.

The CLI is global; the data is per-project. Each repository gets its own
`.agentcheckpoint/` store (excluded locally via `.git/info/exclude`), and
stores never see each other. Outside a git repository every command fails
safely with exit code 2.

## Development

## Quickstart

```bash
cd my-project
agentck init
```

Work with your agent, then freeze the state:

```bash
agentck save glm-cache-refactor \
    --agent glm \
    --goal "Fix CUDA memory leak" \
    --completed "switched eviction policy to LRU" \
    --decision "preserve public Cache API" \
    --blocker "test_large_batch fails with stale references" \
    --next "inspect Cache.evict() around line 184" \
    --do-not "modify allocator.cpp" \
    --test "git rev-parse --verify HEAD"
```

`--test` commands are actually executed at save time; their exit codes and
output tails are recorded as machine-observed evidence.

### What a checkpoint contains

```text
.agentcheckpoint/checkpoints/cp_20261004_231501/
├── manifest.json        # the checkpoint (schema agent-checkpoint/v1)
├── handoff.md           # static handoff rendered at save time
├── integrity.json       # sha256 of every artifact — tamper-evident
├── git/                 # OBSERVED: status.json, staged.patch, tracked.patch, untracked/
├── execution/           # OBSERVED: tests.json (commands, exit codes, tails)
└── semantic/            # AGENT-REPORTED: decisions.md, constraints.md, next-steps.md
```

Git facts always come from `git` itself, never from the model, so
hallucination cannot pollute the ground-truth layer.

## Verify before you trust

```text
$ agentck verify

Checkpoint cp_20261004_161741 (label: glm-cache-refactor)
Created 2026-10-04T16:17:41Z — source agent: glm

Integrity
✓ 10 artifacts match recorded hashes

Repository
✓ same repository
✓ branch unchanged (main)
✓ HEAD unchanged (c3e654351b9d)

Files
! src_cache.py changed since checkpoint
✓ test_cache.py unchanged

Tests
! git rev-parse --verify HEAD
  PASS at checkpoint — result is now STALE (repository drifted after this command ran)

Claims
? "switched eviction policy to LRU"
  agent-reported, not independently verified

Resume confidence: 75%
  -10 tracked file changed: src_cache.py
  -15 recorded test results are stale (repository drifted after they ran)
```

Exit codes make it scriptable: `0` = no drift, `1` = drift detected,
`2` = error.

## Hand off to the next agent

```bash
agentck resume codex > HANDOFF.md      # also: claude, glm, plain
```

```markdown
# AgentCheckpoint Resume
- Checkpoint: `cp_20261004_161741` (label: glm-cache-refactor)
- Resume confidence: **100%**

## Completed
[OBSERVED]
- src_cache.py (unstaged)
- test_cache.py (unstaged)

[AGENT-REPORTED]
- switched eviction policy to LRU

## Verification
- ✓ `git rev-parse --verify HEAD` — PASS at checkpoint; no drift since checkpoint; not re-run

Everything under [AGENT-REPORTED] is an unverified claim unless it was
independently reproduced below.
```

Each target adds the same body with a target-specific preamble. The evidence
tagging is the contract: `[OBSERVED]`/`[VERIFIED]` are tooling-recorded;
`[AGENT-REPORTED]` must be re-verified before it is built upon.

## Compare and restore

```bash
agentck list
agentck show latest
agentck diff cp_20261004_161741 cp_20261004_170201
agentck verify
```

Restore is safe by construction. The default creates a **new git worktree**
and never touches your current tree; hashes are re-verified after the restore:

```text
$ agentck restore cp_20261004_161741
Restored cp_20261004_161741 (mode: worktree)
  location: ../my-project-agentck-cp_20261004_161741
  untracked files restored: 1
  hash verification: 3/3 matched
```

In-place restore exists but is guarded: it refuses without `--yes` and always
writes an automatic `pre-restore-…` safety checkpoint first.

## Command reference

| Command | Purpose |
|---|---|
| `agentck init` | create `.agentcheckpoint/` (also excludes it locally via `.git/info/exclude`) |
| `agentck save [label] [--goal …] [--next …] [--do-not …] [--semantic file.json] [--test cmd] [--parent ref]` | freeze the current state; `--parent` forks from an earlier checkpoint |
| `agentck list [--json]` | all checkpoints |
| `agentck log` | the checkpoint DAG as a tree (forks and broken parent links visible) |
| `agentck show [ref] [--json]` | one checkpoint + its handoff document |
| `agentck diff <a> <b>` | what changed between two checkpoints |
| `agentck verify [ref] [--json]` | drift / staleness / integrity / confidence (exit 1 on drift) |
| `agentck replay [ref] [--json]` | re-run the recorded `--test` commands and compare results (exit 1 on regression) |
| `agentck resume [claude\|codex\|glm\|plain] [--output FILE]` | handoff document for the next agent |
| `agentck restore <ref> [--worktree(default) \| --in-place --yes]` | put the working state back |

References accept `latest`, an exact id, a unique id prefix, or a label.

## Design notes

- **Local-first, zero runtime dependencies.** Python ≥ 3.10 stdlib + git.
- **Ground truth is never LLM-generated.** Every git value is collected by
  running git.
- **Tamper-evident.** `verify`/`restore` re-hash all artifacts and refuse on
  mismatch — including files added behind their back.
- **Cross-platform byte fidelity.** git is driven with `core.autocrlf=false`
  during capture/restore so hashes survive round-trips on any OS config.
- **Model-agnostic.** The engine does not know what Claude is; agents
  integrate by emitting a semantic JSON file (protocol §4). A ready-made
  agent skill lives at [`skills/agent-checkpoint/SKILL.md`](skills/agent-checkpoint/SKILL.md)
  — it teaches an agent when to checkpoint and the evidence rules
  ("never claim tests pass unless recorded via `--test`").

## Status & roadmap

v0.2 implements the full `agent-checkpoint/v1` protocol (see
[spec/agent-checkpoint-v1.md](spec/agent-checkpoint-v1.md)), plus execution
replay and the checkpoint DAG. See [CHANGELOG.md](CHANGELOG.md) for history.
Next candidates: hook-driven command history, per-agent Skills packaging for
distribution, checkpoint quality score.

Limitations of v1, stated honestly: conflicted (unmerged) states are recorded
but not restorable; verify does not re-run test commands (use `agentck replay`);
redaction is best-effort, and patches are warned about rather than rewritten.

## Development

```bash
py -3 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/pytest          # 68 tests, hermetic temp git repositories
.venv/Scripts/ruff check .
```

See [SPEC.md](SPEC.md) for architecture and the agent working agreement.

## License

MIT
