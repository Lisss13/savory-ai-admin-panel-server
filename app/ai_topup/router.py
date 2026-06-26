"""HTTP-эндпоинты модуля ai_topup.

Обработка заявок на докупку AI-запросов: список/деталь + approve/reject.
Все endpoints — admin-only через `CurrentAdmin`. Query-параметры в camelCase
(через `alias=`), JSON-поля — через `CamelModel`. Пагинация — `limit`/`offset`
(как во всём сервисе, см. `PaginationParams`).
"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.admin.dependencies import ClientIp, CurrentAdmin, DbSession
from app.ai_topup import service
from app.ai_topup.constants import TopUpRequestStatus
from app.ai_topup.schemas import (
    ApproveTopUpRequestReq,
    ApproveTopUpResp,
    RejectTopUpRequestReq,
    TopUpRequestResp,
)
from app.common.utils.pagination import PaginatedResponse, PaginationParams
from app.schemas import Envelope

router = APIRouter(prefix="/ai-topup", tags=["ai-topup"])


@router.get(
    "/requests",
    status_code=status.HTTP_200_OK,
    summary="Список заявок на докупку AI-запросов",
    description=(
        "Постраничный список. По умолчанию показывает только `pending` (очередь "
        "работы админа). Передайте `?status=approved|rejected` для конкретного "
        "статуса. Опционально — фильтры `organizationId`, `restaurantId`. "
        "Soft-deleted скрыты, сортировка `createdAt DESC`."
    ),
)
async def list_top_up_requests(
    _admin: CurrentAdmin,
    db: DbSession,
    pagination: PaginationParams,
    status_filter: Annotated[
        TopUpRequestStatus | None, Query(alias="status")
    ] = TopUpRequestStatus.PENDING,
    organization_id: Annotated[int | None, Query(alias="organizationId", gt=0)] = None,
    restaurant_id: Annotated[int | None, Query(alias="restaurantId", gt=0)] = None,
) -> Envelope[PaginatedResponse[TopUpRequestResp]]:
    items, total = await service.list_top_up_requests(
        db,
        status=status_filter,
        organization_id=organization_id,
        restaurant_id=restaurant_id,
        pagination=pagination,
    )
    return Envelope(
        data=PaginatedResponse[TopUpRequestResp](
            items=items, limit=pagination.limit, offset=pagination.offset, total=total
        ),
        code=status.HTTP_200_OK,
    )


@router.get(
    "/requests/{req_id}",
    status_code=status.HTTP_200_OK,
    summary="Получить заявку по id",
)
async def get_top_up_request(
    req_id: int,
    _admin: CurrentAdmin,
    db: DbSession,
) -> Envelope[TopUpRequestResp]:
    req = await service.get_top_up_request(db, req_id)
    return Envelope(data=req, code=status.HTTP_200_OK)


@router.post(
    "/requests/{req_id}/approve",
    status_code=status.HTTP_200_OK,
    summary="Одобрить заявку и выдать квоту",
    description=(
        "Атомарно: заявка → `approved`, создаётся `ai_request_quotas` с "
        "`requestsGranted = packsCount * requestsPerPack` и `expiresAt` = начало "
        "следующего месяца (UTC). Approve не-`pending` заявки → 409."
    ),
)
async def approve_top_up_request(
    req_id: int,
    body: ApproveTopUpRequestReq,
    admin: CurrentAdmin,
    db: DbSession,
    client_ip: ClientIp,
) -> Envelope[ApproveTopUpResp]:
    resp = await service.approve_top_up_request(
        db, req_id=req_id, payload=body, admin_id=admin.id, client_ip=client_ip
    )
    return Envelope(data=resp, code=status.HTTP_200_OK)


@router.post(
    "/requests/{req_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Отклонить заявку",
    description=(
        "Переводит pending-заявку в `rejected` с опциональным `adminComment`. "
        "Квоту не создаёт. Reject из не-`pending` статуса → 409."
    ),
)
async def reject_top_up_request(
    req_id: int,
    body: RejectTopUpRequestReq,
    admin: CurrentAdmin,
    db: DbSession,
    client_ip: ClientIp,
) -> Envelope[TopUpRequestResp]:
    req = await service.reject_top_up_request(
        db, req_id=req_id, payload=body, admin_id=admin.id, client_ip=client_ip
    )
    return Envelope(data=req, code=status.HTTP_200_OK)
