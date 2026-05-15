"""HTTP-эндпоинты языкового модуля.

Только для админа — все эндпоинты требуют валидный JWT с `role=admin`
(см. `CurrentAdmin`). Поведение по ошибкам — через доменные исключения
из `exceptions.py`, глобальный обработчик в `app/exceptions.py` приводит
их к envelope `{data, messages, code}`.
"""

from fastapi import APIRouter, status

from app.admin.dependencies import ClientIp, CurrentAdmin, DbSession
from app.languages import service
from app.languages.schemas import (
    LanguageCreate,
    LanguageDeleteResponse,
    LanguageResponse,
)
from app.schemas import Envelope

router = APIRouter(prefix="/languages", tags=["languages"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Список языков",
    description="Возвращает все активные (не soft-deleted) языки.",
    response_model=Envelope[list[LanguageResponse]],
)
async def get_languages(
    db: DbSession,
    _admin: CurrentAdmin,
) -> Envelope[list[LanguageResponse]]:
    languages = await service.list_languages(db)
    return Envelope(
        data=[LanguageResponse.model_validate(lang) for lang in languages],
        code=status.HTTP_200_OK,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать язык",
    description="Создаёт новый язык. `code` — ISO 639-1 (две lowercase-буквы). Дубликат — 409.",
    response_model=Envelope[LanguageResponse],
)
async def create_language(
    payload: LanguageCreate,
    db: DbSession,
    admin: CurrentAdmin,
    client_ip: ClientIp,
) -> Envelope[LanguageResponse]:
    language = await service.create_language(db, payload, admin_id=admin.id, client_ip=client_ip)
    return Envelope(data=LanguageResponse.model_validate(language), code=status.HTTP_201_CREATED)


@router.delete(
    "/{language_id}",
    status_code=status.HTTP_200_OK,
    summary="Удалить язык",
    description=(
        "Soft-удаляет язык (выставляет `deleted_at`). Удалить дефолтный язык (`en`) нельзя — 409."
    ),
    response_model=Envelope[LanguageDeleteResponse],
)
async def delete_language(
    language_id: int,
    db: DbSession,
    admin: CurrentAdmin,
    client_ip: ClientIp,
) -> Envelope[LanguageDeleteResponse]:
    language = await service.delete_language(
        db, language_id, admin_id=admin.id, client_ip=client_ip
    )
    return Envelope(
        data=LanguageDeleteResponse(id=language.id),
        code=status.HTTP_200_OK,
    )
