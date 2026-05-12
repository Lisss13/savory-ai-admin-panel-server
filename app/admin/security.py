"""Admin-specific тонкая обёртка над generic-крипто из `app/lib/security/`.

- Пароли: bcrypt-функции реэкспортируются из `app.lib.security.passwords`.
- JWT: `create_access_token` / `decode_access_token` подставляют значения из
  `admin_settings` и возвращают доменный `TokenPayload` / кидают доменный
  `InvalidToken`.
"""

from datetime import timedelta

from app.admin.config import admin_settings
from app.admin.exceptions import InvalidToken
from app.admin.schemas import TokenPayload
from app.lib.security import jwt as _jwt
from app.lib.security.passwords import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    verify_password,
)

__all__ = [
    "DUMMY_PASSWORD_HASH",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]


def create_access_token(subject: int, expires_in: timedelta | None = None) -> str:
    """Подписывает JWT с `sub=admin_id`. По умолчанию срок — из конфигурации."""
    if expires_in is None:
        expires_in = timedelta(minutes=admin_settings.jwt_expires_minutes)
    return _jwt.encode_token(
        subject=str(subject),
        secret=admin_settings.jwt_secret,
        algorithm=admin_settings.jwt_algorithm,
        expires_in=expires_in,
    )


def decode_access_token(token: str) -> TokenPayload:
    """Декодирует и валидирует токен. Любая ошибка → `InvalidToken`."""
    try:
        raw = _jwt.decode_token(
            token,
            secret=admin_settings.jwt_secret,
            algorithm=admin_settings.jwt_algorithm,
        )
    except _jwt.InvalidTokenError as exc:
        raise InvalidToken() from exc

    try:
        sub = int(raw["sub"])
        exp = int(raw["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidToken() from exc

    return TokenPayload(sub=sub, exp=exp)
