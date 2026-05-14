"""Доменные исключения модуля службы поддержки."""

from fastapi import status

from app.exceptions import AppException


class SupportTicketNotFound(AppException):
    """Тикет с таким id не найден (или soft-deleted)."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "support ticket not found"
