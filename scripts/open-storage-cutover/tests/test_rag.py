import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cutover.errors import CutoverRefused
from cutover.rag import (
    DUE_STATES,
    IndexLink,
    due_queue_exclusions,
    guard_rag_enabled,
    is_due,
    plan_requeue,
    render_requeue_sql,
)

REPO = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_due_queue_names_the_claim_due_exclusions() -> None:
    indexing = (
        REPO / "src/open-storage/app/app/domain/indexing.py"
    ).read_text(encoding="utf-8")
    match = re.search(r"DUE_INDEX_STATES.*?frozenset\(\s*\{(.*?)\}\s*\)", indexing, re.S)
    assert match is not None
    names = set(re.findall(r"IndexLinkState\.([A-Z_]+)", match.group(1)))
    assert names == set(DUE_STATES)

    repo = (
        REPO
        / "src/open-storage/app/app/infrastructure/database/repositories/file_index_link_repo.py"
    ).read_text(encoding="utf-8")
    body = repo[repo.index("async def claim_due") : repo.index("async def apply_transition")]
    assert "FileIndexLink.state.in_(_DUE_STATE_VALUES)" in body
    assert "FileIndexLink.section != FileSectionModel.PRIVATE" in body
    assert "FileIndexLink.next_attempt_at.is_(None)" in body
    assert "FileIndexLink.next_attempt_at <= moment" in body

    named = due_queue_exclusions()
    assert set(named["state_in"]) == set(DUE_STATES)
    assert named["section_excluded"] == "PRIVATE"

    assert is_due(state="PENDING", section="FILES", next_attempt_at=None, now=NOW) is True
    assert is_due(state="PENDING", section="FILES", next_attempt_at=NOW, now=NOW) is True
    assert (
        is_due(
            state="PENDING",
            section="FILES",
            next_attempt_at=NOW + timedelta(seconds=1),
            now=NOW,
        )
        is False
    )
    assert is_due(state="INDEXED", section="PHOTOS", next_attempt_at=None, now=NOW) is False
    assert is_due(state="FAILED", section="FILES", next_attempt_at=None, now=NOW) is False
    assert is_due(state="SKIPPED", section="FILES", next_attempt_at=None, now=NOW) is False
    assert is_due(state="PENDING", section="PRIVATE", next_attempt_at=None, now=NOW) is False


def test_requeue_keeps_rag_file_id_and_refuses_to_enable_rag() -> None:
    later = NOW + timedelta(days=1)
    links = (
        IndexLink("link-indexed", "PHOTOS", "INDEXED", "rag-1", later, 3),
        IndexLink("link-removed", "FILES", "REMOVED", "rag-2", later, 2),
        IndexLink("link-private", "PRIVATE", "INDEXED", "rag-private", later, 4),
        IndexLink("link-pending", "FILES", "PENDING", None, later, 1),
    )

    plan = plan_requeue(links)

    by_id = {link.id: link for link in plan.links}
    assert by_id["link-indexed"].state == "PENDING"
    assert by_id["link-indexed"].rag_file_id == "rag-1"
    assert by_id["link-indexed"].next_attempt_at is None
    assert by_id["link-indexed"].attempts == 0
    assert by_id["link-indexed"].excluded is False
    assert (
        is_due(
            state=by_id["link-indexed"].state,
            section=by_id["link-indexed"].section,
            next_attempt_at=by_id["link-indexed"].next_attempt_at,
            now=NOW,
        )
        is True
    )
    assert by_id["link-removed"].state == "REMOVED"
    assert by_id["link-removed"].rag_file_id == "rag-2"
    assert by_id["link-removed"].next_attempt_at is None
    assert by_id["link-private"].state == "INDEXED"
    assert by_id["link-private"].rag_file_id == "rag-private"
    assert by_id["link-private"].next_attempt_at == later
    assert by_id["link-private"].attempts == 4
    assert by_id["link-private"].excluded is True
    assert by_id["link-pending"].rag_file_id is None
    assert plan.rag_enabled == "false"
    assert "rag_file_id" not in plan.sql
    assert "RAG_ENABLED" not in plan.sql

    with pytest.raises(CutoverRefused, match="RAG_ENABLED"):
        plan_requeue(links, rag_enabled="true")
    assert guard_rag_enabled(None) == "false"
    assert guard_rag_enabled("false") == "false"


def test_requeue_sql_matches_the_planner_on_sqlite() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE file_index_links (
            id TEXT PRIMARY KEY,
            section TEXT NOT NULL,
            state TEXT NOT NULL,
            rag_file_id TEXT,
            next_attempt_at TEXT,
            attempts INTEGER NOT NULL
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO file_index_links
            (id, section, state, rag_file_id, next_attempt_at, attempts)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ("link-indexed", "PHOTOS", "INDEXED", "rag-1", "2026-02-01T00:00:00+00:00", 3),
            ("link-removed", "FILES", "REMOVED", "rag-2", "2026-02-01T00:00:00+00:00", 2),
            ("link-private", "PRIVATE", "INDEXED", "rag-private", "2026-02-01T00:00:00+00:00", 4),
        ),
    )
    connection.executescript(render_requeue_sql())
    rows = connection.execute(
        """
        SELECT id, section, state, rag_file_id, next_attempt_at, attempts
        FROM file_index_links
        ORDER BY id
        """
    ).fetchall()
    assert rows == [
        ("link-indexed", "PHOTOS", "PENDING", "rag-1", None, 0),
        ("link-private", "PRIVATE", "INDEXED", "rag-private", "2026-02-01T00:00:00+00:00", 4),
        ("link-removed", "FILES", "REMOVED", "rag-2", None, 0),
    ]
