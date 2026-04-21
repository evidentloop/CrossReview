"""CrossReview CLI — ``crossreview pack`` / ``crossreview verify``.

Implements 1C.1 (pack CLI). Verify is a stub until 1B.4+ land.

Usage::

    crossreview pack --diff HEAD~1 > pack.json
    crossreview pack --diff HEAD~1 --intent "fix auth" --focus auth > pack.json
    crossreview pack --diff HEAD~1 --task ./task.md --context ./plan.md > pack.json
"""

from __future__ import annotations

import argparse
import sys

from .pack import (
    GitDiffError,
    assemble_pack,
    changed_files_from_git,
    compute_pack_completeness,
    diff_from_git,
    pack_to_json,
    read_context_files,
    read_task_file,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crossreview",
        description="Context-isolated verification harness for AI-generated code.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- pack ---
    pack_p = sub.add_parser(
        "pack",
        help="Assemble a ReviewPack from a git diff.",
    )
    pack_p.add_argument(
        "--diff",
        required=True,
        metavar="REF",
        help="Git ref for diff base (e.g. HEAD~1, abc123, main..feat).",
    )
    pack_p.add_argument(
        "--intent",
        default=None,
        help="Task intent string.",
    )
    pack_p.add_argument(
        "--task",
        default=None,
        metavar="FILE",
        help="Path to a task description file (content stored in task_file).",
    )
    pack_p.add_argument(
        "--focus",
        action="append",
        default=None,
        help="Focus area (repeatable).",
    )
    pack_p.add_argument(
        "--context",
        action="append",
        default=None,
        metavar="FILE",
        help="Extra context file path (repeatable).",
    )

    # --- verify (stub) ---
    sub.add_parser(
        "verify",
        help="Pack + review + output (not yet implemented).",
    )

    return parser


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute ``crossreview pack``."""

    # 1. Obtain diff
    try:
        diff = diff_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not diff.strip():
        print("error: git diff produced empty output — nothing to pack.", file=sys.stderr)
        return 1

    # 2. Get changed files via git (NUL-delimited, handles special-char paths)
    try:
        changed_files = changed_files_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # 3. Read optional files
    task_content: str | None = None
    if args.task:
        try:
            task_content = read_task_file(args.task)
        except OSError as exc:
            print(f"error: cannot read task file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: task file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1

    context_files = None
    if args.context:
        try:
            context_files = read_context_files(args.context)
        except OSError as exc:
            print(f"error: cannot read context file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: context file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1

    # 4. Assemble
    try:
        pack = assemble_pack(
            diff,
            changed_files=changed_files,
            intent=args.intent,
            task_file=task_content,
            focus=args.focus,
            context_files=context_files,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # 5. Diagnostic to stderr
    completeness = compute_pack_completeness(pack)
    n_files = len(pack.changed_files)
    print(
        f"crossreview pack: {n_files} file(s), completeness={completeness:.2f}, "
        f"artifact={pack.artifact_fingerprint[:12]}",
        file=sys.stderr,
    )

    # 6. JSON to stdout
    print(pack_to_json(pack))
    return 0


def _cmd_verify(_args: argparse.Namespace) -> int:
    """Stub for ``crossreview verify`` — requires 1B.4+ components."""
    print(
        "error: 'verify' is not yet implemented. Use 'pack' to generate a ReviewPack.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "pack":
        return _cmd_pack(args)
    if args.command == "verify":
        return _cmd_verify(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def _entry_point() -> None:
    """Console-script entry point — propagates return code to exit status."""
    raise SystemExit(main())
