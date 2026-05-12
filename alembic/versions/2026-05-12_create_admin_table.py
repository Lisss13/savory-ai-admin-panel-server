"""create admin table

Revision ID: 20260512_admin
Revises:
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260512_admin"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт таблицу admin под bootstrap-учётку и JWT-аутентификацию.

    UNIQUE-ограничение на email уже создаёт btree-индекс в Postgres,
    поэтому отдельный `Index(...)` не нужен.
    """
    op.create_table(
        "admin",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("email", name="admin_email_key"),
    )


def downgrade() -> None:
    op.drop_table("admin")
