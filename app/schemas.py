"""Общие схемы ответа для всего сервиса."""

from pydantic import BaseModel, Field


class Envelope[T](BaseModel):
    """Стандартный конверт ответа: `{data, messages, code}`.

    Единый контракт всех бэкендов Savory — фронт (Axios) ожидает именно
    эту форму как от Go-`server/`, так и от этого сервиса
    (см. ../CLAUDE.md, раздел "Контракт API").
    """

    data: T | None = None
    messages: list[str] = Field(default_factory=list)
    code: int = 200
