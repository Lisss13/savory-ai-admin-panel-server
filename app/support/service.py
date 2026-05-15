from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin_log import service as admin_log_service
from app.admin_log.constants import AdminAction, EntityType
from app.lib.logs.diff import calculate_diff
from app.models import SupportTickets
from app.support.constants import TicketStatus
from app.support.exceptions import SupportTicketNotFound
from app.support.schemas import SupportTicketUpdateReq


async def list_support_tickets(
    db: AsyncSession,
    status: TicketStatus | None = None,
) -> list[SupportTickets]:
    stmt = (
        select(SupportTickets)
        .options(selectinload(SupportTickets.user))
        .where(SupportTickets.deleted_at.is_(None))
        .order_by(SupportTickets.updated_at.desc())
    )
    if status is not None:
        stmt = stmt.where(SupportTickets.status == status)

    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_support_ticket(db: AsyncSession, ticket_id: int) -> SupportTickets:
    stmt = (
        select(SupportTickets)
        .options(selectinload(SupportTickets.user))
        .where(
            SupportTickets.id == ticket_id,
            SupportTickets.deleted_at.is_(None),
        )
    )
    res: SupportTickets | None = (await db.scalars(stmt)).one_or_none()
    if res is None:
        raise SupportTicketNotFound
    return res


async def update_support_ticket(
    db: AsyncSession,
    ticket_id: int,
    body: SupportTicketUpdateReq,
    *,
    admin_id: int,
    client_ip: str | None,
) -> SupportTickets:
    db_ticket: SupportTickets | None = await db.get(SupportTickets, ticket_id)
    if not db_ticket:
        raise SupportTicketNotFound

    update_data = body.model_dump(exclude_unset=True)
    before, after = calculate_diff(db_ticket, update_data)

    if before:
        db_ticket.updated_at = datetime.now(UTC)
        # Лог пишем перед commit — общая транзакция: упадёт бизнес, откатится и лог.
        await admin_log_service.log_action(
            db,
            admin_id=admin_id,
            action=AdminAction.UPDATE,
            entity_type=EntityType.SUPPORT_TICKET,
            entity_id=ticket_id,
            details={"before": before, "after": after},
            ip_address=client_ip,
        )

    await db.commit()
    await db.refresh(db_ticket, attribute_names=["user"])
    return db_ticket
