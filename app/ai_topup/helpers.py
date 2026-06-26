"""Чистые helper-функции модуля ai_topup (без обращений в БД).

Вынесены в отдельный модуль для удобства unit-тестирования (без фикстур с
AsyncSession) и ясного разделения «арифметика дат и валидация» vs «SQL».
"""

from datetime import UTC, datetime

from app.ai_topup.exceptions import InvalidStringCharacters


def now_utc() -> datetime:
    """Текущее время в UTC. Вынесено в helper для тестирования и единого `now`
    на всю транзакцию (передаётся параметром в нижестоящие функции)."""
    return datetime.now(UTC)


def next_month_start(now: datetime) -> datetime:
    """Начало следующего календарного месяца в UTC (00:00:00, 1-е число).

    Это `expires_at` выданной квоты — квота сгорает в конце текущего месяца.
    Корректно перескакивает через границу года (декабрь → январь).
    """
    year = now.year + (now.month == 12)
    month = now.month % 12 + 1
    return datetime(year, month, 1, tzinfo=UTC)


def validate_no_null_bytes(s: str | None) -> None:
    """Postgres не принимает NUL-байт в строковых полях — отсекаем заранее."""
    if s is not None and "\x00" in s:
        raise InvalidStringCharacters
