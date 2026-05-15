"""Pydantic-схемы IO для admin-audit-log модуля.

Внешний контракт — camelCase (см. ../CLAUDE.md, "Контракт API"). `details`
хранится в БД как JSONB и отдаётся клиенту dict без дополнительной обработки.
"""

from datetime import datetime
from typing import Any

from app.admin_log.constants import AdminAction, EntityType
from app.schemas import CamelModel


class AdminLogResp(CamelModel):
    """Запись журнала для read-API.

    `admin_name`/`admin_email` подтягиваются из таблицы `admin` сервисом
    одним батч-селектом — модель сама хранит только `admin_id`.
    """

    id: int
    admin_id: int
    admin_name: str | None = None
    admin_email: str | None = None
    action: AdminAction
    entity_type: EntityType | str
    entity_id: int | None = None
    details: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime


class AdminLogListResp(CamelModel):
    """Страница журнала."""

    items: list[AdminLogResp]
    page: int
    page_size: int
    total: int
