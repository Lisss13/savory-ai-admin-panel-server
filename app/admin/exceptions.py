"""Доменные исключения admin-модуля."""

from fastapi import status

from app.exceptions import AppException


class InvalidCredentials(AppException):
    """Логин или пароль не подходят (или админ деактивирован)."""

    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "invalid credentials"


class InvalidToken(AppException):
    """Bearer-токен отсутствует, повреждён, истёк или подписан чужим ключом."""

    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "invalid or expired token"


class AdminNotFound(AppException):
    """Админ с таким id/email не найден (используется в служебных путях, не в login)."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "admin not found"


class TooManyLoginAttempts(AppException):
    """Превышен лимит неудачных попыток входа для этого email."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "too many login attempts, try again later"
