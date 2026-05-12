"""ORM-модели admin-модуля.

- `Admin` — учётная запись администратора Savory (таблица `admin`).
- `AdminLoginLog` — журнал попыток входа (таблица `admin_login_log`).

Это отдельные сущности от `users` (см. `app/models.py`): пользователи —
ресторанные роли из Go-сервера, админы — сотрудники Savory с доступом к
глобальной админ-панели. Никакого FK на `users` сознательно нет.
"""

import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

# BigInteger в Postgres, Integer в SQLite — иначе autoincrement в SQLite не работает.
_PK_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class Admin(Base):
    """Учётная запись администратора Savory."""

    __tablename__ = "admin"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    # UNIQUE сам по себе создаёт btree-индекс в Postgres — `index=True` тут лишний.
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AdminLoginLog(Base):
    """Журнал попыток входа в админ-панель.

    Пишется всегда — и при успехе, и при провале (включая неизвестный email
    и срабатывание rate-limit). `admin_id` nullable: для неудачных попыток с
    неизвестным email вкладывать некуда.
    """

    __tablename__ = "admin_login_log"

    id: Mapped[int] = mapped_column(_PK_TYPE, primary_key=True, autoincrement=True)
    admin_id: Mapped[int | None] = mapped_column(
        _PK_TYPE,
        ForeignKey("admin.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
