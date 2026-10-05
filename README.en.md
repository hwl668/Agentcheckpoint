<div align="center">

# 📌 AgentCheckpoint

**Verifiable, restorable execution checkpoints for coding agents**

`agentck` freezes the real working state of a coding-agent session — git
state, executed test evidence, and the agent's own claims (stored
*separately*) — and tells the next agent whether that state is still
trustworthy before it builds on it.

[![CI](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml/badge.svg)](https://github.com/hwl668/Agentcheckpoint/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agentck)](https://pypi.org/project/agentck/)
[![Python](https://img.shields.io/pypi/pyversions/agentck)](https://pypi.org/project/agentck/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[Install](#-install) · [Quickstart](#-quickstart) · [Commands](#-commands) · [How it works](#-how-it-works) · [Roadmap](#-roadmap)

[简体中文](README.md) · **English** · [日本語](README.ja.md) · [Español](README.es.md) · [Русский](README.ru.md)

<img src="docs/demo.gif" alt="agentck demo" width="820">

</div>

## 💡 Why

Handoff tools summarize. But a summary cannot answer three lethal questions:

- Since those tests passed, **has the code drifted?**
- That "it's done" claim — **is there evidence?**
- Can the repository be put back **exactly** the way it was?

AgentCheckpoint answers with one iron rule:

```text
Agent summary ≠ Ground truth
```

Every piece of information belongs to one of three classes, stored and
labelled separately, never conflated:

```text
CLAIM:      "fixed cache eviction"            ← agent-reported
OBSERVED:   src/cache.py modified             ← machine-collected (git)
VERIFIED:   pytest tests/test_cache.py → exit 0
STALE:      src/cache.py changed afterwards   ← marked stale on drift
```

So `agentck verify` hands you a verdict before you take over:

```text
Files
! src_cache.py changed since checkpoint
Tests
! git rev-parse --verify HEAD
  PASS at checkpoint — result is now STALE
Claims
? "switched eviction policy to LRU"
  agent-reported, not independently verified

Resume confidence: 75%
```

Exit codes are scriptable: `0` no drift · `1` drift · `2` error.

## ✨ Highlights

|  | Feature | What it means |
|---|---|---|
| 🔖 | **Evidence classes** | OBSERVED / VERIFIED / AGENT-REPORTED tagged end-to-end; claims are never rendered as facts |
| 🕵 | **Drift detection** | HEAD moved, branch changed, file hashes differ → recorded test results marked STALE |
| 🔐 | **Tamper-evident** | Every artifact hashed (SHA256); verify / restore re-hash everything and refuse on mismatch |
| 🔁 | **Execution replay** | Re-run commands recorded in a checkpoint: consistent / regression / improved |
| 🌳 | **Checkpoint DAG** | Fork from any node with `--parent`; `log` renders the tree |
| 🛟 | **Safe restore** | Creates a fresh git worktree by default, never touches your tree; in-place needs `--yes` and always saves a safety checkpoint first |
| 🤖 | **Model-agnostic** | The engine knows no specific agent; Claude / Codex / GLM are just different renderers |
| 📦 | **Local-first** | Zero runtime dependencies (Python ≥ 3.10 + git); data stays in the project; no accounts, no network, no LLM calls |

## 📦 Install

<details open>
<summary><b>Global install from source (recommended)</b></summary>

```bash
git clone https://github.com/hwl668/Agentcheckpoint.git
cd Agentcheckpoint

# one-time helper (if you do not have pipx yet):
py -3 -m pip install --user pipx          # POSIX: python3 -m pip install --user pipx

# install globally (editable: source changes take effect immediately):
py -3 -m pipx install -e .
py -3 -m pipx ensurepath                  # add ~/.local/bin to PATH, once
```

Open a new terminal:

```bash
cd ~/projects/any-project
agentck --version
agentck init
```

</details>

<details>
<summary><b>Alternatives</b></summary>

```bash
pipx install agentck                # once published to PyPI
uv tool install agentck             # uv users
py -3 -m pip install --user .       # plain pip, no venv isolation
```

> Naming note: the PyPI distribution is **`agentck`** (`agentcheckpoint` is
> taken by an unrelated project); the Python package still imports as
> `agentcheckpoint`, and the command is `agentck`.

</details>

**Global CLI, per-project data**: every repository gets its own
`.agentcheckpoint/` (locally excluded via `.git/info/exclude` — your
`.gitignore` is never touched), and stores never see each other. Outside a
git repository every command fails safely with exit code 2.

## 🚀 Quickstart

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
    --blocker "test_large_batch fails" \
    --next "inspect Cache.evict() around line 184" \
    --do-not "modify allocator.cpp" \
    --test "git rev-parse --verify HEAD"
```

`--test` commands are **actually executed**; their exit codes and output
tails are recorded as machine evidence. When handing over to another agent:

```bash
agentck verify            # is the state still trustworthy?
agentck resume codex > HANDOFF.md
```

Want to go back to a checkpoint you trust?

```bash
agentck restore cp_20261004_161741      # into a fresh worktree; current tree untouched
```

## 🧰 Commands

| Command | Purpose |
|---|---|
| `agentck init` | initialize `.agentcheckpoint/` (also excludes it locally) |
| `agentck save [label] [--goal …] [--test cmd] [--parent ref]` | freeze the current state; `--test` executes and records evidence |
| `agentck list [--json]` | all checkpoints |
| `agentck log` | the checkpoint DAG as a tree (forks and broken links visible) |
| `agentck show [ref] [--json]` | one checkpoint + its handoff document |
| `agentck diff <a> <b>` | what changed between two checkpoints |
| `agentck verify [ref] [--json]` | drift / staleness / integrity / confidence (exit 1 = drift) |
| `agentck replay [ref] [--json]` | re-run recorded commands and compare (exit 1 = regression) |
| `agentck resume [claude\|codex\|glm\|plain]` | evidence-tagged handoff document for the next agent |
| `agentck restore <ref>` | restore state (worktree by default; `--in-place --yes` rewrites the current tree) |

References accept `latest`, an exact id, a unique prefix, or a label.

## 🧠 How it works

Each checkpoint is a human-readable directory (schema
`agent-checkpoint/v1`):

<details>
<summary><b>Checkpoint layout</b></summary>

```text
.agentcheckpoint/checkpoints/cp_20261004_161741/
├── manifest.json        # the checkpoint (agent claims + machine observations)
├── handoff.md           # static handoff rendered at save time
├── integrity.json       # SHA256 of every artifact — tamper-evident
├── git/                 # OBSERVED: status.json, staged.patch, tracked.patch, untracked/
├── execution/           # OBSERVED: tests.json (commands, exit codes, tails)
└── semantic/            # AGENT-REPORTED: decisions.md, constraints.md, next-steps.md
```

</details>

Three hard rules:

1. **Git facts always come from git commands**, never from an LLM —
   hallucination cannot pollute the ground-truth layer.
2. **Claims and observations are stored separately**: goal / completed /
   decisions / blockers only go into `agent_claims`, always labelled
   "not independently verified".
3. **Checkpoints are append-only**: verify and restore re-hash everything;
   any tampering is caught.

The exact confidence heuristic, DAG and replay semantics are specified in
the [protocol spec (English)](spec/agent-checkpoint-v1.md).

## 🛡 Safety design and known limits

- Restore creates a fresh worktree by default; `--in-place` requires an
  explicit `--yes` and always writes an automatic `pre-restore-` safety
  checkpoint first.
- Checkout and patch application force `core.autocrlf=false`, so restored
  bytes match the hashes recorded at save time bit for bit.
- Semantic input and recorded output are **best-effort redacted** for
  secrets; suspected secrets in patches are warned about, never rewritten
  (rewriting would break integrity).
- Honest v1 limits: unmerged (conflicted) states are recorded but not
  restorable; verify does not re-run commands (use `agentck replay`);
  redaction is best-effort, not a guarantee.

## 🧭 Roadmap

- [x] Full `agent-checkpoint/v1` protocol (save / verify / resume / restore / diff)
- [x] Checkpoint DAG + execution replay
- [ ] Claude Code hooks for automatic checkpoints (session end / before risky actions)
- [ ] Distributable Skill packages per agent platform
- [ ] Checkpoint quality score

## 🤖 Agent integration

Make Claude / Codex / GLM use agentck properly: install
[`skills/agent-checkpoint/SKILL.md`](skills/agent-checkpoint/SKILL.md)
into your agent. It specifies when to checkpoint, that claims must be
specific and falsifiable, and the evidence discipline: *never claim tests
pass unless recorded via `--test`*.

## 💻 Development

```bash
py -3 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/pytest          # 68 tests, all on hermetic temporary git repos
.venv/Scripts/ruff check .
```

Deep dives (English): [SPEC.md](SPEC.md) · [protocol spec](spec/agent-checkpoint-v1.md) ·
[CHANGELOG](CHANGELOG.md)

---

<div align="center">

**MIT** © AgentCheckpoint contributors

Global CLI, per-project data.

</div>
