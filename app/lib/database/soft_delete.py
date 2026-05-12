from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import ColumnElement
from sqlalchemy.orm import Mapped


class SoftDeletable(Protocol):
    """Контракт ORM-сущности, поддерживающей мягкое удаление.

    Атрибуты описаны runtime-типами (`datetime | None`), а не `Mapped[...]`:
    Protocol проверяет форму инстанса, а у инстанса дескриптор `Mapped[T]`
    раскрывается до `T`.
    """

    deleted_at: datetime | None
    updated_at: datetime | None


def soft_delete(instance: SoftDeletable) -> None:
    """Мягко удаляет ORM-объект: проставляет `deleted_at` и `updated_at` текущим UTC.

    `commit` не вызывается — это ответственность сервиса. Так можно мягко удалить
    несколько связанных сущностей в одной транзакции и единожды закоммитить.
    Перед вызовом убедись, что объект уже в сессии (получен через `select(...)`
    или добавлен `db.add()`).
    """
    now = datetime.now(UTC)
    instance.deleted_at = now
    instance.updated_at = now


def not_deleted(deleted_at_col: Mapped[datetime | None]) -> ColumnElement[bool]:
    """Возвращает условие WHERE для отбора только не удалённых записей.

    Принимает колонку, а не модель — так типобезопасно и не зависит от
    наличия конкретного атрибута у переданного класса.
    Пример: ``select(Languages).where(not_deleted(Languages.deleted_at))``.
    """
    return deleted_at_col.is_(None)
