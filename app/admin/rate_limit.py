"""In-memory rate-limit для логина в админ-панель.

Ограничивает попытки входа на email: после `max_attempts` подряд неудачных
попыток в окне `window` адрес блокируется на `lockout`. Успешный логин
сбрасывает счётчик.

Ограничения:
- Состояние живёт в памяти процесса — при нескольких uvicorn-воркерах лимит
  считается **на воркер**, не глобально. Для уровня админ-панели (низкий
  трафик, один-два воркера) этого достаточно. Если понадобится глобально —
  заменить на Redis-backed реализацию того же интерфейса.
- Без блокировки/локов: операции достаточно короткие, GIL обеспечивает
  атомарность отдельных шагов; гонка может максимум сдвинуть счётчик на 1.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.admin.config import admin_settings
from app.admin.exceptions import TooManyLoginAttempts


class LoginRateLimiter:
    """In-memory per-email rate-limiter."""

    def __init__(self, max_attempts: int, window: timedelta, lockout: timedelta) -> None:
        self._max_attempts = max_attempts
        self._window = window
        self._lockout = lockout
        self._attempts: dict[str, list[datetime]] = defaultdict(list)
        self._lockouts: dict[str, datetime] = {}

    def check(self, key: str) -> None:
        """Бросает `TooManyLoginAttempts`, если ключ под блокировкой."""
        now = datetime.now(tz=UTC)
        until = self._lockouts.get(key)
        if until is not None and until > now:
            raise TooManyLoginAttempts()
        if until is not None:
            # Срок истёк — чистим, чтобы счётчик мог накопиться заново.
            self._lockouts.pop(key, None)

    def record_failure(self, key: str) -> None:
        """Регистрирует неудачную попытку. После `max_attempts` ставит lockout."""
        now = datetime.now(tz=UTC)
        window_start = now - self._window
        attempts = [a for a in self._attempts[key] if a > window_start]
        attempts.append(now)
        self._attempts[key] = attempts
        if len(attempts) >= self._max_attempts:
            self._lockouts[key] = now + self._lockout
            self._attempts[key] = []

    def record_success(self, key: str) -> None:
        """Успешный логин — сбрасываем все счётчики и блокировки для ключа."""
        self._attempts.pop(key, None)
        self._lockouts.pop(key, None)

    def reset(self) -> None:
        """Полный сброс — для тестов."""
        self._attempts.clear()
        self._lockouts.clear()


login_rate_limiter = LoginRateLimiter(
    max_attempts=admin_settings.login_max_attempts,
    window=timedelta(minutes=admin_settings.login_window_minutes),
    lockout=timedelta(minutes=admin_settings.login_lockout_minutes),
)
