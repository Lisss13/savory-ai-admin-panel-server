"""Unit-тесты бизнес-логики языкового модуля.

Гоняем напрямую функции сервиса на тестовой sqlite-сессии, без HTTP.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.languages import service
from app.languages.exceptions import (
    CannotDeleteDefaultLanguage,
    LanguageCodeAlreadyExists,
    LanguageNotFound,
)
from app.languages.schemas import LanguageCreate
from app.models import Languages


async def test_create_language_persists_row_with_timestamps(db_session: AsyncSession):
    """Создание выставляет `created_at`/`updated_at` и возвращает свежий объект."""
    payload = LanguageCreate(code="fr", name="French", description="Français")
    language = await service.create_language(db_session, payload, admin_id=1, client_ip=None)

    assert language.id is not None
    assert language.code == "fr"
    assert language.name == "French"
    assert language.description == "Français"
    assert language.deleted_at is None
    assert language.created_at is not None
    assert language.updated_at is not None


async def test_create_language_rejects_duplicate_code(db_session: AsyncSession):
    """Повторный POST с тем же `code` → 409 `LanguageCodeAlreadyExists`."""
    await service.create_language(
        db_session, LanguageCreate(code="de", name="German"), admin_id=1, client_ip=None
    )

    with pytest.raises(LanguageCodeAlreadyExists):
        await service.create_language(
            db_session,
            LanguageCreate(code="de", name="Deutsch"),
            admin_id=1,
            client_ip=None,
        )


async def test_list_languages_returns_only_active(db_session: AsyncSession):
    """Soft-deleted записи не должны попадать в `list_languages`."""
    keep = await service.create_language(
        db_session, LanguageCreate(code="es", name="Spanish"), admin_id=1, client_ip=None
    )
    drop = await service.create_language(
        db_session, LanguageCreate(code="it", name="Italian"), admin_id=1, client_ip=None
    )
    await service.delete_language(db_session, drop.id, admin_id=1, client_ip=None)

    active = await service.list_languages(db_session)
    codes = {lang.code for lang in active}
    assert codes == {"es"}
    assert keep.id in {lang.id for lang in active}


async def test_get_language_raises_when_missing(db_session: AsyncSession):
    """Несуществующий id → `LanguageNotFound` (404)."""
    with pytest.raises(LanguageNotFound):
        await service.get_language(db_session, 999_999)


async def test_get_language_hides_soft_deleted(db_session: AsyncSession):
    """`get_language` отдаёт 404 для soft-deleted: повторный DELETE не должен плодить
    дублирующие лог-записи о «повторном удалении» уже удалённого языка.
    """
    lang = await service.create_language(
        db_session,
        LanguageCreate(code="pt", name="Portuguese"),
        admin_id=1,
        client_ip=None,
    )
    await service.delete_language(db_session, lang.id, admin_id=1, client_ip=None)

    with pytest.raises(LanguageNotFound):
        await service.get_language(db_session, lang.id)


async def test_delete_language_is_idempotent_404_on_repeat(db_session: AsyncSession):
    """Повторный DELETE → 404 и НЕ пишет второй admin_logs-запись (фикс дублирования)."""
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from app.admin_log.models import AdminLogs

    lang = await service.create_language(
        db_session,
        LanguageCreate(code="sw", name="Swahili"),
        admin_id=1,
        client_ip=None,
    )
    await service.delete_language(db_session, lang.id, admin_id=1, client_ip=None)
    logs_after_first = (
        await db_session.execute(
            sa_select(func.count())
            .select_from(AdminLogs)
            .where(AdminLogs.entity_type == "language", AdminLogs.action == "delete")
        )
    ).scalar_one()

    with pytest.raises(LanguageNotFound):
        await service.delete_language(db_session, lang.id, admin_id=1, client_ip=None)

    logs_after_second = (
        await db_session.execute(
            sa_select(func.count())
            .select_from(AdminLogs)
            .where(AdminLogs.entity_type == "language", AdminLogs.action == "delete")
        )
    ).scalar_one()
    assert logs_after_second == logs_after_first


async def test_delete_language_is_soft(db_session: AsyncSession):
    """`delete_language` не сносит строку, а выставляет `deleted_at`."""
    lang = await service.create_language(
        db_session,
        LanguageCreate(code="ja", name="Japanese"),
        admin_id=1,
        client_ip=None,
    )
    deleted = await service.delete_language(db_session, lang.id, admin_id=1, client_ip=None)

    assert deleted.id == lang.id
    assert deleted.deleted_at is not None

    # Физически запись осталась в таблице — это soft delete.
    raw = await db_session.execute(select(Languages).where(Languages.id == lang.id))
    row = raw.scalar_one()
    assert row.deleted_at is not None


async def test_delete_default_language_is_forbidden(db_session: AsyncSession):
    """Дефолтный `en` нельзя удалить — даже админом."""
    en = await service.create_language(
        db_session,
        LanguageCreate(code="en", name="English"),
        admin_id=1,
        client_ip=None,
    )

    with pytest.raises(CannotDeleteDefaultLanguage):
        await service.delete_language(db_session, en.id, admin_id=1, client_ip=None)

    # Запись осталась нетронутой.
    await db_session.refresh(en)
    assert en.deleted_at is None


async def test_delete_language_raises_when_missing(db_session: AsyncSession):
    """Удаление несуществующего id → 404, без побочных эффектов."""
    with pytest.raises(LanguageNotFound):
        await service.delete_language(db_session, 12345, admin_id=1, client_ip=None)
