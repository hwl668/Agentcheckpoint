"""Execution replay: re-run commands recorded at checkpoint time and compare.

Replay is what turns "tests passed at checkpoint" from a claim into something
that can be re-checked at any later moment. Recorded commands are the ones
the user provided via `--test` (or the semantic file), so replaying them
never executes anything the user did not originally ask to record.
"""

from __future__ import annotations

from pathlib import Path

from agentcheckpoint.checkpoint.create import _run_test_command
from agentcheckpoint.schema import Manifest


def replay_checkpoint(cp_dir: Path, manifest: Manifest, root: Path, config: dict) -> dict:
    results: list[dict] = []
    for recorded in manifest.tests:
        command = recorded.get("command", "")
        replayed = _run_test_command(command, root, config["limits"])
        was_code = recorded.get("exit_code")
        now_code = replayed["exit_code"]
        if now_code is None:
            verdict = "error"
        elif was_code == 0 and now_code != 0:
            verdict = "regression"
        elif was_code != 0 and now_code == 0:
            verdict = "improved"
        else:
            verdict = "consistent"
        results.append(
            {
                "command": command,
                "recorded_exit_code": was_code,
                "replayed_exit_code": now_code,
                "duration_ms": replayed["duration_ms"],
                "verdict": verdict,
                "stdout_tail": replayed["stdout_tail"],
                "stderr_tail": replayed["stderr_tail"],
            }
        )

    def count(verdict: str) -> int:
        return sum(1 for r in results if r["verdict"] == verdict)

    regressions, errors = count("regression"), count("error")
    exit_hint = 2 if errors else (1 if regressions else 0)
    return {
        "id": manifest.id,
        "label": manifest.label,
        "created_at": manifest.created_at,
        "commands_total": len(results),
        "results": results,
        "summary": {
            "consistent": count("consistent"),
            "regressions": regressions,
            "improved": count("improved"),
            "errors": errors,
        },
        "exit_hint": exit_hint,
    }
