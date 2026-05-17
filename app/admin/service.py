"""Бизнес-логика admin-модуля: CRUD, аутентификация, seed, audit log."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import security
from app.admin.config import admin_settings
from app.admin.exceptions import AdminNotFound, InvalidCredentials
from app.admin.models import Admin, AdminLoginLog


async def get_admin_by_email(db: AsyncSession, email: str) -> Admin | None:
    """Возвращает админа по email или `None` (без исключений — используется в логине)."""
    res = await db.execute(select(Admin).where(Admin.email == email))
    return res.scalar_one_or_none()


async def get_admin_by_id(db: AsyncSession, admin_id: int) -> Admin:
    """Возвращает админа по id. Отсутствие → `AdminNotFound`."""
    res = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = res.scalar_one_or_none()
    if admin is None:
        raise AdminNotFound()
    return admin


async def create_admin(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    name: str | None = None,
) -> Admin:
    """Создаёт админа с хешированным паролем. Без `commit` — это решение вызывающей стороны."""
    admin = Admin(
        email=email,
        password_hash=security.hash_password(password),
        name=name,
        is_active=True,
    )
    db.add(admin)
    await db.flush()
    await db.refresh(admin)
    return admin


async def add_new_admin(
    db: AsyncSession,
    email: str,
    password: str,
    name: str | None = None,
) -> Admin:
    admin = await create_admin(db, email=email, password=password, name=name)
    await db.commit()
    return admin


async def authenticate_admin(db: AsyncSession, *, email: str, password: str) -> Admin:
    """Проверяет пару email/пароль. Любая ошибка — единое `InvalidCredentials`.

    Защита от timing-attack: даже если админ не найден или деактивирован,
    мы ВСЁ РАВНО вызываем `verify_password` против `DUMMY_PASSWORD_HASH`,
    чтобы время ответа не зависело от существования учётки.
    """
    admin = await get_admin_by_email(db, email)
    candidate_hash = admin.password_hash if admin is not None else security.DUMMY_PASSWORD_HASH
    password_ok = security.verify_password(password, candidate_hash)

    if admin is None or not admin.is_active or not password_ok:
        raise InvalidCredentials()
    return admin


async def seed_default_admin(db: AsyncSession) -> Admin:
    """Создаёт bootstrap-админа из `[admin]` config.toml, если такого ещё нет.

    Идемпотентна и race-safe: если параллельный воркер уже вставил bootstrap,
    мы получим `IntegrityError` на UNIQUE(email) → откатываемся и возвращаем
    существующего.
    """
    existing = await get_admin_by_email(db, admin_settings.bootstrap_email)
    if existing is not None:
        return existing

    try:
        admin = await create_admin(
            db,
            email=admin_settings.bootstrap_email,
            password=admin_settings.bootstrap_password,
            name=admin_settings.bootstrap_name,
        )
        await db.commit()
    except IntegrityError:
        # Кто-то нас опередил между SELECT и INSERT — это нормально.
        await db.rollback()
        existing = await get_admin_by_email(db, admin_settings.bootstrap_email)
        if existing is None:
            # IntegrityError по другой причине — пробрасываем.
            raise
        return existing

    await db.refresh(admin)
    return admin


async def record_login_attempt(
    db: AsyncSession,
    *,
    email: str,
    success: bool,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    failure_reason: str | None = None,
) -> None:
    """Пишет попытку входа в `admin_login_log`. Коммитит транзакцию сам."""
    db.add(
        AdminLoginLog(
            admin_id=admin_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            failure_reason=failure_reason,
        )
    )
    await db.commit()
