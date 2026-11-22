import sqlite3

import pytest

from cutover.errors import CutoverRefused
from cutover.subjects import (
    SubjectUser,
    apply_subject_sql,
    apply_subject_switch,
    render_subject_sql,
)


def test_switch_is_one_to_one_and_creates_no_user_row() -> None:
    users = (
        SubjectUser("old-user-1", "one@example.test"),
        SubjectUser("old-user-2", "two@example.test"),
    )
    mapping = {"old-user-1": "subject-1", "old-user-2": "subject-2"}

    switched = apply_subject_switch(users, mapping)

    assert len(switched) == len(users)
    assert [user.id for user in switched] == ["subject-1", "subject-2"]
    assert [user.email for user in switched] == ["one@example.test", "two@example.test"]
    with pytest.raises(CutoverRefused, match="unmapped"):
        apply_subject_switch(switched, mapping)


def test_duplicate_targets_and_unmapped_ids_are_rejected() -> None:
    users = (
        SubjectUser("old-user-1", "one@example.test"),
        SubjectUser("old-user-2", "two@example.test"),
    )
    with pytest.raises(CutoverRefused, match="duplicate target"):
        apply_subject_switch(
            users,
            {"old-user-1": "subject-1", "old-user-2": "subject-1"},
        )
    with pytest.raises(CutoverRefused, match="unmapped"):
        apply_subject_switch(users, {"old-user-1": "subject-1"})


def test_sqlite_rewrite_keeps_the_row_and_moves_child_ids() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL);
        CREATE TABLE file_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id)
        );
        CREATE TABLE user_quota_usage (
            user_id TEXT PRIMARY KEY REFERENCES users(id),
            total_bytes INTEGER NOT NULL
        );
        CREATE TABLE file_index_links (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            rag_file_id TEXT
        );
        CREATE TABLE upload_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id)
        );
        INSERT INTO users (id, email) VALUES ('old-user-1', 'one@example.test');
        INSERT INTO users (id, email) VALUES ('old-user-2', 'two@example.test');
        INSERT INTO file_records (id, user_id) VALUES ('file-1', 'old-user-1');
        INSERT INTO user_quota_usage (user_id, total_bytes) VALUES ('old-user-2', 4);
        INSERT INTO file_index_links (id, user_id, rag_file_id)
            VALUES ('link-1', 'old-user-1', 'rag-1');
        INSERT INTO upload_sessions (id, user_id) VALUES ('session-1', 'old-user-2');
        """
    )
    mapping = {"old-user-1": "subject-2", "old-user-2": "subject-1"}
    before = connection.execute("SELECT count(*) FROM users").fetchone()[0]

    apply_subject_sql(connection, ("old-user-1", "old-user-2"), mapping)

    after_rows = connection.execute(
        "SELECT id, email FROM users ORDER BY email"
    ).fetchall()
    assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == before
    assert after_rows == [
        ("subject-2", "one@example.test"),
        ("subject-1", "two@example.test"),
    ]
    assert connection.execute("SELECT user_id FROM file_records").fetchone()[0] == "subject-2"
    assert connection.execute("SELECT user_id FROM user_quota_usage").fetchone()[0] == "subject-1"
    assert connection.execute(
        "SELECT user_id, rag_file_id FROM file_index_links"
    ).fetchone() == ("subject-2", "rag-1")
    assert connection.execute("SELECT user_id FROM upload_sessions").fetchone()[0] == "subject-1"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    sql = render_subject_sql(("old-user-1", "old-user-2"), mapping)
    assert "INSERT INTO users" not in sql
    assert "INSERT INTO " not in sql

    current_ids = tuple(
        row[0] for row in connection.execute("SELECT id FROM users ORDER BY id")
    )
    with pytest.raises(CutoverRefused, match="unmapped"):
        apply_subject_sql(connection, current_ids, mapping)
    assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == before
