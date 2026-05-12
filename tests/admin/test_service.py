"""Тесты `app.admin.service`: CRUD, authenticate, seed."""

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import security, service
from app.admin.exceptions import AdminNotFound, InvalidCredentials
from app.admin.models import Admin


async def test_create_admin_hashes_password_and_persists(db_session: AsyncSession):
    """`create_admin` сохраняет админа с захешированным паролем."""
    admin = await service.create_admin(
        db_session,
        email="root@savory.ai",
        password="secret123",
        name="Root",
    )
    await db_session.commit()

    assert admin.id is not None
    assert admin.email == "root@savory.ai"
    assert admin.name == "Root"
    # Пароль в БД — это хеш, а не plain-text.
    assert admin.password_hash != "secret123"
    assert admin.password_hash.startswith("$2")  # bcrypt префикс
    assert admin.is_active is True


async def test_authenticate_admin_returns_admin_for_valid_credentials(db_session: AsyncSession):
    """Корректные креды → возвращается админ."""
    await service.create_admin(db_session, email="a@b.c", password="pwd", name="A")
    await db_session.commit()

    admin = await service.authenticate_admin(db_session, email="a@b.c", password="pwd")
    assert admin.email == "a@b.c"


async def test_authenticate_admin_raises_for_wrong_password(db_session: AsyncSession):
    """Неверный пароль → `InvalidCredentials`."""
    await service.create_admin(db_session, email="a@b.c", password="pwd", name="A")
    await db_session.commit()

    with pytest.raises(InvalidCredentials):
        await service.authenticate_admin(db_session, email="a@b.c", password="WRONG")


async def test_authenticate_admin_raises_for_unknown_email(db_session: AsyncSession):
    """Неизвестный email → `InvalidCredentials` (не `AdminNotFound` — это login)."""
    with pytest.raises(InvalidCredentials):
        await service.authenticate_admin(db_session, email="ghost@x.y", password="pwd")


async def test_authenticate_admin_runs_verify_for_unknown_email(db_session: AsyncSession):
    """Защита от timing-attack: для неизвестного email тоже считаем bcrypt.

    Без этого время ответа выдаёт, существует ли учётка. Проверяем, что
    `verify_password` всё-таки был вызван — через мок.
    """
    with patch.object(security, "verify_password", wraps=security.verify_password) as spy:
        with pytest.raises(InvalidCredentials):
            await service.authenticate_admin(db_session, email="ghost@x.y", password="pwd")
    assert spy.called, "verify_password должен вызываться даже для несуществующего email"


async def test_authenticate_admin_raises_for_inactive_admin(db_session: AsyncSession):
    """Неактивный админ не должен логиниться, даже с корректным паролем."""
    admin = await service.create_admin(db_session, email="a@b.c", password="pwd", name="A")
    admin.is_active = False
    await db_session.commit()

    with pytest.raises(InvalidCredentials):
        await service.authenticate_admin(db_session, email="a@b.c", password="pwd")


async def test_get_admin_by_id_returns_admin(db_session: AsyncSession):
    """`get_admin_by_id` возвращает админа по id."""
    created = await service.create_admin(db_session, email="a@b.c", password="pwd", name="A")
    await db_session.commit()

    fetched = await service.get_admin_by_id(db_session, created.id)
    assert fetched.id == created.id
    assert fetched.email == "a@b.c"


async def test_get_admin_by_id_raises_when_missing(db_session: AsyncSession):
    """Отсутствующий админ → `AdminNotFound`."""
    with pytest.raises(AdminNotFound):
        await service.get_admin_by_id(db_session, 999_999)


async def test_seed_default_admin_creates_when_absent(db_session: AsyncSession):
    """`seed_default_admin` создаёт админа, если его нет."""
    await service.seed_default_admin(db_session)

    res = await db_session.execute(select(Admin))
    admins = res.scalars().all()
    assert len(admins) == 1


async def test_seed_default_admin_is_idempotent(db_session: AsyncSession):
    """Повторный вызов `seed_default_admin` не должен плодить дубликаты."""
    await service.seed_default_admin(db_session)
    await service.seed_default_admin(db_session)

    res = await db_session.execute(select(Admin))
    admins = res.scalars().all()
    assert len(admins) == 1


async def test_seed_default_admin_survives_concurrent_insert(db_session: AsyncSession, test_engine):
    """Гонка двух воркеров: пока мы проверяли «есть ли админ», параллельная
    транзакция уже вставила запись. На UNIQUE-конфликте seed должен откатиться
    и вернуть существующего админа, а не упасть.
    """
    from app.admin.config import admin_settings

    # Имитируем «другого воркера»: вставляем bootstrap-админа отдельной сессией
    # ПОСЛЕ того, как наш seed уже прочитал «никого нет».
    real_get = service.get_admin_by_email

    inserted = {"done": False}

    async def fake_get(db, email):
        result = await real_get(db, email)
        if not inserted["done"] and email == admin_settings.bootstrap_email:
            # «Другой воркер» проскочил между нашим SELECT и INSERT.
            async_session_factory = __import__(
                "sqlalchemy.ext.asyncio", fromlist=["async_sessionmaker"]
            ).async_sessionmaker
            sf = async_session_factory(test_engine, expire_on_commit=False)
            async with sf() as other:
                await service.create_admin(
                    other,
                    email=admin_settings.bootstrap_email,
                    password="x",
                    name="conflict",
                )
                await other.commit()
            inserted["done"] = True
        return result

    with patch.object(service, "get_admin_by_email", side_effect=fake_get):
        admin = await service.seed_default_admin(db_session)

    assert admin is not None
    res = await db_session.execute(select(Admin))
    admins = res.scalars().all()
    assert len(admins) == 1
