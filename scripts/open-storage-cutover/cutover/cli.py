"""Print a cutover plan. There is no subcommand that runs it."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from cutover.bucket import plan_mirror
from cutover.dump_restore import plan_dump_restore
from cutover.errors import CutoverRefused
from cutover.rag import plan_requeue
from cutover.subjects import render_subject_sql


def run(action: str) -> None:
    """No action is executed. pg_dump, mc, DNS, and decommission all refuse."""
    raise CutoverRefused(f"refuses to run {action}; this tool only plans and checks")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cutover",
        description="Print open-storage cutover plans. Does not connect to a service.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dump = sub.add_parser("plan-dump", help="print pg_dump -Fc, pg_restore, and the truncate")
    dump.add_argument("--dump-path", required=True)
    dump.add_argument("--legacy-stopped", action="store_true")

    mirror = sub.add_parser("plan-mirror", help="print mc mirror --preserve between endpoints")
    mirror.add_argument("--source-endpoint", required=True)
    mirror.add_argument("--target-endpoint", required=True)

    subjects = sub.add_parser("plan-subjects", help="print the in-place users.id rewrite")
    subjects.add_argument("--mapping", required=True, type=Path)
    subjects.add_argument("--user-id", action="append", required=True)

    requeue = sub.add_parser("plan-requeue", help="print the file_index_links reset")
    requeue.add_argument("--enable-rag", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "plan-dump":
            plan = plan_dump_restore(
                legacy_app_stopped=args.legacy_stopped,
                dump_path=args.dump_path,
            )
            for step in plan.steps:
                print(" ".join(step))
            for query in plan.baseline_count_sql:
                print(query)
            return 0
        if args.command == "plan-mirror":
            plan = plan_mirror(
                source_endpoint=args.source_endpoint,
                target_endpoint=args.target_endpoint,
            )
            print(f"source_endpoint={plan.source_endpoint}")
            print(f"target_endpoint={plan.target_endpoint}")
            print(" ".join(plan.command))
            for command in plan.summarize_commands:
                print(" ".join(command))
            return 0
        if args.command == "plan-subjects":
            payload = json.loads(args.mapping.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise CutoverRefused("mapping file is a JSON object of old id to subject")
            print(render_subject_sql(args.user_id, {str(k): str(v) for k, v in payload.items()}))
            return 0
        if args.command == "plan-requeue":
            if args.enable_rag:
                plan_requeue((), rag_enabled="true")
            plan = plan_requeue(())
            print(plan.sql, end="")
            print(f"RAG_ENABLED={plan.rag_enabled}")
            return 0
    except CutoverRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    raise CutoverRefused(f"unknown command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
