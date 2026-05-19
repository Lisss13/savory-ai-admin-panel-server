"""HTTP-эндпоинты модуля subscriptions.

Два роутера в одном файле — `router` (`/admin/subscriptions`) и
`extension_requests_router` (`/subscriptions/extension-requests`). Approve
атомарно мутирует обе сущности, helper-ы общие — разносить по двум модулям
заставило бы cross-import.

Минимальный набор endpoints под админский UI:
- список + создание подписок (для отображения и ручного создания админом);
- список + детали заявок, reject и approve.

Все endpoints — admin-only через `CurrentAdmin`. Query-параметры в camelCase
(через `alias=`), JSON-поля — через `CamelModel`.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.admin.dependencies import ClientIp, CurrentAdmin, DbSession
from app.schemas import Envelope, PagedResp
from app.subscriptions import service
from app.subscriptions.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ExtensionRequestStatus,
)
from app.subscriptions.schemas import (
    ApproveExtensionRequestReq,
    ApproveExtensionResp,
    CreateSubscriptionReq,
    ExtensionRequestResp,
    RejectExtensionRequestReq,
    SubscriptionResp,
)

# ---------------------------------------------------------------------------
# /admin/subscriptions
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Список подписок",
    description=(
        "Постраничный список подписок с фильтрами. Soft-deleted скрыты. "
        "`expired=true` → `endDate < now`; `expired=false` → `endDate >= now`."
    ),
)
async def list_subscriptions(
    _admin: CurrentAdmin,
    db: DbSession,
    organization_id: Annotated[int | None, Query(alias="organizationId", gt=0)] = None,
    is_active: Annotated[bool | None, Query(alias="isActive")] = None,
    expired: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Envelope[PagedResp[SubscriptionResp]]:
    items, total = await service.list_subscriptions(
        db,
        organization_id=organization_id,
        is_active=is_active,
        expired=expired,
        page=page,
        page_size=page_size,
    )
    return Envelope(
        data=PagedResp[SubscriptionResp](items=items, page=page, page_size=page_size, total=total),
        code=status.HTTP_200_OK,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать подписку для организации",
    description=(
        "Создаёт подписку. Если `isActive` не указан или `true` — деактивирует "
        "существующую активную у той же организации (инвариант «≤ 1 активной»)."
    ),
)
async def create_subscription(
    body: CreateSubscriptionReq,
    admin: CurrentAdmin,
    db: DbSession,
    client_ip: ClientIp,
) -> Envelope[SubscriptionResp]:
    sub = await service.create_subscription(
        db, payload=body, admin_id=admin.id, client_ip=client_ip
    )
    return Envelope(data=sub, code=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# /subscriptions/extension-requests
# ---------------------------------------------------------------------------

extension_requests_router = APIRouter(
    prefix="/subscriptions/extension", tags=["subscription-extension"]
)


@extension_requests_router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Список заявок на продление",
    description=(
        "Постраничный список. По умолчанию показывает только `pending` (очередь "
        "работы админа). Передайте `?status=rejected|completed|approved` для "
        "конкретного статуса. Опционально — фильтр `organizationId`."
    ),
)
async def list_extension_requests(
    _admin: CurrentAdmin,
    db: DbSession,
    status_filter: Annotated[
        ExtensionRequestStatus | None, Query(alias="status")
    ] = ExtensionRequestStatus.PENDING,
    organization_id: Annotated[int | None, Query(alias="organizationId", gt=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Envelope[PagedResp[ExtensionRequestResp]]:
    items, total = await service.list_extension_requests(
        db,
        status=status_filter,
        organization_id=organization_id,
        page=page,
        page_size=page_size,
    )
    return Envelope(
        data=PagedResp[ExtensionRequestResp](
            items=items, page=page, page_size=page_size, total=total
        ),
        code=status.HTTP_200_OK,
    )


@extension_requests_router.get(
    "/{req_id}",
    status_code=status.HTTP_200_OK,
    summary="Получить заявку по id",
)
async def get_extension_request(
    req_id: int,
    _admin: CurrentAdmin,
    db: DbSession,
) -> Envelope[ExtensionRequestResp]:
    req = await service.get_extension_request(db, req_id)
    return Envelope(data=req, code=status.HTTP_200_OK)


@extension_requests_router.post(
    "/{req_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Отклонить заявку",
    description=(
        "Переводит pending-заявку в `rejected` с опциональным `adminComment`. "
        "Подписку не трогает. Reject из не-pending статуса → 400."
    ),
)
async def reject_extension_request(
    req_id: int,
    body: RejectExtensionRequestReq,
    admin: CurrentAdmin,
    db: DbSession,
    client_ip: ClientIp,
) -> Envelope[ExtensionRequestResp]:
    req = await service.reject_extension_request(
        db, req_id=req_id, payload=body, admin_id=admin.id, client_ip=client_ip
    )
    return Envelope(data=req, code=status.HTTP_200_OK)


@extension_requests_router.post(
    "/{req_id}/approve",
    status_code=status.HTTP_200_OK,
    summary="Одобрить заявку и продлить/создать подписку",
    description=(
        "Атомарно: заявка → `completed`, подписка продлена (`seamless`) или создана "
        "новая (`immediate`). При `seamless` без активной — фолбэк в `immediate_new`; "
        "фактический режим возвращается в `mode` ответа."
    ),
)
async def approve_extension_request(
    req_id: int,
    body: ApproveExtensionRequestReq,
    admin: CurrentAdmin,
    db: DbSession,
    client_ip: ClientIp,
) -> Envelope[ApproveExtensionResp]:
    resp = await service.approve_extension_request(
        db, req_id=req_id, payload=body, admin_id=admin.id, client_ip=client_ip
    )
    return Envelope(data=resp, code=status.HTTP_200_OK)
