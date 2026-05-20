"""Unit-тесты бизнес-логики `app/support/service.py`.

Гоняем напрямую функции сервиса на тестовой sqlite-сессии, без HTTP.
Покрываем:
- листинг (фильтр soft-deleted, сортировка по `updated_at DESC`, фильтр по статусу);
- get по id (успех, 404 на отсутствующий и на soft-deleted);
- patch (применение `exclude_unset`, 404 на отсутствующий).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.utils.pagination import PaginationModel
from app.models import SupportTickets
from app.support import service
from app.support.constants import TicketStatus
from app.support.exceptions import SupportTicketNotFound
from app.support.schemas import SupportTicketUpdateReq

from .conftest import TicketFactory

# Дефолтные параметры пагинации для тестов листинга — limit достаточный, чтобы
# не отрезать ни одну фикстуру.
DEFAULT_PAGINATION = PaginationModel(limit=100, offset=0)


async def test_list_returns_empty_when_no_tickets(db_session: AsyncSession):
    """Пустая таблица → пустой список (а не None и не исключение)."""
    result = await service.list_support_tickets(db_session, DEFAULT_PAGINATION)
    assert result == []


async def test_list_excludes_soft_deleted(db_session: AsyncSession, make_ticket: TicketFactory):
    """`deleted_at IS NOT NULL` — строка не должна возвращаться."""
    active = await make_ticket(status="new", title="active")
    await make_ticket(status="new", title="dead", deleted_at=datetime.now(tz=UTC))

    result = await service.list_support_tickets(db_session, DEFAULT_PAGINATION)

    ids = [t.id for t in result]
    assert ids == [active.id]


async def test_list_orders_by_updated_at_desc(db_session: AsyncSession, make_ticket: TicketFactory):
    """Сортировка `updated_at DESC` — самые свежие сверху."""
    now = datetime.now(tz=UTC)
    older = await make_ticket(status="new", updated_at=now - timedelta(hours=2))
    newest = await make_ticket(status="new", updated_at=now)
    middle = await make_ticket(status="new", updated_at=now - timedelta(hours=1))

    result = await service.list_support_tickets(db_session, DEFAULT_PAGINATION)

    assert [t.id for t in result] == [newest.id, middle.id, older.id]


async def test_list_filters_by_status(db_session: AsyncSession, make_ticket: TicketFactory):
    """Передан `status=in_progress` — возвращаются только тикеты с этим статусом."""
    await make_ticket(status="new", title="n1")
    in_progress = await make_ticket(status="in_progress", title="ip1")
    await make_ticket(status="completed", title="c1")

    result = await service.list_support_tickets(
        db_session, DEFAULT_PAGINATION, status=TicketStatus.IN_PROGRESS
    )

    assert [t.id for t in result] == [in_progress.id]


async def test_list_without_status_returns_all_statuses(
    db_session: AsyncSession, make_ticket: TicketFactory
):
    """`status=None` (или не передан) — возвращаются тикеты со всеми валидными статусами."""
    await make_ticket(status="new")
    await make_ticket(status="in_progress")
    await make_ticket(status="completed")

    result = await service.list_support_tickets(db_session, DEFAULT_PAGINATION, status=None)

    statuses = {t.status for t in result}
    assert statuses == {"new", "in_progress", "completed"}


async def test_get_returns_existing_ticket(db_session: AsyncSession, make_ticket: TicketFactory):
    """Базовый случай — получили тикет по id."""
    ticket = await make_ticket(status="new", title="findable")

    result = await service.get_support_ticket(db_session, ticket.id)

    assert result.id == ticket.id
    assert result.title == "findable"


async def test_get_raises_when_missing(db_session: AsyncSession):
    """Несуществующий id → `SupportTicketNotFound` (HTTP 404 в роутере)."""
    with pytest.raises(SupportTicketNotFound):
        await service.get_support_ticket(db_session, 999_999)


async def test_get_treats_soft_deleted_as_missing(
    db_session: AsyncSession, make_ticket: TicketFactory
):
    """Soft-deleted строка не должна выдаваться (контракт `deleted_at IS NULL`)."""
    ticket = await make_ticket(status="new", title="dead", deleted_at=datetime.now(tz=UTC))

    with pytest.raises(SupportTicketNotFound):
        await service.get_support_ticket(db_session, ticket.id)


async def test_update_changes_status_and_persists(
    db_session: AsyncSession, make_ticket: TicketFactory
):
    """Patch меняет статус, изменения коммитятся в БД."""
    ticket = await make_ticket(status="new")
    body = SupportTicketUpdateReq(status=TicketStatus.IN_PROGRESS)

    updated = await service.update_support_ticket(
        db_session, ticket.id, body, admin_id=1, client_ip=None
    )

    assert updated.id == ticket.id
    assert updated.status == "in_progress"

    # И в БД тоже — не только в Python-объекте.
    row = (
        await db_session.execute(select(SupportTickets).where(SupportTickets.id == ticket.id))
    ).scalar_one()
    assert row.status == "in_progress"


async def test_update_with_empty_body_is_noop(db_session: AsyncSession, make_ticket: TicketFactory):
    """`exclude_unset=True` — пустое тело не должно затирать существующий статус."""
    ticket = await make_ticket(status="completed")
    body = SupportTicketUpdateReq()  # status вообще не передан

    updated = await service.update_support_ticket(
        db_session, ticket.id, body, admin_id=1, client_ip=None
    )

    assert updated.status == "completed"


async def test_update_raises_when_missing(db_session: AsyncSession):
    """Patch несуществующего id → 404, без побочных эффектов."""
    body = SupportTicketUpdateReq(status=TicketStatus.IN_PROGRESS)

    with pytest.raises(SupportTicketNotFound):
        await service.update_support_ticket(db_session, 999_999, body, admin_id=1, client_ip=None)
