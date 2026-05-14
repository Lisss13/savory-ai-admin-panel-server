from fastapi import APIRouter
from fastapi import status as status_http

from app.admin.dependencies import CurrentAdmin
from app.database import DbSession
from app.schemas import Envelope
from app.support.constants import TicketStatus
from app.support.schemas import SupportTicketResp, SupportTicketUpdateReq
from app.support import service as svc

router = APIRouter(prefix="/support", tags=["support"])


@router.get(
    "",
    status_code=status_http.HTTP_200_OK,
    summary="Список тикетов поддержки",
    description="Возвращает все активные support tickets",
    response_model=Envelope[list[SupportTicketResp]],
)
async def get_support_tickets(
        _admin: CurrentAdmin,
        db: DbSession,
        status: TicketStatus | None = None,
) -> Envelope[list[SupportTicketResp]]:
    tickets = await svc.list_support_tickets(db, status)
    return Envelope(
        data=[SupportTicketResp.model_validate(t) for t in tickets],
        code=status_http.HTTP_200_OK,
    )


@router.get(
    "/{ticket_id}",
    status_code=status_http.HTTP_200_OK,
    summary="получить тикет поддержки по id",
)
async def get_support_ticket(
        _admin: CurrentAdmin,
        db: DbSession,
        ticket_id: int,
) -> Envelope[SupportTicketResp]:
    ticket = await svc.get_support_ticket(db, ticket_id)
    return Envelope(
        data=ticket,
        code=status_http.HTTP_200_OK,
    )


@router.patch(
    "/{ticket_id}",
    status_code=status_http.HTTP_200_OK,
    summary="Обновить тикет поддержки",
    description=(
            "Обновляет тикет по id из пути. "
            "Возвращает 404, если тикет не найден или soft-deleted."
    ),
)
async def patch_support_ticket(
        _admin: CurrentAdmin,
        db: DbSession,
        ticket_id: int,
        body: SupportTicketUpdateReq,
) -> Envelope[SupportTicketResp]:
    ticket = await svc.update_support_ticket(db, ticket_id, body)
    return Envelope(
        data=ticket,
        code=status_http.HTTP_200_OK,
    )
