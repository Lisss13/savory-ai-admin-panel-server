"""Хелпер для расчёта diff'а ORM-объекта при PATCH-эндпоинтах.

Используется сервисами, которые пишут в `admin_logs`: чтобы лог содержал и
старое, и новое значение в одной записи (`{before, after}`), и одновременно
чтобы повторный PATCH с тем же телом не плодил дубли в журнале.
"""

from typing import Any

from sqlalchemy.orm import DeclarativeBase


def calculate_diff(
    db_request: DeclarativeBase, update_data: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Сравнивает поля ORM-объекта с `update_data`, применяет изменения и возвращает diff.

    Делает три вещи за один проход:
    1. Считает `before` — старые значения **только тех** полей из `update_data`,
       что реально отличаются от текущих. Поля, где значение совпало, в diff
       не попадают (это спасает audit-лог от дубликатов при повторных PATCH'ах
       с тем же телом — двойной клик, retry с фронта и т.п.).
    2. Считает `after` — новые значения тех же изменившихся полей.
    3. Применяет `after` к `db_request` через `setattr`. SQLAlchemy сама
       отметит атрибуты как dirty и обновит строку при ближайшем `flush`.

    Возвращает `(before, after)`. Если оба пустые — реальных изменений нет,
    вызывающий код должен пропустить `log_action` и, при необходимости,
    не дёргать `updated_at`.

    Пример:
        >>> before, after = calculate_diff(ticket, {"status": "in_progress"})
        >>> # before == {"status": "new"}, after == {"status": "in_progress"}
        >>> # ticket.status уже выставлен в "in_progress"
    """
    before = {
        k: getattr(db_request, k) for k, v in update_data.items() if getattr(db_request, k) != v
    }
    after = {k: update_data[k] for k in before}
    for key, value in after.items():
        setattr(db_request, key, value)

    return before, after


def is_diff(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return bool(before or after)


def calculate_diff_dict(
    db_request: DeclarativeBase, update_data: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    before, after = calculate_diff(db_request, update_data)
    return {
        "before": before,
        "after": after,
    }
