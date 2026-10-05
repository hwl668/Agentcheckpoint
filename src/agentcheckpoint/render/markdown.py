"""Markdown rendering: resume/handoff documents, verify reports, checkpoint diffs.

Evidence tagging is the point of this module: everything the reader sees is
labelled as [OBSERVED] (machine-collected), [VERIFIED] (machine-checked and
still true), or [AGENT-REPORTED] (a claim). Agent claims are never rendered
as facts.
"""

from __future__ import annotations

CHECK = "✓"
WARN = "!"
UNKNOWN = "?"
FAIL = "✗"

TARGETS = ("plain", "claude", "codex", "glm")


def _preamble(agent_name: str) -> str:
    return (
        f"You are {agent_name}, resuming work previously performed by another coding agent.\n"
        "How to read this document:\n"
        f"- Items tagged [OBSERVED] or [VERIFIED] were recorded by tooling and are ground truth.\n"
        f"- Items tagged [AGENT-REPORTED] are claims from the previous agent; re-verify anything\n"
        "  you intend to build on.\n"
        "- The 'Do not touch' list is binding.\n"
        "- Run `agentck verify` yourself if you need fresh drift information."
    )


_PREAMBLES: dict[str, str] = {
    "plain": "",
    "claude": _preamble("Claude Code"),
    "codex": _preamble("Codex"),
    "glm": _preamble("GLM"),
}


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- (none recorded)"]


def _short_head(head: str | None) -> str:
    return head[:12] if head else "(no commits)"


def handoff_document(manifest: dict, report: dict | None = None, target: str = "plain") -> str:
    """Render the full resume/handoff document.

    ``report`` (from verify_checkpoint) adds live drift/staleness/confidence;
    without it the document is the static snapshot written at save time.
    """
    m = manifest
    lines: list[str] = []
    add = lines.append

    preamble = _PREAMBLES.get(target, "")
    if preamble:
        add(preamble)
        add("")

    add("# AgentCheckpoint Resume")
    add("")
    label = m.get("label")
    add(f"- Checkpoint: `{m.get('id')}`" + (f" (label: {label})" if label else ""))
    add(f"- Schema: {m.get('schema')}")
    add(f"- Created: {m.get('created_at')}")
    add(f"- Source agent: {m.get('source_agent')}")
    if report is not None:
        add(f"- Resume confidence: **{report['confidence']}%**")
    add("")

    task = m.get("task", {})
    add("## Goal")
    add("")
    add(task.get("goal") or "(not recorded)")
    add("")
    add(f"Task status: {task.get('status') or 'in_progress'}")
    add("")

    repo = m.get("repo", {})
    observed = m.get("observed", {})
    add("## Repository State")
    add("")
    add(f"- Branch: {repo.get('branch') or '(detached)'}")
    subject = repo.get("head_subject")
    head_line = f"- HEAD: `{_short_head(repo.get('head'))}`"
    if subject:
        head_line += f" — {subject}"
    add(head_line)
    add(
        "- Working tree: "
        f"{len(observed.get('staged_files', []))} staged, "
        f"{len(observed.get('unstaged_files', []))} unstaged, "
        f"{len(observed.get('untracked_files', []))} untracked, "
        f"{len(observed.get('conflicts', []))} conflicts"
    )
    add("")

    add("## Completed")
    add("")
    add("[OBSERVED]")
    files = observed.get("files", []) or []
    if files:
        for entry in files:
            states = ", ".join(entry.get("states", []))
            add(f"- {entry['path']} ({states})")
    else:
        add("- (no file changes recorded)")
    add("")
    add("[AGENT-REPORTED]")
    lines.extend(_bullets(m.get("agent_claims", {}).get("completed", []) or []))
    add("")

    add("## Verification")
    add("")
    tests = m.get("verification", {}).get("tests", []) or []
    if not tests:
        add("No commands were executed at checkpoint time.")
    for test in tests:
        add(_test_line(test, report))
    add("")
    add(
        "Everything under [AGENT-REPORTED] is an unverified claim unless it was "
        "independently reproduced below."
    )
    add("")

    claims = m.get("agent_claims", {})
    add("## Decisions")
    add("")
    lines.extend(_bullets(claims.get("decisions", []) or []))
    add("")
    add("## Constraints")
    add("")
    lines.extend(_bullets(claims.get("constraints", []) or []))
    add("")
    add("## Do not touch")
    add("")
    lines.extend(_bullets(m.get("do_not", []) or []))
    add("")
    add("## Current blocker")
    add("")
    blockers = claims.get("blockers", []) or []
    lines.extend(_bullets(blockers))
    add("")

    add("## Important files")
    add("")
    if files:
        for entry in files[:20]:
            add(f"- {entry['path']}")
        if len(files) > 20:
            add(f"- … and {len(files) - 20} more")
    else:
        add("- (none recorded)")
    add("")

    add("## Next Action")
    add("")
    lines.extend(_bullets(m.get("next", []) or []))
    add("")

    add("## Drift")
    add("")
    if report is None:
        add("Drift information not computed at save time — run `agentck verify`.")
    else:
        repository = report["repository"]
        if not repository["accessible"]:
            add(f"- {WARN} repository state could not be inspected from the current location.")
        elif report["drift"]:
            add("Drift detected since checkpoint:")
            if repository["head"]["same"] is False:
                add(
                    f"  - HEAD moved: `{_short_head(repository['head']['recorded'])}` → "
                    f"`{_short_head(repository['head']['current'])}`"
                )
            for row in report["files"]:
                if row["verdict"] in ("changed", "missing"):
                    add(f"  - {row['verdict']}: {row['path']}")
        else:
            add("No repository drift detected.")
    add("")

    return "\n".join(lines).rstrip() + "\n"


def _test_line(test: dict, report: dict | None) -> str:
    command = test.get("command", "?")
    exit_code = test.get("exit_code")
    outcome = "PASS" if exit_code == 0 else f"FAIL (exit {exit_code})"
    if report is not None:
        for recorded in report["tests"]:
            if recorded["command"] == command:
                if recorded["verdict"] == "stale":
                    return (
                        f"- {WARN} `{command}` — {outcome} at checkpoint; "
                        "result is now **STALE** (repository drifted)"
                    )
                return (
                    f"- {CHECK} `{command}` — {outcome} at checkpoint; "
                    "no drift since checkpoint; not re-run"
                )
    return f"- {UNKNOWN} `{command}` — {outcome} at checkpoint (run `agentck verify` for staleness)"


def replay_document(report: dict) -> str:
    lines: list[str] = []
    add = lines.append
    label = f" (label: {report['label']})" if report.get("label") else ""
    add(f"Replay of {report['id']}{label}")
    add(
        f"Recorded at {report['created_at']} — re-running "
        f"{report['commands_total']} command(s) in the current repository."
    )
    add("")

    def fmt(code: int | None) -> str:
        if code == 0:
            return "PASS"
        if code is None:
            return "NO RESULT"
        return f"FAIL (exit {code})"

    for result in report["results"]:
        was, now = result["recorded_exit_code"], result["replayed_exit_code"]
        verdict = result["verdict"]
        if verdict == "regression":
            add(f"{WARN} {result['command']}")
            add(f"  recorded {fmt(was)} → replayed {fmt(now)} — REGRESSION since checkpoint")
        elif verdict == "improved":
            add(f"{CHECK} {result['command']}")
            add(f"  recorded {fmt(was)} → replayed {fmt(now)} — improved since checkpoint")
        elif verdict == "error":
            add(f"{FAIL} {result['command']}")
            add(f"  recorded {fmt(was)} → replay failed (timed out or could not run)")
        else:
            add(f"{CHECK} {result['command']}")
            add(f"  recorded {fmt(was)} → replayed {fmt(now)} — consistent")
        if verdict in ("regression", "error"):
            tail = (result.get("stderr_tail") or result.get("stdout_tail") or "").strip()
            if tail:
                add("  output tail:")
                for tail_line in tail.splitlines()[-8:]:
                    add(f"    {tail_line}")

    summary = report["summary"]
    add("")
    add(
        f"{summary['consistent']}/{report['commands_total']} consistent, "
        f"{summary['regressions']} regression(s), "
        f"{summary['improved']} improved, "
        f"{summary['errors']} error(s)"
    )
    return "\n".join(lines) + "\n"


def _node_label(manifest) -> str:
    extras = []
    if manifest.label:
        extras.append(manifest.label)
    if manifest.source_agent:
        extras.append(manifest.source_agent)
    if manifest.head:
        extras.append("@" + manifest.head[:7])
    return manifest.id + (f" ({', '.join(extras)})" if extras else "")


def graph_document(manifests: list) -> str:
    """Render the checkpoint DAG as an ASCII tree (forks = shared parents)."""
    if not manifests:
        return "no checkpoints yet — run `agentck save`\n"
    lines: list[str] = []
    by_id = {m.id: m for m in manifests}
    children: dict[str, list] = {}
    roots: list[tuple[object, str | None]] = []
    for manifest in manifests:
        parent = manifest.data.get("parent")
        if parent and parent in by_id:
            children.setdefault(parent, []).append(manifest)
        else:
            roots.append((manifest, parent))

    def walk(node, prefix: str) -> None:
        kids = children.get(node.id, [])
        for index, kid in enumerate(kids):
            last = index == len(kids) - 1
            branch = "└─ " if last else "├─ "
            lines.append(f"{prefix}{branch}{_node_label(kid)}")
            walk(kid, prefix + ("   " if last else "│  "))

    for manifest, orphan_parent in roots:
        note = f"  ! parent {orphan_parent} not found in this store" if orphan_parent else ""
        lines.append(f"{_node_label(manifest)}{note}")
        walk(manifest, "")
    return "\n".join(lines) + "\n"


def verify_document(report: dict) -> str:
    lines: list[str] = []
    add = lines.append
    label = f" (label: {report['label']})" if report.get("label") else ""
    add(f"Checkpoint {report['id']}{label}")
    add(f"Created {report['created_at']} — source agent: {report['source_agent']}")
    add("")

    add("Integrity")
    integrity = report["integrity"]
    if integrity["ok"]:
        add(f"{CHECK} {integrity['checked']} artifacts match recorded hashes")
    else:
        for problem in integrity["problems"]:
            add(f"{FAIL} {problem}")
    add("")

    add("Repository")
    repository = report["repository"]
    if not repository["accessible"]:
        add(f"{WARN} repository state could not be inspected")
    else:
        if repository["same_path"]:
            add(f"{CHECK} same repository")
        else:
            add(f"{WARN} different repository path than the checkpoint recorded")
        branch = repository["branch"]
        head = repository["head"]
        if branch["same"]:
            add(f"{CHECK} branch unchanged ({branch['recorded']})")
        else:
            add(f"{WARN} branch changed: {branch['recorded']} → {branch['current']}")
        if head["exists"] is False:
            add(f"{FAIL} recorded HEAD {head['recorded']} no longer exists in this repository")
        elif head["same"]:
            add(f"{CHECK} HEAD unchanged ({_short_head(head['recorded'])})")
        else:
            head_from = _short_head(head["recorded"])
            head_to = _short_head(head["current"])
            add(f"{WARN} HEAD moved: {head_from} → {head_to}")
    for note in repository["notes"]:
        add(f"{WARN} {note}")
    add("")

    add("Files")
    if report["files"]:
        for row in report["files"]:
            if row["verdict"] == "unchanged":
                add(f"{CHECK} {row['path']} unchanged")
            else:
                add(f"{WARN} {row['path']} {row['verdict']} since checkpoint")
    else:
        add("no changed files were recorded at checkpoint")
    if report["new_changes"]["count"]:
        add(
            f"{UNKNOWN} {report['new_changes']['count']} new change(s) since checkpoint "
            "(current work, not drift)"
        )
    add("")

    add("Tests")
    if report["tests"]:
        for row in report["tests"]:
            exit_code = row["exit_code"]
            outcome = "PASS" if exit_code == 0 else f"FAIL (exit {exit_code})"
            if row["verdict"] == "stale":
                add(f"{WARN} {row['command']}")
                add(f"  {outcome} at checkpoint — result is now STALE ({row['reason']})")
            else:
                add(f"{CHECK} {row['command']}")
                add(f"  {outcome} at checkpoint ({row['reason']})")
    else:
        add("no test results were recorded at checkpoint")
    add("")

    add("Claims")
    if report["claims"]:
        for claim in report["claims"]:
            add(f"{UNKNOWN} \"{claim['claim']}\"")
            add("  agent-reported, not independently verified")
    else:
        add("no agent claims recorded")
    add("")

    add(f"Resume confidence: {report['confidence']}%")
    for entry in report["confidence_breakdown"]:
        add(f"  {entry}")
    return "\n".join(lines) + "\n"


def diff_document(diff: dict) -> str:
    lines: list[str] = []
    add = lines.append
    a, b = diff["a"], diff["b"]
    add(f"{a['id']} → {b['id']}")
    add("")

    def field_line(name: str, before: object, after: object, changed: bool) -> None:
        if changed:
            add(f"  {name}: {before or '-'} → {after or '-'} (changed)")
        else:
            add(f"  {name}: {before or '-'} (unchanged)")

    add("Repository")
    field_line("branch", a["branch"], b["branch"], diff["branch_changed"])
    field_line("HEAD", _short_head(a["head"]), _short_head(b["head"]), diff["head_changed"])
    add("")

    add("Task")
    field_line("goal", a["goal"], b["goal"], diff["goal_changed"])
    add("")

    add("Files (observed at a → observed at b)")
    files = diff["files"]
    if not (files["added"] or files["removed"] or files["changed"]):
        add("  (no observed file differences)")
    for path in files["added"]:
        add(f"  + {path} (new in {b['id']})")
    for path in files["removed"]:
        add(f"  - {path} (only in {a['id']})")
    for path in files["changed"]:
        add(f"  ~ {path} (content changed)")
    add("")

    sections = (
        ("completed", "Claims (completed)"),
        ("next", "Next steps"),
        ("do_not", "Do not"),
    )
    for section, title in sections:
        delta = diff[section]
        add(title)
        if not (delta["added"] or delta["removed"]):
            add("  (unchanged)")
        for item in delta["added"]:
            add(f"  + \"{item}\"")
        for item in delta["removed"]:
            add(f"  - \"{item}\"")
        add("")
    return "\n".join(lines).rstrip() + "\n"
