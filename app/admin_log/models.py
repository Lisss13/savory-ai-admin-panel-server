"""ORM-модели admin-audit-log модуля.

`AdminLogs` — журнал админских действий. FK ведёт на `admin.id` (см.
`app/admin/models.py`), не на `users.id`: в этом сервисе пользователей нет,
все админы лежат в собственной таблице `admin`.
"""

import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.admin.models import Admin
from app.models import Base

# BigInteger в Postgres, Integer в SQLite — иначе autoincrement в SQLite не работает.
_PK_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class AdminLogs(Base):
    """Журнал действий админа над сущностями системы."""

    __tablename__ = "admin_logs"
    __table_args__ = (
        Index("idx_admin_logs_created_at", "created_at"),
        Index("idx_admin_logs_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(
        _PK_TYPE,
        ForeignKey("admin.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int | None] = mapped_column(_PK_TYPE)
    details: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    ip_address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    admin: Mapped[Admin] = relationship(Admin)
