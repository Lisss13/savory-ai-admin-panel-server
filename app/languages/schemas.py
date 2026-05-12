"""Pydantic-схемы IO для языкового модуля.

Все поля JSON-ответов — camelCase (см. общий контракт API в `../CLAUDE.md`).
На вход допускаем оба варианта (`populate_by_name=True` в `CamelModel`).
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.languages.constants import (
    LANGUAGE_CODE_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
)
from app.schemas import CamelModel


class LanguageResponse(CamelModel):
    """Публичное представление языка."""

    id: int
    code: str
    name: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LanguageCreate(BaseModel):
    """Тело запроса создания языка.

    Код языка — ISO 639-1 lowercase (`en`, `ru`, `ar`). Регистр и пробелы
    отсекаются паттерном, чтобы в БД не попадали "EN" или "En".
    """

    code: str = Field(
        min_length=LANGUAGE_CODE_LENGTH,
        max_length=LANGUAGE_CODE_LENGTH,
        pattern=r"^[a-z]{2}$",
    )
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)


class LanguageDeleteResponse(CamelModel):
    """Ответ на удаление — возвращаем id удалённого языка."""

    id: int
