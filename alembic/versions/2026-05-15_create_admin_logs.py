"""create admin_logs table

Revision ID: 20260515_alogs
Revises: 20260512_audit
Create Date: 2026-05-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260515_alogs"
down_revision: str | Sequence[str] | None = "20260512_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Журнал админских действий. FK admin_id → admin.id (RESTRICT — следы не теряем)."""
    op.create_table(
        "admin_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admin.id"], ondelete="RESTRICT", name="admin_logs_admin_id_fkey"
        ),
    )
    op.create_index("admin_logs_admin_id_idx", "admin_logs", ["admin_id"])
    op.create_index("idx_admin_logs_created_at", "admin_logs", ["created_at"])
    op.create_index("idx_admin_logs_deleted_at", "admin_logs", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_admin_logs_deleted_at", table_name="admin_logs")
    op.drop_index("idx_admin_logs_created_at", table_name="admin_logs")
    op.drop_index("admin_logs_admin_id_idx", table_name="admin_logs")
    op.drop_table("admin_logs")
