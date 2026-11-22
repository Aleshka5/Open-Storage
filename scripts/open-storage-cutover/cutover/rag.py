"""Requeue plan for file_index_links. RAG_ENABLED stays false."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from cutover.errors import CutoverRefused

# claim_due keeps a row only when its state is in this set, its section is not
# PRIVATE, and next_attempt_at is null or <= the claim time. INDEXED, FAILED
# and SKIPPED are outside the set, so they are not claimed.
DUE_STATES = frozenset({"PENDING", "SUBMITTED", "REMOVED", "REINDEX_PENDING"})
EXCLUDED_SECTION = "PRIVATE"
RAG_ENABLED_DEFAULT = "false"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class IndexLink:
    id: str
    section: str
    state: str
    rag_file_id: str | None
    next_attempt_at: datetime | None
    attempts: int


@dataclass(frozen=True)
class PlannedLink:
    id: str
    section: str
    state: str
    rag_file_id: str | None
    next_attempt_at: datetime | None
    attempts: int
    excluded: bool


@dataclass(frozen=True)
class RequeuePlan:
    links: tuple[PlannedLink, ...]
    rag_enabled: str
    sql: str


def is_due(
    *,
    state: str,
    section: str,
    next_attempt_at: datetime | None,
    now: datetime,
) -> bool:
    """The claim_due predicate. A future next_attempt_at excludes the row."""
    if state not in DUE_STATES:
        return False
    if section == EXCLUDED_SECTION:
        return False
    if next_attempt_at is not None and next_attempt_at > now:
        return False
    return True


def guard_rag_enabled(value: str | None) -> str:
    """Default false. A true value is refused and is not written."""
    if value is None or value.strip() == "":
        return RAG_ENABLED_DEFAULT
    if value.strip().lower() in _TRUE_VALUES:
        raise CutoverRefused("refuses to set RAG_ENABLED=true")
    if value.strip().lower() != "false":
        raise CutoverRefused("RAG_ENABLED stays false")
    return RAG_ENABLED_DEFAULT


def plan_requeue(
    links: Sequence[IndexLink],
    *,
    rag_enabled: str | None = None,
) -> RequeuePlan:
    """Reset non-private links to a due state and leave rag_file_id as it is.

    REMOVED stays REMOVED so the same rag_file_id is still the delete target.
    Every other non-private row becomes PENDING with next_attempt_at null.
    PRIVATE rows are unchanged because the predicate excludes that section.
    """
    enabled = guard_rag_enabled(rag_enabled)
    planned: list[PlannedLink] = []
    for link in links:
        if link.section == EXCLUDED_SECTION:
            planned.append(
                PlannedLink(
                    id=link.id,
                    section=link.section,
                    state=link.state,
                    rag_file_id=link.rag_file_id,
                    next_attempt_at=link.next_attempt_at,
                    attempts=link.attempts,
                    excluded=True,
                )
            )
            continue
        state = "REMOVED" if link.state == "REMOVED" else "PENDING"
        planned.append(
            PlannedLink(
                id=link.id,
                section=link.section,
                state=state,
                rag_file_id=link.rag_file_id,
                next_attempt_at=None,
                attempts=0,
                excluded=False,
            )
        )
    sql = render_requeue_sql()
    return RequeuePlan(links=tuple(planned), rag_enabled=enabled, sql=sql)


def render_requeue_sql() -> str:
    """Updates that do not assign rag_file_id and do not mention RAG_ENABLED."""
    sql = "\n".join(
        (
            "UPDATE file_index_links",
            "SET state = 'PENDING', next_attempt_at = NULL, attempts = 0",
            "WHERE section <> 'PRIVATE' AND state <> 'REMOVED';",
            "UPDATE file_index_links",
            "SET next_attempt_at = NULL, attempts = 0",
            "WHERE section <> 'PRIVATE' AND state = 'REMOVED';",
        )
    )
    for line in sql.splitlines():
        if "rag_file_id" in line or "RAG_ENABLED" in line:
            raise CutoverRefused("requeue SQL must leave rag_file_id and RAG_ENABLED alone")
    return sql + "\n"


def due_queue_exclusions() -> Mapping[str, object]:
    """Names of the claim_due filters, for the procedure doc and the tests."""
    return {
        "state_in": tuple(sorted(DUE_STATES)),
        "section_excluded": EXCLUDED_SECTION,
        "next_attempt_at": "null or <= claim time; a later timestamp is excluded",
    }
