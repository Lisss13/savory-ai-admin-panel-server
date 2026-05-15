"""Константы и enum's admin-audit-log модуля."""

from enum import StrEnum


class AdminAction(StrEnum):
    """Тип действия админа над сущностью.

    Подмножество Go-таксономии (`block/unblock/activate/deactivate` пока не
    используем — соответствующих эндпоинтов в FastAPI-сервисе ещё нет).
    """

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class EntityType(StrEnum):
    """Тип сущности, над которой админ совершил действие."""

    ONBOARDING_REQUEST = "onboarding_request"
    SUPPORT_TICKET = "support_ticket"
    LANGUAGE = "language"


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
