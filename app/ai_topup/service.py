"""Бизнес-логика модуля ai_topup.

Эталон — `app/subscriptions/service.py` (заявки на продление подписки).
Все мутации пишут аудит-запись в `admin_logs` ПЕРЕД commit'ом (общая
транзакция: упадёт бизнес — откатится и лог).

Approve блокирует строку заявки (`SELECT ... FOR UPDATE`) — защита от
double-approve той же заявки (Postgres сериализует; SQLite игнорирует, но
статус-гейт `pending` всё равно делает повтор идемпотентным).

Единственное место бизнес-логики апрува — расчёт `requests_granted`
(`packs_count * requests_per_pack`); размер пакета берётся из snapshot заявки,
не из конфига admin-сервиса.
"""

from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin_log import service as admin_log_service
from app.admin_log.constants import AdminAction, EntityType
from app.ai_topup.constants import TopUpRequestStatus
from app.ai_topup.exceptions import TopUpRequestNotFound, TopUpRequestNotPending
from app.ai_topup.helpers import next_month_start, now_utc, validate_no_null_bytes
from app.ai_topup.schemas import (
    ApproveTopUpRequestReq,
    ApproveTopUpResp,
    OrganizationShort,
    QuotaResp,
    RejectTopUpRequestReq,
    RestaurantShort,
    TopUpRequestResp,
    UserShort,
)
from app.common.utils.pagination import PaginationModel
from app.models import AIRequestQuotas, AIRequestTopUpRequests

# ---------- internal: mapping ----------


def _to_response(req: AIRequestTopUpRequests) -> TopUpRequestResp:
    """Маппинг ORM → Response. Невалидный статус из БД (legacy/ручной insert)
    мапим на `PENDING` вместо 500 — defensive.
    """
    try:
        status_enum = TopUpRequestStatus(req.status or TopUpRequestStatus.PENDING.value)
    except ValueError:
        status_enum = TopUpRequestStatus.PENDING

    return TopUpRequestResp(
        id=int(req.id),
        organization=OrganizationShort.model_validate(req.organization),
        restaurant=RestaurantShort.model_validate(req.restaurant),
        user=UserShort.model_validate(req.user),
        name=req.name,
        phone=req.phone,
        email=req.email,
        packs_count=int(req.packs_count),
        requests_per_pack=int(req.requests_per_pack),
        price_per_pack=float(req.price_per_pack),
        currency=req.currency,
        total_price=float(req.total_price),
        comment=req.comment,
        status=status_enum,
        admin_comment=req.admin_comment,
        created_at=req.created_at,
        processed_at=req.processed_at,
    )


# ---------- internal: lookups ----------


async def _get_request_loaded(
    db: AsyncSession, req_id: int, *, for_update: bool = False
) -> AIRequestTopUpRequests:
    """Заявка с eager-loaded organization + restaurant + user. 404 если нет/soft-deleted."""
    stmt = (
        select(AIRequestTopUpRequests)
        .options(
            selectinload(AIRequestTopUpRequests.organization),
            selectinload(AIRequestTopUpRequests.restaurant),
            selectinload(AIRequestTopUpRequests.user),
        )
        .where(
            AIRequestTopUpRequests.id == req_id,
            AIRequestTopUpRequests.deleted_at.is_(None),
        )
    )
    if for_update:
        stmt = stmt.with_for_update()
    req = (await db.scalars(stmt)).one_or_none()
    if req is None:
        raise TopUpRequestNotFound
    return req


# ---------- public API ----------


async def list_top_up_requests(
    db: AsyncSession,
    *,
    status: TopUpRequestStatus | None,
    organization_id: int | None,
    restaurant_id: int | None,
    pagination: PaginationModel,
) -> tuple[list[TopUpRequestResp], int]:
    """Список заявок. По дефолту в роутере фильтр `status=pending`. Сортировка `created_at DESC`."""
    filters: list[Any] = [AIRequestTopUpRequests.deleted_at.is_(None)]
    if status is not None:
        filters.append(AIRequestTopUpRequests.status == status.value)
    if organization_id is not None:
        filters.append(AIRequestTopUpRequests.organization_id == organization_id)
    if restaurant_id is not None:
        filters.append(AIRequestTopUpRequests.restaurant_id == restaurant_id)

    total = int(
        (
            await db.execute(
                select(func.count()).select_from(AIRequestTopUpRequests).where(and_(*filters))
            )
        ).scalar_one()
    )
    if total == 0:
        return [], 0

    stmt = (
        select(AIRequestTopUpRequests)
        .options(
            selectinload(AIRequestTopUpRequests.organization),
            selectinload(AIRequestTopUpRequests.restaurant),
            selectinload(AIRequestTopUpRequests.user),
        )
        .where(and_(*filters))
        .order_by(
            AIRequestTopUpRequests.created_at.desc(),
            AIRequestTopUpRequests.id.desc(),
        )
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    reqs = list((await db.scalars(stmt)).all())
    return [_to_response(r) for r in reqs], total


async def get_top_up_request(db: AsyncSession, req_id: int) -> TopUpRequestResp:
    req = await _get_request_loaded(db, req_id)
    return _to_response(req)


async def approve_top_up_request(
    db: AsyncSession,
    *,
    req_id: int,
    payload: ApproveTopUpRequestReq,
    admin_id: int,
    client_ip: str | None,
) -> ApproveTopUpResp:
    """Атомарно: заявка → `approved` И создаётся `ai_request_quotas`.

    `requests_granted = packs_count * requests_per_pack` (snapshot из заявки).
    `expires_at` = начало следующего календарного месяца (UTC) — квота сгорает.
    Один commit: бизнес или audit упал — откат всего.
    """
    validate_no_null_bytes(payload.admin_comment)

    request = await _get_request_loaded(db, req_id, for_update=True)
    if request.status != TopUpRequestStatus.PENDING.value:
        raise TopUpRequestNotPending

    now = now_utc()

    # 1) Меняем заявку.
    request.status = TopUpRequestStatus.APPROVED.value
    request.admin_comment = payload.admin_comment or ""
    request.processed_at = now
    request.updated_at = now

    # 2) Создаём квоту. requests_granted = packs_count * requests_per_pack (snapshot!).
    requests_granted = int(request.packs_count) * int(request.requests_per_pack)
    expires_at = next_month_start(now)
    quota = AIRequestQuotas(
        restaurant_id=request.restaurant_id,
        top_up_request_id=request.id,
        requests_granted=requests_granted,
        period_start=now,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    db.add(quota)
    await db.flush()

    # 3) Audit ПЕРЕД commit (общая транзакция).
    _ = await admin_log_service.log_action(
        db,
        admin_id=admin_id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.AI_TOPUP_REQUEST,
        entity_id=int(request.id),
        details={
            "status": TopUpRequestStatus.APPROVED.value,
            "requestsGranted": requests_granted,
            "restaurantId": int(request.restaurant_id),
            "expiresAt": expires_at.isoformat(),
        },
        ip_address=client_ip,
    )

    await db.commit()
    await db.refresh(request, attribute_names=["organization", "restaurant", "user"])

    return ApproveTopUpResp(
        top_up_request=_to_response(request),
        quota=QuotaResp(
            requests_granted=requests_granted,
            period_start=now,
            expires_at=expires_at,
        ),
    )


async def reject_top_up_request(
    db: AsyncSession,
    *,
    req_id: int,
    payload: RejectTopUpRequestReq,
    admin_id: int,
    client_ip: str | None,
) -> TopUpRequestResp:
    """Отклоняет pending-заявку. Квоту НЕ создаёт.

    Reject имеет смысл только из `pending` — иначе 409 `TopUpRequestNotPending`.
    """
    validate_no_null_bytes(payload.admin_comment)

    request = await _get_request_loaded(db, req_id, for_update=True)
    if request.status != TopUpRequestStatus.PENDING.value:
        raise TopUpRequestNotPending

    now = now_utc()
    request.status = TopUpRequestStatus.REJECTED.value
    request.admin_comment = payload.admin_comment or ""
    request.processed_at = now
    request.updated_at = now

    _ = await admin_log_service.log_action(
        db,
        admin_id=admin_id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.AI_TOPUP_REQUEST,
        entity_id=int(request.id),
        details={
            "status": TopUpRequestStatus.REJECTED.value,
            "restaurantId": int(request.restaurant_id),
        },
        ip_address=client_ip,
    )

    await db.commit()
    await db.refresh(request, attribute_names=["organization", "restaurant", "user"])
    return _to_response(request)
