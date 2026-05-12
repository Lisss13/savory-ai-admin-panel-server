"""Бизнес-логика языкового модуля."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.languages.constants import DEFAULT_LANGUAGE_CODE
from app.languages.exceptions import (
    CannotDeleteDefaultLanguage,
    LanguageCodeAlreadyExists,
    LanguageNotFound,
)
from app.languages.schemas import LanguageCreate
from app.lib.database.soft_delete import soft_delete
from app.models import Languages


async def list_languages(db: AsyncSession) -> list[Languages]:
    """Возвращает все активные (не soft-deleted) языки в порядке id."""
    stmt = select(Languages).where(Languages.deleted_at.is_(None)).order_by(Languages.id)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_language(db: AsyncSession, language_id: int) -> Languages:
    """Возвращает активный язык по id. Отсутствие → `LanguageNotFound`."""
    stmt = select(Languages).where(Languages.id == language_id)
    res = await db.execute(stmt)
    language = res.scalar_one_or_none()
    if language is None:
        raise LanguageNotFound()
    return language


async def create_language(db: AsyncSession, payload: LanguageCreate) -> Languages:
    """Создаёт язык. Дубликат `code` → `LanguageCodeAlreadyExists` (409)."""
    now = datetime.now(UTC)
    language = Languages(
        **payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(language)
    try:
        await db.commit()
    except IntegrityError as exc:
        # UNIQUE(code) сломан — либо активным дубликатом, либо soft-deleted
        # с тем же code (т.к. индекс в схеме не partial — см. app/models.py).
        await db.rollback()
        raise LanguageCodeAlreadyExists() from exc
    await db.refresh(language)
    return language


async def delete_language(db: AsyncSession, language_id: int) -> Languages:
    """Soft-удаляет язык. Дефолтный (`en`) — `CannotDeleteDefaultLanguage` (409).

    Возвращает удалённую запись (с проставленным `deleted_at`), чтобы вызывающий
    мог отдать клиенту хотя бы `id`.
    """
    language = await get_language(db, language_id)
    if language.code == DEFAULT_LANGUAGE_CODE:
        raise CannotDeleteDefaultLanguage()
    soft_delete(language)
    await db.commit()
    await db.refresh(language)
    return language
