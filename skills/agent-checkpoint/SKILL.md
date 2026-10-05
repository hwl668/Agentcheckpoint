---
name: agent-checkpoint
description: Save verifiable, restorable checkpoints of coding-agent work with the agentck CLI. Use when completing a unit of work, before a risky change, when a milestone is reached, or when handing work over to another agent (Claude, Codex, GLM, ...). Also use when resuming work that a previous agent checkpointed.
---

# AgentCheckpoint skill

AgentCheckpoint (`agentck`) freezes the real working state of an agent
session and proves to the next agent whether that state is still valid.
Its core rule binds YOU:

> Machine-observed facts and agent-reported claims are stored separately.
> Never present a claim as a verified fact.

## When to checkpoint

- After completing a coherent unit of work (a fix, a refactor step).
- Immediately BEFORE a risky change, so it can be restored.
- When you are about to hand work to another agent or end your session.
- When the user asks to "checkpoint", "save progress", or "hand off".

## How to save

Requirements and decisions go through flags — they are stored as
agent-reported claims, never as facts:

```bash
agentck save <short-label> \
    --agent glm \
    --goal "What this work is trying to achieve" \
    --completed "One concrete claim per flag" \
    --decision "Why you chose this approach" \
    --constraint "Any constraint you must respect" \
    --blocker "What is currently blocking you, if anything" \
    --next "The single most useful next action" \
    --do-not "Files or areas that must not be touched" \
    --test "pytest tests/test_cache.py"
```

Rules:

1. **Git state is collected for you.** Never describe the repo state in
   claims — `agentck` records HEAD, diffs, and untracked files itself.
2. **Evidence beats claims.** If you say work is complete, back it with
   `--test CMD` so the exit code is recorded as machine-observed fact. Do
   not write "tests pass" as a claim unless you ran them via `--test` or in
   the session.
3. `--completed` items must be specific and falsifiable ("switched eviction
   policy to LRU in src/cache.py"), not vague ("made some changes").
4. For longer context, write the semantic JSON (fields: agent, goal, status,
   completed, decisions, constraints, blockers, next_steps, do_not, tests —
   unknown keys are rejected) and run `agentck save <label> --semantic file.json`.
5. Forking two lines of work from one point: `agentck save <label> --parent <ref>`.

## How to resume work another agent checkpointed

```bash
agentck verify          # drift, staleness, integrity, resume confidence
agentck resume codex    # or claude / glm / plain — evidence-tagged handoff
```

- Treat `[OBSERVED]` and `[VERIFIED]` as ground truth.
- Treat `[AGENT-REPORTED]` as claims: re-verify anything you build on.
- Respect the "Do not touch" list.
- If `verify` reports drift or stale tests, tell the user before continuing.

## Restore (ask first)

`agentck restore <ref>` restores into a NEW git worktree — safe, non-destructive.
`agentck restore <ref> --in-place --yes` rewrites the current tree (a safety
checkpoint is saved first). Only run in-place restore when the user explicitly
asked to reset their working tree.

## Useful reads

```bash
agentck list      # all checkpoints
agentck log       # checkpoint DAG as a tree (forks visible)
agentck show latest
agentck diff <ref-a> <ref-b>
agentck replay    # re-run the recorded --test commands, compare results
```
