"""Generic-утилиты для bcrypt-хеширования паролей.

Без passlib-обёртки — соль вшита в bcrypt-хеш, `verify_password` сам её
достаёт. Модуль не привязан ни к какому домену: используется из
`app/admin/security.py` и может переиспользоваться будущими auth-флоу.
"""

import bcrypt


def hash_password(password: str) -> str:
    """Возвращает bcrypt-хеш в utf-8 строке (с встроенной солью)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Заглушка для защиты от timing-attack: при аутентификации `verify_password`
# вызывается даже при отсутствии учётки. Хешируем один раз при импорте —
# стоимость bcrypt одинаковая в любом случае.
DUMMY_PASSWORD_HASH = hash_password("dummy-password-not-used")


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль. Мусорный хеш → `False` (а не исключение наружу)."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
