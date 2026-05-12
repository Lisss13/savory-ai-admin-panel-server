"""Generic-обёртка над PyJWT для подписи/проверки access-токенов.

Не знает ни о каком домене: секрет, алгоритм и срок передаются параметрами.
Доменные обёртки (например, `app/admin/security.py`) подставляют свои
значения из settings и оборачивают доменные исключения.

`python-jose` НЕ используем — анти-паттерн.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as _pyjwt
from jwt.exceptions import InvalidTokenError

__all__ = ["InvalidTokenError", "decode_token", "encode_token"]


def encode_token(
    *,
    subject: str,
    secret: str,
    algorithm: str,
    expires_in: timedelta,
) -> str:
    """Подписывает JWT с `sub` и стандартными `iat`/`exp`."""
    now = datetime.now(tz=UTC)
    payload = {
        "sub": subject,
        "exp": int((now + expires_in).timestamp()),
        "iat": int(now.timestamp()),
    }
    return _pyjwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, *, secret: str, algorithm: str) -> dict[str, Any]:
    """Декодирует и валидирует токен. Кидает `InvalidTokenError` при любой проблеме."""
    return _pyjwt.decode(token, secret, algorithms=[algorithm])
