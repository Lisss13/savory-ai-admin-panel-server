"""Доменные исключения языкового модуля."""

from fastapi import status

from app.exceptions import AppException


class LanguageNotFound(AppException):
    """Язык с таким id не найден (или soft-deleted)."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "language not found"


class LanguageCodeAlreadyExists(AppException):
    """Активный язык с таким кодом уже есть — нарушен UNIQUE(code)."""

    status_code = status.HTTP_409_CONFLICT
    detail = "language code already exists"


class CannotDeleteDefaultLanguage(AppException):
    """Нельзя удалить дефолтный язык (`en`) — на него ссылаются другие сервисы."""

    status_code = status.HTTP_409_CONFLICT
    detail = "cannot delete default language"
