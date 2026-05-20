"""Чистые helper-функции модуля subscriptions (без обращений в БД).

Вынесены в отдельный модуль для:
- разгрузки `service.py` (там осталась только бизнес-оркестрация);
- удобства unit-тестирования (без фикстур с AsyncSession);
- ясного разделения «чистая арифметика и валидация» vs «SQL-запросы».
"""

import calendar
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.orm import Mapped

from app.subscriptions.exceptions import (
    InvalidEndDateOverride,
    InvalidStringCharacters,
)


def now_utc() -> datetime:
    """Текущее время в UTC. Вынесено в helper для тестирования и единого `now`
    на всю транзакцию (передаётся параметром в нижестоящие функции)."""
    return datetime.now(UTC)


def ensure_aware_utc(dt: datetime) -> datetime:
    """Naive (из SQLite) → aware UTC; aware с другой TZ → конверсия в UTC.

    Компенсация различий Postgres vs SQLite: Postgres сохраняет tzinfo,
    SQLite его теряет (DateTime(timezone=True) для aiosqlite даёт naive).
    """
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def add_months(dt: datetime, months: int) -> datetime:
    """Прибавляет N месяцев. Clamp дня к последнему дню целевого месяца.

    Паритет с Go `time.AddDate(0, months, 0)`: 31 янв + 1 мес → 28/29 фев,
    31 мая + 1 мес → 30 июн. tzinfo сохраняется.
    """
    if months == 0:
        return dt
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def resolve_limit(*, override: int | None, requested: int | None, fallback: int) -> int:
    """Приоритет: override > requested(>0) > fallback. Использует approve."""
    if override is not None and override > 0:
        return override
    if requested is not None and requested > 0:
        return requested
    return fallback


def compute_new_end_date(
    *, override: datetime | None, base: datetime, period_months: int
) -> datetime:
    """Считает финальный `endDate` для approve.

    Если задан `override` — он становится окончательной правдой.
    Иначе — `base + period_months` через `add_months`.

    `base` — это `active_sub.end_date` (для seamless) или `now` (для immediate);
    разница в base зашита в вызывающем коде.
    """
    if override is not None:
        return ensure_aware_utc(override)
    return add_months(ensure_aware_utc(base), period_months)


def validate_end_date_override(override: datetime | None, start: datetime, now: datetime) -> None:
    """Если override задан — должен быть строго > start и > now."""
    if override is None:
        return
    override_aware = ensure_aware_utc(override)
    if override_aware <= ensure_aware_utc(start) or override_aware <= now:
        raise InvalidEndDateOverride


def validate_no_null_bytes(s: str | None) -> None:
    """Postgres не принимает NUL-байт в строковых полях — отсекаем заранее."""
    if s is not None and "\x00" in s:
        raise InvalidStringCharacters


def is_active_truthy(col: Mapped[bool | None]) -> ColumnElement[bool]:
    """SQL-фильтр «подписка считается активной».

    В БД `is_active` nullable с server_default=true; NULL трактуем как `True`
    (как сделал бы Postgres-default), поэтому фильтр — `IS NOT FALSE`.
    Используется и для `WHERE is_active=?` и для `_deactivate_active_for_org`.
    """
    return col.is_not(False)


def is_active_falsy(col: Mapped[bool | None]) -> ColumnElement[bool]:
    """SQL-фильтр «подписка явно неактивна» — `IS FALSE`. NULL → не подходит."""
    return col.is_(False)


def jsonify(value: object) -> Any:
    """Готовит значение к записи в `admin_logs.details` (JSON-колонка).

    `datetime` → ISO-8601 строка; вложенные dict/list проходятся рекурсивно.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonify(v) for v in value]
    return value
