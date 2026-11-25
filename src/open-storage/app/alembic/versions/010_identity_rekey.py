"""allow a subject re-key to keep existing files

Identity cutover changes ``users.id`` to the idp subject. Foreign keys on
``user_id`` must follow that update, and ``object_prefix_id`` keeps the
pre-cutover id that object keys and the vault key salt already use.

Downgrade drops ``object_prefix_id``. Do not downgrade after a subject has
been re-keyed: the object prefix would be lost while the bytes stay put.

Revision ID: 010_identity_rekey
Revises: 009_remove_archive
Create Date: 2026-11-25 19:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_identity_rekey"
down_revision: Union[str, None] = "009_remove_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_USER_FK_TABLES = ("file_records", "user_quota_usage", "upload_sessions")


def _user_fk_name(table: str) -> str:
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            JOIN pg_attribute att
              ON att.attrelid = rel.oid AND att.attnum = ANY (con.conkey)
            WHERE nsp.nspname = current_schema()
              AND rel.relname = :table
              AND con.contype = 'f'
              AND att.attname = 'user_id'
              AND con.confrelid = 'users'::regclass
            """
        ),
        {"table": table},
    ).scalar_one()


def _recreate_user_fk(table: str, *, onupdate: str) -> None:
    name = _user_fk_name(table)
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        name,
        table,
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
        onupdate=onupdate,
    )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("object_prefix_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE users SET object_prefix_id = id WHERE object_prefix_id IS NULL")
    op.alter_column("users", "object_prefix_id", nullable=False)
    for table in _USER_FK_TABLES:
        _recreate_user_fk(table, onupdate="CASCADE")


def downgrade() -> None:
    for table in reversed(_USER_FK_TABLES):
        _recreate_user_fk(table, onupdate="NO ACTION")
    op.drop_column("users", "object_prefix_id")
