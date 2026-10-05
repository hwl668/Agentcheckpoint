# SPEC.md — AgentCheckpoint

> **A verifiable, restorable execution checkpoint protocol for coding agents.**
>
> Not "summarize what the last agent said" — freeze the agent's real working
> state and prove to the next agent that the state it receives is still valid.

AgentCheckpoint is **not** a conversation summarizer or an AI memory tool. The
product thesis: cross-agent context transfer is the surface need; the real
problem is whether the transferred working state is *trustworthy* and
*restorable*. The normative protocol lives in
[`spec/agent-checkpoint-v1.md`](spec/agent-checkpoint-v1.md).

## Core principle

```text
Agent summary  ≠  Ground truth
```

A checkpoint separates three evidence classes everywhere — storage, reports,
handoff documents:

- **OBSERVED** — collected from tooling at checkpoint time (git HEAD, branch,
  diffs, untracked files, hashes). Always produced by running `git`, never by
  an LLM.
- **VERIFIED** — machine-checked and still true later (integrity re-hash,
  unchanged files, un-stale test results).
- **AGENT-REPORTED** — claims (goal, completed work, decisions, blockers,
  next steps, do-not-touch). Never rendered as facts.

```text
CLAIM:      "fixed cache eviction"        (source = glm)
OBSERVED:   src/cache.py modified
VERIFIED:   pytest tests/test_cache.py → exit 0
STALE:      src/cache.py changed after the test ran
```

## First-version scope

Shipped: `init`, `save`, `list`, `show`, `diff`, `verify`, `resume`,
`restore` (worktree by default, guarded in-place).

Deliberately cut: MCP, GUI, cloud sync, LLM API calls, chat-log parsing,
daemon processes, complex agent hooks.

## Architecture

```text
src/agentcheckpoint/
├── cli.py                  # argparse wiring, exit codes
├── schema.py               # agent-checkpoint/v1 manifest + strict semantic input
├── store.py                # .agentcheckpoint layout, ids, reference resolution
├── util.py, errors.py
├── git/
│   ├── collector.py        # machine-observed git state (the ground-truth layer)
│   ├── patch.py            # patch application (autocrlf-forced for byte fidelity)
│   └── restore.py          # worktree/checkout/untracked write-back primitives
├── checkpoint/
│   ├── create.py           # save: collect → run tests → manifest → integrity
│   ├── load.py             # manifest loading + integrity checking
│   ├── verify.py           # drift/staleness/confidence engine
│   ├── replay.py           # re-run recorded commands, compare verdicts
│   ├── diff.py             # manifest-level comparison
│   └── restore.py          # orchestration: safety checkpoint → patch → hash check
├── render/
│   ├── markdown.py         # evidence-tagged handoff/verify/diff documents
│   └── claude.py, codex.py, glm.py   # target-specific preambles
└── security/redact.py      # best-effort secret redaction + patch warnings
```

The bottom engine knows nothing about any specific agent. Claude/Codex/GLM
support is a *renderer* concern; their skills only need to emit the semantic
JSON from §4 of the protocol spec.

## Milestones

| Milestone | Scope | Status |
|---|---|---|
| M0 | CLI scaffold + schema + store | ✅ done |
| M1 | Deterministic git collector | ✅ done |
| M2 | `save` / `list` / `show` | ✅ done |
| M3 | Evidence-tagged markdown renderer + agent adapters | ✅ done |
| M4 | `verify` (drift/stale/confidence) + `diff` | ✅ done |
| M5 | Safe restore (worktree default, guarded in-place) | ✅ done |
| M6 | Claude/Codex/GLM adapters (preambles + semantic JSON contract) | ✅ basic (renderers; per-agent Skills live outside this repo) |
| M7 | Hooks + command/test history | 🔶 partial (`--test` execution recording + `replay` shipped; shell hooks deferred) |
| M8 | README/demo/release polish | ✅ docs shipped; release pending |

Beyond-plan items already shipped in v0.2: checkpoint DAG (`save --parent` +
`agentck log`, advanced item #3) and execution replay (`agentck replay`,
advanced item #5).

## Working agreement for agent contributors

When working on this repository with an LLM coding agent, give it this brief:

```text
You are implementing AgentCheckpoint, a CLI that creates verifiable and
restorable execution checkpoints for coding-agent sessions.

Core principle: machine-observed facts and agent-reported claims MUST be
stored separately. Machine-observed: git HEAD, branch, working-tree status,
staged/unstaged diffs, untracked files, executed commands, test exit codes,
timestamps, hashes. Agent-reported: goal, completed work, decisions,
constraints, blockers, next steps, do-not-touch. Never present
agent-reported claims as verified facts.

Read spec/agent-checkpoint-v1.md first. Implement only the milestone you are
given. Before changing code: inspect the repository, describe the files you
plan to modify, implement, add tests, run pytest + ruff, summarize exactly
what changed. Do not invent functionality outside the spec.

Hard requirements: Python >= 3.10, src layout, stdlib-only runtime, pytest
tests, cross-platform, no LLM APIs, local-first, never modify the user's
repository unexpectedly, restore must be safe, schema versioned, files
human-readable.
```

## Development

```bash
py -3 -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # POSIX: .venv/bin/pip
.venv/Scripts/pytest                       # 68 tests, hermetic temp git repos
.venv/Scripts/ruff check .
```

No runtime dependencies; dev deps are pytest + ruff only.
