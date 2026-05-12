"""HTTP-эндпоинты языкового модуля.

Только для админа — все эндпоинты требуют валидный JWT с `role=admin`
(см. `CurrentAdmin`). Поведение по ошибкам — через доменные исключения
из `exceptions.py`, глобальный обработчик в `app/exceptions.py` приводит
их к envelope `{data, messages, code}`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.dependencies import CurrentAdmin
from app.database import get_db
from app.languages import service
from app.languages.schemas import (
    LanguageCreate,
    LanguageDeleteResponse,
    LanguageResponse,
)
from app.schemas import Envelope

router = APIRouter(prefix="/languages", tags=["languages"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Список языков",
    description="Возвращает все активные (не soft-deleted) языки.",
)
async def get_languages(
    db: DbSession,
    _admin: CurrentAdmin,
) -> Envelope[list[LanguageResponse]]:
    languages = await service.list_languages(db)
    data = [LanguageResponse.model_validate(lang) for lang in languages]
    return Envelope(data=data, code=status.HTTP_200_OK)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать язык",
    description="Создаёт новый язык. `code` — ISO 639-1 (две lowercase-буквы). Дубликат — 409.",
)
async def create_language(
    payload: LanguageCreate,
    db: DbSession,
    _admin: CurrentAdmin,
) -> Envelope[LanguageResponse]:
    language = await service.create_language(db, payload)
    return Envelope(data=LanguageResponse.model_validate(language), code=status.HTTP_201_CREATED)


@router.delete(
    "/{language_id}",
    status_code=status.HTTP_200_OK,
    summary="Удалить язык",
    description=(
        "Soft-удаляет язык (выставляет `deleted_at`). Удалить дефолтный язык (`en`) нельзя — 409."
    ),
)
async def delete_language(
    language_id: int,
    db: DbSession,
    _admin: CurrentAdmin,
) -> Envelope[LanguageDeleteResponse]:
    language = await service.delete_language(db, language_id)
    return Envelope(
        data=LanguageDeleteResponse(id=language.id),
        code=status.HTTP_200_OK,
    )
