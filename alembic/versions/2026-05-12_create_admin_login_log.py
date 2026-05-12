"""create admin_login_log table

Revision ID: 20260512_audit
Revises: 20260512_admin
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260512_audit"
down_revision: str | Sequence[str] | None = "20260512_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Журнал попыток входа в админ-панель (успешных и неуспешных)."""
    op.create_table(
        "admin_login_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.BigInteger(), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admin.id"],
            ondelete="SET NULL",
            name="admin_login_log_admin_id_fkey",
        ),
    )
    op.create_index("admin_login_log_admin_id_idx", "admin_login_log", ["admin_id"])
    op.create_index("admin_login_log_email_idx", "admin_login_log", ["email"])
    op.create_index("admin_login_log_created_at_idx", "admin_login_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("admin_login_log_created_at_idx", table_name="admin_login_log")
    op.drop_index("admin_login_log_email_idx", table_name="admin_login_log")
    op.drop_index("admin_login_log_admin_id_idx", table_name="admin_login_log")
    op.drop_table("admin_login_log")
