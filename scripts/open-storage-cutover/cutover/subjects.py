"""Map each users.id to an idp subject once. The rewrite does not insert a user."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cutover.errors import CutoverRefused

TEMP_PREFIX = "__cutover_tmp_"
CHILD_TABLES = (
    "file_records",
    "user_quota_usage",
    "file_index_links",
    "upload_sessions",
)


class SubjectMapError(CutoverRefused):
    """The mapping is not one-to-one with the current users.id values."""


@dataclass(frozen=True)
class SubjectUser:
    id: str
    email: str


def validate_subject_map(
    user_ids: Sequence[str],
    mapping: Mapping[str, str],
) -> dict[str, str]:
    """Require every current users.id exactly once, and unique targets."""
    if len(user_ids) != len(set(user_ids)):
        raise SubjectMapError("duplicate users.id")
    cleaned: dict[str, str] = {}
    seen_targets: set[str] = set()
    for old, new in mapping.items():
        if not isinstance(old, str) or not isinstance(new, str) or old == "" or new == "":
            raise SubjectMapError("mapping ids must be non-empty strings")
        if old.startswith(TEMP_PREFIX) or new.startswith(TEMP_PREFIX):
            raise SubjectMapError("mapping id uses the scratch prefix")
        if "'" in old or "'" in new or ";" in old or ";" in new or "--" in old or "--" in new:
            raise SubjectMapError("mapping id contains a character the SQL generator refuses")
        if new in seen_targets:
            raise SubjectMapError(f"duplicate target {new}")
        seen_targets.add(new)
        cleaned[old] = new
    ids = set(user_ids)
    unmapped = sorted(ids - set(cleaned))
    if unmapped:
        raise SubjectMapError("unmapped ids: " + ", ".join(unmapped))
    extra = sorted(set(cleaned) - ids)
    if extra:
        raise SubjectMapError("mapping keys are not users.id: " + ", ".join(extra))
    return {user_id: cleaned[user_id] for user_id in user_ids}


def apply_subject_switch(
    users: Sequence[SubjectUser],
    mapping: Mapping[str, str],
) -> tuple[SubjectUser, ...]:
    """Return the same rows with ids replaced by subjects. Length is unchanged."""
    validated = validate_subject_map(tuple(user.id for user in users), mapping)
    rewritten = tuple(
        SubjectUser(id=validated[user.id], email=user.email) for user in users
    )
    if len(rewritten) != len(users):
        raise SubjectMapError("subject switch created a users row")
    if len({user.id for user in rewritten}) != len(rewritten):
        raise SubjectMapError("duplicate target")
    return rewritten


def render_subject_sql(user_ids: Sequence[str], mapping: Mapping[str, str]) -> str:
    """SQL that rewrites ids in place. It contains no INSERT into users."""
    validated = validate_subject_map(user_ids, mapping)
    lines = [
        "BEGIN;",
        "-- in-place id rewrite, no INSERT into users, column type is unchanged",
    ]
    for index, old in enumerate(user_ids):
        temp = f"{TEMP_PREFIX}{index}"
        lines.extend(_updates(old, temp))
    for index, old in enumerate(user_ids):
        temp = f"{TEMP_PREFIX}{index}"
        lines.extend(_updates(temp, validated[old]))
    lines.append("COMMIT;")
    sql = "\n".join(lines) + "\n"
    if "INSERT INTO users" in sql or "INSERT INTO " in sql:
        raise SubjectMapError("subject SQL must not insert rows")
    return sql


def apply_subject_sql(connection, user_ids: Sequence[str], mapping: Mapping[str, str]) -> None:
    """Run the generated script on a SQLite connection. Foreign keys are off for the rewrite."""
    connection.execute("PRAGMA foreign_keys=OFF")
    try:
        for statement in _executable_statements(render_subject_sql(user_ids, mapping)):
            connection.execute(statement)
        connection.commit()
    finally:
        connection.execute("PRAGMA foreign_keys=ON")


def _executable_statements(sql: str) -> list[str]:
    statements: list[str] = []
    for chunk in sql.split(";"):
        lines = [
            line
            for line in chunk.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if lines:
            statements.append("\n".join(lines))
    return statements


def _updates(old: str, new: str) -> list[str]:
    quoted_old = _quote(old)
    quoted_new = _quote(new)
    lines = [f"UPDATE users SET id = {quoted_new} WHERE id = {quoted_old};"]
    for table in CHILD_TABLES:
        lines.append(
            f"UPDATE {table} SET user_id = {quoted_new} WHERE user_id = {quoted_old};"
        )
    return lines


def _quote(value: str) -> str:
    return "'" + value + "'"
