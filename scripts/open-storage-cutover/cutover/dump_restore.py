"""Dump and restore plan for db_storage. Commands are returned, never run."""

from dataclasses import dataclass

from cutover.errors import CutoverRefused

SOURCE_DATABASE = "db_storage"
TARGET_HOST = "open-storage-postgres"
TARGET_DATABASE = "db_storage"
EMPTY_TABLE = "upload_sessions"
TRUNCATE_UPLOAD_SESSIONS = "TRUNCATE TABLE upload_sessions;"

BASELINE_COUNT_SQL: tuple[str, ...] = (
    "SELECT count(*) AS users FROM users;",
    "SELECT status, section, count(*) AS n FROM file_records GROUP BY status, section;",
    "SELECT count(*) AS user_quota_usage FROM user_quota_usage;",
    "SELECT state, count(*) AS n FROM file_index_links GROUP BY state;",
    "SELECT count(*) AS upload_sessions FROM upload_sessions;",
)

_HOST_BUCKET_MARKERS = ("/media/aleksey/HardDisk/minio", "xl.meta")


@dataclass(frozen=True)
class DumpRestorePlan:
    """Ordered commands. Step 3 empties upload_sessions so its rows are not carried."""

    legacy_app_stopped: bool
    dump_path: str
    steps: tuple[tuple[str, ...], ...]
    baseline_count_sql: tuple[str, ...]
    empty_tables: tuple[str, ...]
    source_database: str
    target_host: str
    target_database: str


def plan_dump_restore(*, legacy_app_stopped: bool, dump_path: str) -> DumpRestorePlan:
    """Plan pg_dump -Fc of db_storage and pg_restore into the namespace database.

    The legacy app must already be stopped. upload_sessions is truncated after
    restore. This function does not run pg_dump, pg_restore, or psql.
    """
    if legacy_app_stopped is not True:
        raise CutoverRefused("legacy app must be stopped before pg_dump")
    _reject_dump_path(dump_path)
    plan = DumpRestorePlan(
        legacy_app_stopped=True,
        dump_path=dump_path,
        steps=(
            ("pg_dump", "-Fc", "-d", SOURCE_DATABASE, "-f", dump_path),
            (
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "-h",
                TARGET_HOST,
                "-d",
                TARGET_DATABASE,
                dump_path,
            ),
            (
                "psql",
                "-h",
                TARGET_HOST,
                "-d",
                TARGET_DATABASE,
                "-c",
                TRUNCATE_UPLOAD_SESSIONS,
            ),
        ),
        baseline_count_sql=BASELINE_COUNT_SQL,
        empty_tables=(EMPTY_TABLE,),
        source_database=SOURCE_DATABASE,
        target_host=TARGET_HOST,
        target_database=TARGET_DATABASE,
    )
    validate_dump_restore_plan(plan)
    return plan


def validate_dump_restore_plan(plan: DumpRestorePlan) -> None:
    """Reject a plan that dumps a live app, skips -Fc, or carries upload_sessions."""
    if plan.legacy_app_stopped is not True:
        raise CutoverRefused("legacy app must be stopped before pg_dump")
    if len(plan.steps) != 3:
        raise CutoverRefused("dump, restore, then truncate upload_sessions")
    dump_command, restore_command, empty_command = plan.steps
    if dump_command[0] != "pg_dump" or "-Fc" not in dump_command:
        raise CutoverRefused("dump must be pg_dump -Fc")
    if SOURCE_DATABASE not in dump_command or plan.source_database != SOURCE_DATABASE:
        raise CutoverRefused("dump source database must be db_storage")
    if restore_command[0] != "pg_restore":
        raise CutoverRefused("restore must be pg_restore")
    if plan.target_host != TARGET_HOST or TARGET_HOST not in restore_command:
        raise CutoverRefused("pg_restore target host is open-storage-postgres")
    if plan.target_database != TARGET_DATABASE or TARGET_DATABASE not in restore_command:
        raise CutoverRefused("pg_restore target database is the namespace database")
    if empty_command[:5] != ("psql", "-h", TARGET_HOST, "-d", TARGET_DATABASE):
        raise CutoverRefused("upload_sessions is emptied on the namespace database")
    if empty_command[-1] != TRUNCATE_UPLOAD_SESSIONS:
        raise CutoverRefused("upload_sessions rows are not carried")
    if plan.empty_tables != (EMPTY_TABLE,):
        raise CutoverRefused("upload_sessions is the table restored empty")
    if plan.baseline_count_sql != BASELINE_COUNT_SQL:
        raise CutoverRefused("baseline counts are the fixed table queries")
    for command in plan.steps:
        _reject_destructive_command(command)
    _reject_dump_path(plan.dump_path)


def _reject_dump_path(dump_path: str) -> None:
    if not isinstance(dump_path, str) or dump_path.strip() == "" or dump_path != dump_path.strip():
        raise CutoverRefused("dump path is a file path for the custom-format archive")
    for marker in _HOST_BUCKET_MARKERS:
        if marker in dump_path:
            raise CutoverRefused("dump path is not the MinIO host directory")


def _reject_destructive_command(command: tuple[str, ...]) -> None:
    if not command:
        raise CutoverRefused("empty command")
    if command[0] in {"cp", "rm", "docker", "mc"}:
        raise CutoverRefused("dump plan does not copy a host directory or change volumes")
    flat = " ".join(command).lower()
    if "drop database" in flat or "volume rm" in flat or "xl.meta" in flat:
        raise CutoverRefused("dump plan does not drop a database or copy xl.meta")
