"""Доменные исключения модуля ai_topup.

Все наследуют `AppException` — глобальный handler конвертирует их в envelope
`{data: null, messages: [detail], code: status_code}` (см. `app/exceptions.py`).
"""

from fastapi import status
from sqlalchemy.util.typing import final

from app.exceptions import AppException


@final
class TopUpRequestNotFound(AppException):
    """Заявка на докупку не найдена или soft-deleted."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "top-up request not found"


@final
class TopUpRequestNotPending(AppException):
    """Approve/Reject можно делать только над заявкой в статусе `pending`."""

    status_code = status.HTTP_409_CONFLICT
    detail = "top-up request is not in pending status"


@final
class InvalidStringCharacters(AppException):
    """В строковом поле есть NUL-байт (0x00) — Postgres его не принимает."""

    status_code = status.HTTP_400_BAD_REQUEST
    detail = "invalid characters in request"
