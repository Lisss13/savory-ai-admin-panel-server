"""Бизнес-логика языкового модуля."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_log import service as admin_log_service
from app.admin_log.constants import AdminAction, EntityType
from app.common.database.soft_delete import soft_delete
from app.languages.constants import DEFAULT_LANGUAGE_CODE
from app.languages.exceptions import (
    CannotDeleteDefaultLanguage,
    LanguageCodeAlreadyExists,
    LanguageNotFound,
)
from app.languages.schemas import LanguageCreate
from app.models import Languages


async def list_languages(db: AsyncSession) -> list[Languages]:
    """Возвращает все активные (не soft-deleted) языки в порядке id."""
    stmt = select(Languages).where(Languages.deleted_at.is_(None)).order_by(Languages.id)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_language(db: AsyncSession, language_id: int) -> Languages:
    """Возвращает активный (не soft-deleted) язык по id. Отсутствие → `LanguageNotFound`.

    Фильтр по `deleted_at IS NULL` нужен в т.ч. для идемпотентности DELETE:
    повторный запрос на уже удалённый язык должен возвращать 404, а не плодить
    лог-записи о «повторном удалении».
    """
    stmt = select(Languages).where(Languages.id == language_id, Languages.deleted_at.is_(None))
    res = await db.execute(stmt)
    language = res.scalar_one_or_none()
    if language is None:
        raise LanguageNotFound()
    return language


async def create_language(
    db: AsyncSession,
    payload: LanguageCreate,
    *,
    admin_id: int,
    client_ip: str | None,
) -> Languages:
    now = datetime.now(UTC)
    language = Languages(
        **payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(language)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise LanguageCodeAlreadyExists() from exc

    await admin_log_service.log_action(
        db,
        admin_id=admin_id,
        action=AdminAction.CREATE,
        entity_type=EntityType.LANGUAGE,
        entity_id=language.id,
        # Единая форма details: before/after. У CREATE до — ничего, после — payload.
        details={"before": None, "after": payload.model_dump()},
        ip_address=client_ip,
    )
    await db.commit()
    await db.refresh(language)
    return language


async def delete_language(
    db: AsyncSession,
    language_id: int,
    *,
    admin_id: int,
    client_ip: str | None,
) -> Languages:
    language = await get_language(db, language_id)
    if language.code == DEFAULT_LANGUAGE_CODE:
        raise CannotDeleteDefaultLanguage()

    snapshot = {"code": language.code, "name": language.name}
    soft_delete(language)
    await admin_log_service.log_action(
        db,
        admin_id=admin_id,
        action=AdminAction.DELETE,
        entity_type=EntityType.LANGUAGE,
        entity_id=language.id,
        # Единая форма details: до удаления — снапшот, после — ничего.
        details={"before": snapshot, "after": None},
        ip_address=client_ip,
    )
    await db.commit()
    await db.refresh(language)
    return language
