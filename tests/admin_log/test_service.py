"""Тесты сервисного слоя admin-audit-log модуля."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import service as admin_service
from app.admin_log import service
from app.admin_log.constants import AdminAction, EntityType
from app.admin_log.models import AdminLogs


async def _make_admin(db_session: AsyncSession, email: str = "auditor@savory.ai"):
    """Создаёт минимального админа и коммитит — нужен для FK admin_id."""
    admin = await admin_service.create_admin(
        db_session,
        email=email,
        password="topsecret",
        name="Auditor",
    )
    await db_session.commit()
    return admin


async def test_log_action_creates_row_with_serialized_details(db_session: AsyncSession):
    """log_action сохраняет запись с правильными полями; details лежит в БД как dict (JSONB)."""
    admin = await _make_admin(db_session)

    details = {"status": "contacted", "phone": "+1"}
    log = await service.log_action(
        db_session,
        admin_id=admin.id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.ONBOARDING_REQUEST,
        entity_id=42,
        details=details,
        ip_address="10.0.0.1",
    )
    await db_session.commit()

    stmt = select(AdminLogs).where(AdminLogs.id == log.id)
    fetched = (await db_session.execute(stmt)).scalar_one()
    assert fetched.admin_id == admin.id
    assert fetched.action == "update"
    assert fetched.entity_type == "onboarding_request"
    assert fetched.entity_id == 42
    assert fetched.ip_address == "10.0.0.1"
    assert fetched.details == details
    assert fetched.created_at is not None


async def test_log_action_does_not_commit(db_session: AsyncSession, test_engine):
    """log_action делает flush, но не commit — без явного commit запись не сохранится."""
    admin = await _make_admin(db_session)

    await service.log_action(
        db_session,
        admin_id=admin.id,
        action=AdminAction.CREATE,
        entity_type=EntityType.LANGUAGE,
        entity_id=1,
        details={"code": "de"},
        ip_address=None,
    )
    # rollback — имитируем падение бизнес-операции после log_action.
    await db_session.rollback()

    # Открываем независимую сессию, проверяем, что в БД ничего не осталось.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as fresh:
        rows = (await fresh.execute(select(AdminLogs))).scalars().all()
        assert rows == []


async def test_log_action_with_none_details_writes_null(db_session: AsyncSession):
    """details=None → колонка NULL (не строка 'null')."""
    admin = await _make_admin(db_session)
    log = await service.log_action(
        db_session,
        admin_id=admin.id,
        action=AdminAction.DELETE,
        entity_type=EntityType.LANGUAGE,
        entity_id=1,
        details=None,
        ip_address=None,
    )
    await db_session.commit()

    stmt = select(AdminLogs).where(AdminLogs.id == log.id)
    fetched = (await db_session.execute(stmt)).scalar_one()
    assert fetched.details is None


async def test_list_logs_returns_total_and_attaches_admin_info(db_session: AsyncSession):
    """list_logs склеивает admin_name/email и считает total."""
    admin = await _make_admin(db_session, email="lister@savory.ai")
    for i in range(3):
        await service.log_action(
            db_session,
            admin_id=admin.id,
            action=AdminAction.UPDATE,
            entity_type=EntityType.SUPPORT_TICKET,
            entity_id=i,
            details={"i": i},
            ip_address="127.0.0.1",
        )
    await db_session.commit()

    items, total = await service.list_logs(db_session, page=1, page_size=10)
    assert total == 3
    assert len(items) == 3
    assert all(item["admin_email"] == "lister@savory.ai" for item in items)
    assert all(item["admin_name"] == "Auditor" for item in items)


async def test_list_logs_orders_by_created_at_desc(db_session: AsyncSession):
    """Сортировка — свежее наверху."""
    admin = await _make_admin(db_session)
    now = datetime.now(UTC)

    for offset in (2, 0, 1):
        log = AdminLogs(
            admin_id=admin.id,
            action="update",
            entity_type="support_ticket",
            entity_id=offset,
            details=None,
            ip_address=None,
            created_at=now - timedelta(minutes=offset),
            updated_at=now - timedelta(minutes=offset),
        )
        db_session.add(log)
    await db_session.commit()

    items, _ = await service.list_logs(db_session, page=1, page_size=10)
    entity_ids = [item["entity_id"] for item in items]
    # offset=0 — самое свежее, offset=2 — самое старое.
    assert entity_ids == [0, 1, 2]


async def test_list_logs_pagination(db_session: AsyncSession):
    """page=2, page_size=1 возвращает второй элемент."""
    admin = await _make_admin(db_session)
    for i in range(3):
        await service.log_action(
            db_session,
            admin_id=admin.id,
            action=AdminAction.UPDATE,
            entity_type=EntityType.LANGUAGE,
            entity_id=i,
            details={"i": i},
            ip_address=None,
        )
    await db_session.commit()

    items, total = await service.list_logs(db_session, page=2, page_size=1)
    assert total == 3
    assert len(items) == 1


async def test_list_logs_filter_by_admin_id(db_session: AsyncSession):
    """admin_id_filter возвращает только записи указанного админа."""
    a1 = await _make_admin(db_session, email="a1@savory.ai")
    a2 = await _make_admin(db_session, email="a2@savory.ai")
    await service.log_action(
        db_session,
        admin_id=a1.id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.SUPPORT_TICKET,
        entity_id=1,
        details=None,
        ip_address=None,
    )
    await service.log_action(
        db_session,
        admin_id=a2.id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.SUPPORT_TICKET,
        entity_id=2,
        details=None,
        ip_address=None,
    )
    await db_session.commit()

    items, total = await service.list_logs(db_session, page=1, page_size=10, admin_id_filter=a1.id)
    assert total == 1
    assert items[0]["admin_id"] == a1.id


async def test_list_logs_excludes_soft_deleted(db_session: AsyncSession):
    """deleted_at IS NOT NULL → запись скрыта от list_logs."""
    admin = await _make_admin(db_session)
    now = datetime.now(UTC)

    alive = AdminLogs(
        admin_id=admin.id,
        action="update",
        entity_type="support_ticket",
        entity_id=1,
        details=None,
        ip_address=None,
        created_at=now,
        updated_at=now,
    )
    deleted = AdminLogs(
        admin_id=admin.id,
        action="update",
        entity_type="support_ticket",
        entity_id=2,
        details=None,
        ip_address=None,
        created_at=now,
        updated_at=now,
        deleted_at=now,
    )
    db_session.add_all([alive, deleted])
    await db_session.commit()

    items, total = await service.list_logs(db_session, page=1, page_size=10)
    assert total == 1
    assert items[0]["entity_id"] == 1
