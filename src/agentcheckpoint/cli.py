"""Command-line interface for the `agentck` command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentcheckpoint import __version__, util
from agentcheckpoint.checkpoint.create import save_checkpoint
from agentcheckpoint.checkpoint.diff import diff_checkpoints
from agentcheckpoint.checkpoint.load import list_checkpoints, load_manifest
from agentcheckpoint.checkpoint.replay import replay_checkpoint
from agentcheckpoint.checkpoint.restore import restore_checkpoint
from agentcheckpoint.checkpoint.verify import current_repo_root, verify_checkpoint
from agentcheckpoint.errors import AgentCheckpointError, StoreError
from agentcheckpoint.git.collector import repo_root
from agentcheckpoint.render.markdown import (
    TARGETS,
    diff_document,
    graph_document,
    handoff_document,
    replay_document,
    verify_document,
)
from agentcheckpoint.schema import SchemaError, SemanticData
from agentcheckpoint.store import init_store, load_config, open_store, resolve_ref


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - e.g. replaced stdout in tests/embedders
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
        return 0 if result is None else result
    except AgentCheckpointError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except SchemaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentck",
        description=(
            "Verifiable, restorable execution checkpoints for coding-agent sessions. "
            "Machine-observed facts and agent-reported claims are stored separately."
        ),
    )
    parser.add_argument("--version", action="version", version=f"agentcheckpoint {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sp_init = sub.add_parser("init", help="initialize .agentcheckpoint/ in this repository")
    sp_init.set_defaults(func=cmd_init)

    sp_save = sub.add_parser("save", help="create a checkpoint of the current work state")
    sp_save.add_argument("label", nargs="?", help="short human name, e.g. before-refactor")
    sp_save.add_argument(
        "--agent", help="name of the agent producing this checkpoint (glm/claude/codex/...)"
    )
    sp_save.add_argument("--goal", help="what this work is trying to achieve")
    sp_save.add_argument("--status", help="task status (default: in_progress)")
    sp_save.add_argument(
        "--completed", action="append", metavar="TEXT",
        help="agent-reported completed item (repeatable)",
    )
    sp_save.add_argument(
        "--decision", action="append", metavar="TEXT", help="decision made (repeatable)"
    )
    sp_save.add_argument(
        "--constraint", action="append", metavar="TEXT", help="constraint (repeatable)"
    )
    sp_save.add_argument(
        "--blocker", action="append", metavar="TEXT", help="current blocker (repeatable)"
    )
    sp_save.add_argument("--next", action="append", metavar="TEXT", help="next step (repeatable)")
    sp_save.add_argument(
        "--do-not", action="append", metavar="TEXT", help="do-not-touch instruction (repeatable)"
    )
    sp_save.add_argument(
        "--semantic", metavar="FILE", help="JSON file with semantic context (see SPEC)"
    )
    sp_save.add_argument(
        "--parent", metavar="REF",
        help="record this checkpoint as continuing from REF instead of the latest one (fork)",
    )
    sp_save.add_argument(
        "--test", action="append", metavar="CMD",
        help="run CMD now and record its exit code as machine-observed evidence (repeatable)",
    )
    sp_save.add_argument("--json", action="store_true", help="print the full manifest JSON")
    sp_save.set_defaults(func=cmd_save)

    sp_list = sub.add_parser("list", help="list checkpoints")
    sp_list.add_argument("--limit", type=int, default=100, help="show at most N (newest last)")
    sp_list.add_argument("--json", action="store_true", help="print JSON rows")
    sp_list.set_defaults(func=cmd_list)

    sp_show = sub.add_parser("show", help="show one checkpoint")
    sp_show.add_argument(
        "ref", nargs="?", default="latest",
        help="checkpoint id, unique prefix, label, or 'latest'",
    )
    sp_show.add_argument("--json", action="store_true", help="print the raw manifest JSON")
    sp_show.set_defaults(func=cmd_show)

    sp_diff = sub.add_parser("diff", help="compare two checkpoints")
    sp_diff.add_argument("ref_a", help="older checkpoint reference")
    sp_diff.add_argument("ref_b", help="newer checkpoint reference")
    sp_diff.set_defaults(func=cmd_diff)

    sp_verify = sub.add_parser("verify", help="check a checkpoint against the current repository")
    sp_verify.add_argument(
        "ref", nargs="?", default="latest", help="checkpoint reference (default: latest)"
    )
    sp_verify.add_argument("--json", action="store_true", help="print the full report JSON")
    sp_verify.set_defaults(func=cmd_verify)

    sp_resume = sub.add_parser("resume", help="render a handoff document for the next agent")
    sp_resume.add_argument(
        "pos", nargs="?", metavar="TARGET|CHECKPOINT",
        help="target agent (claude/codex/glm/plain) or a checkpoint reference",
    )
    sp_resume.add_argument("--checkpoint", help="checkpoint reference (default: latest)")
    sp_resume.add_argument("--target", choices=TARGETS, help="renderer (default: plain)")
    sp_resume.add_argument(
        "--output", metavar="FILE", help="write the document to a file instead of stdout"
    )
    sp_resume.set_defaults(func=cmd_resume)

    sp_restore = sub.add_parser("restore", help="restore a checkpoint (worktree by default)")
    sp_restore.add_argument("ref", help="checkpoint reference")
    sp_restore.add_argument(
        "--worktree", action="store_true", default=True,
        help="restore into a new git worktree (default, safest)",
    )
    sp_restore.add_argument(
        "--in-place", action="store_true",
        help="rewrite the CURRENT working tree (requires --yes)",
    )
    sp_restore.add_argument(
        "--yes", action="store_true",
        help="confirm a destructive in-place restore (a safety checkpoint is saved first)",
    )
    sp_restore.add_argument("--path", metavar="DIR", help="custom location for worktree restore")
    sp_restore.add_argument(
        "--overwrite-untracked", action="store_true",
        help="in-place: overwrite existing untracked files with checkpoint copies",
    )
    sp_restore.set_defaults(func=cmd_restore)

    sp_replay = sub.add_parser(
        "replay", help="re-run the commands recorded at checkpoint time and compare"
    )
    sp_replay.add_argument(
        "ref", nargs="?", default="latest", help="checkpoint reference (default: latest)"
    )
    sp_replay.add_argument("--json", action="store_true", help="print the full report JSON")
    sp_replay.set_defaults(func=cmd_replay)

    sp_log = sub.add_parser("log", help="show the checkpoint DAG as a tree")
    sp_log.set_defaults(func=cmd_log)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    store, created, exclude_added = init_store(root)
    if created:
        print(f"Initialized AgentCheckpoint store: {store}")
        print("  .agentcheckpoint/config.toml")
        print("  .agentcheckpoint/checkpoints/")
    else:
        print(f"AgentCheckpoint store already initialized: {store}")
    if exclude_added:
        print(
            "Added `.agentcheckpoint/` to .git/info/exclude (local only, no tracked files touched)."
        )
    print("Next: `agentck save [label] --goal \"...\"`")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    root, store = open_store(Path.cwd())
    config = load_config(store)

    flags = SemanticData(
        agent=args.agent,
        goal=args.goal,
        status=args.status,
        completed=list(args.completed or []),
        decisions=list(args.decision or []),
        constraints=list(args.constraint or []),
        blockers=list(args.blocker or []),
        next_steps=list(args.next or []),
        do_not=list(args.do_not or []),
        tests=list(args.test or []),
        source="flags",
    )
    if args.semantic:
        semantic = _load_semantic_file(Path(args.semantic))
        semantic.merge(flags)
    else:
        semantic = flags

    parent_id = resolve_ref(store, args.parent).name if args.parent else None
    cp_id, cp_dir, manifest, warnings = save_checkpoint(
        root, store, label=args.label, semantic=semantic, config=config, parent_id=parent_id
    )
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if args.json:
        print(util.dump_json(manifest))
        return 0

    observed = manifest["observed"]
    tests = manifest["verification"]["tests"]
    label_note = f" (label: {args.label})" if args.label else ""
    print(f"Checkpoint saved: {cp_id}{label_note}")
    branch_label = manifest["repo"]["branch"] or "(detached)"
    print(f"  branch:   {branch_label} @ {_short(manifest['repo']['head'])}")
    print(
        f"  changes:  {len(observed['staged_files'])} staged, "
        f"{len(observed['unstaged_files'])} unstaged, "
        f"{len(observed['untracked_files'])} untracked, "
        f"{len(observed['conflicts'])} conflicts"
    )
    if tests:
        passed = sum(1 for t in tests if t["exit_code"] == 0)
        print(
            f"  tests:    {len(tests)} recorded "
            f"({passed} passed, {len(tests) - passed} failed/other)"
        )
    goal_note = f" | goal: {manifest['task']['goal']}" if manifest["task"]["goal"] else ""
    print(f"  agent:    {manifest['source_agent']}{goal_note}")
    print(f"  saved to: {cp_dir}")
    return 0


def _load_semantic_file(path: Path) -> SemanticData:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StoreError(f"cannot read semantic file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaError(f"semantic file {path} is not valid JSON: {exc}") from exc
    return SemanticData.from_dict(raw, source=f"file:{path.name}")


def cmd_list(args: argparse.Namespace) -> int:
    _, store = open_store(Path.cwd())
    manifests = list_checkpoints(store)
    if args.limit is not None and args.limit >= 0:
        manifests = manifests[-args.limit:] if args.limit else []
    if args.json:
        rows = [
            {
                "id": m.id,
                "label": m.label,
                "created_at": m.created_at,
                "source_agent": m.source_agent,
                "status": m.status,
                "goal": m.goal,
                "branch": m.branch,
                "head": m.head,
            }
            for m in manifests
        ]
        print(util.dump_json(rows))
        return 0
    if not manifests:
        print("no checkpoints yet — run `agentck save`")
        return 0
    print(f"{'ID':<22} {'LABEL':<20} {'AGENT':<10} {'STATUS':<12} GOAL")
    for m in manifests:
        print(
            f"{m.id:<22} {_trunc(m.label or '-', 20):<20} "
            f"{_trunc(m.source_agent or '-', 10):<10} {_trunc(m.status or '-', 12):<12} "
            f"{_trunc(m.goal or '-', 48)}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    _, store = open_store(Path.cwd())
    cp_dir = resolve_ref(store, args.ref)
    manifest = load_manifest(cp_dir)
    if args.json:
        print(util.dump_json(manifest.data))
        return 0
    label = f" (label: {manifest.label})" if manifest.label else ""
    print(f"Checkpoint {manifest.id}{label}")
    print(f"  created:  {manifest.created_at} by agent {manifest.source_agent}")
    print(f"  branch:   {manifest.branch or '(detached)'} @ {_short(manifest.head)}")
    print(f"  goal:     {manifest.goal or '(not recorded)'}")
    observed = manifest.data["observed"]
    print(
        f"  changes:  {len(observed['staged_files'])} staged, "
        f"{len(observed['unstaged_files'])} unstaged, "
        f"{len(observed['untracked_files'])} untracked"
    )
    print(f"  tests:    {len(manifest.tests)} recorded")
    print()
    handoff_path = cp_dir / "handoff.md"
    print(handoff_path.read_text(encoding="utf-8"), end="")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    _, store = open_store(Path.cwd())
    manifest_a = load_manifest(resolve_ref(store, args.ref_a))
    manifest_b = load_manifest(resolve_ref(store, args.ref_b))
    print(diff_document(diff_checkpoints(manifest_a, manifest_b)))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    root, store = open_store(Path.cwd())
    cp_dir = resolve_ref(store, args.ref)
    manifest = load_manifest(cp_dir)
    if not manifest.tests:
        print(
            f"Checkpoint {manifest.id} has no recorded commands — "
            "use `agentck save --test CMD` to record executable evidence."
        )
        return 0
    report = replay_checkpoint(cp_dir, manifest, root, load_config(store))
    if args.json:
        print(util.dump_json(report))
    else:
        print(replay_document(report))
    return report["exit_hint"]


def cmd_log(args: argparse.Namespace) -> int:
    _, store = open_store(Path.cwd())
    print(graph_document(list_checkpoints(store)), end="")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    _, store = open_store(Path.cwd())
    cp_dir = resolve_ref(store, args.ref)
    manifest = load_manifest(cp_dir)
    report = verify_checkpoint(cp_dir, manifest, current_repo_root(manifest, Path.cwd()))
    if args.json:
        print(util.dump_json(report))
    else:
        print(verify_document(report))
    if not report["integrity"]["ok"]:
        return 2
    return 1 if report["drift"] else 0


def cmd_resume(args: argparse.Namespace) -> int:
    _, store = open_store(Path.cwd())
    ref = args.checkpoint or "latest"
    target = args.target
    if args.pos:
        if args.pos in TARGETS:
            target = target or args.pos
        else:
            ref = args.pos
    target = target or "plain"

    cp_dir = resolve_ref(store, ref)
    manifest = load_manifest(cp_dir)
    report = verify_checkpoint(cp_dir, manifest, current_repo_root(manifest, Path.cwd()))
    document = handoff_document(manifest.data, report=report, target=target)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        print(f"Wrote handoff document: {output}")
    else:
        print(document, end="")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    root, store = open_store(Path.cwd())
    if args.in_place and not args.yes:
        print(
            "error: in-place restore rewrites your current working tree.\n"
            "Re-run with `--in-place --yes`. A safety checkpoint of the current state\n"
            "is always written first. For a non-destructive restore, drop --in-place\n"
            "(a fresh git worktree is created instead).",
            file=sys.stderr,
        )
        return 2
    cp_dir = resolve_ref(store, args.ref)
    manifest = load_manifest(cp_dir)
    mode = "in_place" if args.in_place else "worktree"
    target_path = Path(args.path).resolve() if args.path else None
    config = load_config(store)
    result = restore_checkpoint(
        root,
        store,
        cp_dir,
        manifest,
        mode=mode,
        target_path=target_path,
        config=config,
        overwrite_untracked=args.overwrite_untracked,
    )
    print(f"Restored {result.checkpoint_id} (mode: {result.mode})")
    print(f"  location: {result.path}")
    print(f"  untracked files restored: {len(result.restored_untracked)}")
    for entry in result.skipped_untracked:
        print(f"  skipped untracked: {entry['path']} ({entry['reason']})")
    if result.hash_mismatches:
        matched = result.hash_checked - len(result.hash_mismatches)
        print(f"  hash verification: {matched}/{result.hash_checked} matched")
        for rel in result.hash_mismatches:
            print(f"  MISMATCH: {rel}")
    else:
        print(f"  hash verification: {result.hash_checked}/{result.hash_checked} matched")
    if result.safety_checkpoint_id:
        print(f"  safety checkpoint: {result.safety_checkpoint_id}")
    for note in result.notes:
        print(f"  note: {note}")
    print(f"Next: cd \"{result.path}\" && agentck resume {result.checkpoint_id} --target <agent>")
    return 0


def _short(head: str | None) -> str:
    return head[:12] if head else "(no commits)"


def _trunc(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
