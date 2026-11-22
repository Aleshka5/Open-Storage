"""remove the zstd archive feature

Archiving is gone: every record is a live object, ``ARCHIVED`` is no longer a
status, and the index link state of the same name is retired. The data
migration that expands ``*.zst`` objects back to their hot keys runs before
this revision (``backend/scripts/remove_archive.py``); this migration only
shrinks the schema and is safe on any dataset where no row is ARCHIVED.

PostgreSQL cannot drop a value from an enum, so ``file_status`` is recreated.
That takes an exclusive lock on ``file_records`` for the duration of the
rewrite — on this stand the table is small (a few hundred rows), and the
operator stops ``app`` for the run.

Revision ID: 009_remove_archive
Revises: 008_add_file_index_links
Create Date: 2026-11-07 23:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_remove_archive"
down_revision: Union[str, None] = "008_add_file_index_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _recreate_status_enum(values: Sequence[str]) -> None:
    """Swap ``file_status`` for a new enum with exactly ``values``."""
    joined = ", ".join(f"'{value}'" for value in values)
    op.execute("ALTER TYPE file_status RENAME TO file_status_old")
    op.execute(f"CREATE TYPE file_status AS ENUM ({joined})")
    op.execute(
        "ALTER TABLE file_records ALTER COLUMN status TYPE file_status "
        "USING status::text::file_status"
    )
    op.execute("DROP TYPE file_status_old")


def upgrade() -> None:
    # Belt and braces: a leftover ARCHIVED link would point at a state that no
    # longer exists in the code. The data migration already moved them.
    op.execute("UPDATE file_index_links SET state = 'REMOVED' WHERE state = 'ARCHIVED'")

    connection = op.get_bind()
    remaining = connection.execute(
        sa.text("SELECT count(*) FROM file_records WHERE status::text = 'ARCHIVED'")
    ).scalar_one()
    if remaining:
        # Never drop a status that still owns a row: that would delete user
        # data at the schema level. Run backend/scripts/remove_archive.py first.
        raise RuntimeError(
            f"{remaining} file_records rows are still ARCHIVED; "
            "run backend/scripts/remove_archive.py --phases restore first"
        )

    _recreate_status_enum(("PENDING", "COMMITTED", "DELETED"))

    op.drop_column("file_records", "archive_path")
    op.drop_column("file_records", "is_archived")


def downgrade() -> None:
    op.add_column(
        "file_records",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("file_records", sa.Column("archive_path", sa.Text(), nullable=True))
    _recreate_status_enum(("PENDING", "COMMITTED", "ARCHIVED", "DELETED"))
