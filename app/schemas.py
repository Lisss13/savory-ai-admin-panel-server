"""Общие схемы ответа для всего сервиса."""

from pydantic import BaseModel, ConfigDict, Field


class Envelope[T](BaseModel):
    """Стандартный конверт ответа: `{data, messages, code}`.

    Единый контракт всех бэкендов Savory — фронт (Axios) ожидает именно
    эту форму как от Go-`server/`, так и от этого сервиса
    (см. ../CLAUDE.md, раздел "Контракт API").
    """

    data: T | None = None
    messages: list[str] = Field(default_factory=list)
    code: int = 200


def to_camel(s: str) -> str:
    """`snake_case` → `camelCase`. Используется как `alias_generator` для Response-схем."""
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


class CamelModel(BaseModel):
    """Базовая Response-модель: JSON-поля в camelCase, ORM-объекты читаются по атрибутам.

    Контракт воркспейса: новые поля в API — camelCase (`createdAt`, `userId`).
    `populate_by_name=True` оставляет возможность принимать и snake_case на вход.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )


# class PagedResp[T](CamelModel):
#     """Универсальный формат страницы списка: `{items, page, pageSize, total}`.

#     Используется везде, где нужна пагинация — единая форма для admin-фронта,
#     избавляет от копирования одинаковой структуры в каждый модуль.
#     """

#     items: list[T]
#     page: int
#     page_size: int
#     total: int
