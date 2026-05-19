"""Доменные исключения модуля subscriptions.

Все наследуют `AppException` — глобальный handler конвертирует их в envelope
`{data: null, messages: [detail], code: status_code}` (см. `app/exceptions.py`).
"""

from fastapi import status
from sqlalchemy.util.typing import final

from app.exceptions import AppException


@final
class SubscriptionNotFound(AppException):
    """Подписка не найдена или soft-deleted."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "subscription not found"


@final
class ExtensionRequestNotFound(AppException):
    """Заявка на продление не найдена или soft-deleted."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "extension request not found"


@final
class OrganizationNotFound(AppException):
    """Организация не найдена или soft-deleted (для create-subscription)."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "organization not found"


@final
class ExtensionRequestNotPending(AppException):
    """Approve можно делать только над заявкой в статусе `pending`."""

    status_code = status.HTTP_400_BAD_REQUEST
    detail = "extension request is not in pending status"


@final
class ExtensionPeriodRequired(AppException):
    """Approve без `endDateOverride` требует, чтобы у заявки был period>0."""

    status_code = status.HTTP_400_BAD_REQUEST
    detail = "extension request has no period and no endDateOverride provided"


@final
class InvalidEndDateOverride(AppException):
    """`endDateOverride` должен быть строго после start_date и после now."""

    status_code = status.HTTP_400_BAD_REQUEST
    detail = "end date override must be after start date and after now"


@final
class InvalidStringCharacters(AppException):
    """В строковом поле есть NUL-байт (0x00) — Postgres его не принимает."""

    status_code = status.HTTP_400_BAD_REQUEST
    detail = "invalid characters in request"
