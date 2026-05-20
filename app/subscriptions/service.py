"""Бизнес-логика модуля subscriptions.

Все мутации:
- пишут аудит-запись в `admin_logs` ПЕРЕД commit'ом (общая транзакция:
  упадёт бизнес — откатится и лог);
- держат инвариант «у организации ≤ 1 активной подписки» в `create_subscription`
  и в `approve_extension_request` IMMEDIATE_NEW.

Concurrency-защита: `_get_organization(for_update=True)` в начале мутаций
блокирует строку организации до конца транзакции — два параллельных запроса
на одну орг сериализуются (Postgres `SELECT ... FOR UPDATE`; SQLite игнорирует).
Это исключает race, при котором два POST/approve создают две активные подписки.

Approve дополнительно блокирует строку заявки (`SELECT ... FOR UPDATE`) —
защита от double-approve той же заявки.

Чистые helper-функции (арифметика дат, валидация) — в `helpers.py`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.admin_log import service as admin_log_service
from app.admin_log.constants import AdminAction, EntityType
from app.common.utils.pagination import PaginationModel
from app.models import (
    Organizations,
    Restaurants,
    SubscriptionExtensionRequests,
    Subscriptions,
)
from app.subscriptions.constants import (
    DEFAULT_RESTAURANT_LIMIT,
    EffectiveApprovalMode,
    ExtensionRequestStatus,
    SubscriptionApprovalMode,
)
from app.subscriptions.exceptions import (
    ExtensionPeriodRequired,
    ExtensionRequestNotFound,
    ExtensionRequestNotPending,
    OrganizationNotFound,
)
from app.subscriptions.helpers import (
    add_months,
    compute_new_end_date,
    ensure_aware_utc,
    is_active_falsy,
    is_active_truthy,
    jsonify,
    now_utc,
    resolve_limit,
    validate_end_date_override,
    validate_no_null_bytes,
)
from app.subscriptions.schemas import (
    ApproveExtensionRequestReq,
    ApproveExtensionResp,
    CreateSubscriptionReq,
    ExtensionRequestResp,
    OrganizationShort,
    RejectExtensionRequestReq,
    SubscriptionResp,
    UserShort,
)

# ---------- internal: detail builders ----------


def _subscription_to_detail(
    sub: Subscriptions,
    *,
    now: datetime,
    total_restaurants: int,
    active_restaurants: int,
) -> SubscriptionResp:
    """Собирает `SubscriptionResp` с агрегатами по ресторанам.

    Агрегаты считает вызывающий — `_subscription_to_detail` чистая трансформация.
    `now` приходит снаружи — один и тот же на всю транзакцию, чтобы `days_left`
    был стабилен для всех items в списке (нет дрейфа микросекунд).
    """
    end_aware = ensure_aware_utc(sub.end_date)
    days_left = max(0, int((end_aware - now).total_seconds() // 86400))
    is_expired = end_aware < now

    return SubscriptionResp(
        id=int(sub.id),
        organization=OrganizationShort.model_validate(sub.organization),
        period=int(sub.period),
        start_date=sub.start_date,
        end_date=sub.end_date,
        # NULL в БД (server_default=true) трактуем как True — согласовано с
        # фильтром `is_active_truthy` для запросов.
        is_active=sub.is_active is not False,
        restaurant_limit=int(sub.restaurant_limit or DEFAULT_RESTAURANT_LIMIT),
        active_restaurants=active_restaurants,
        total_restaurants=total_restaurants,
        days_left=days_left,
        is_expired=is_expired,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


async def _build_subscription_detail(
    db: AsyncSession, sub: Subscriptions, *, now: datetime
) -> SubscriptionResp:
    """Подсчитывает агрегаты ресторанов для одной подписки и собирает Response.

    Используется в одиночных запросах (create / approve), где batch JOIN
    лишний — берём отдельным SELECT по organization_id.
    """
    stmt = select(
        func.count(Restaurants.id).label("total"),
        func.count(Restaurants.id).filter(Restaurants.is_active.is_(True)).label("active"),
    ).where(
        Restaurants.organization_id == sub.organization_id,
        Restaurants.deleted_at.is_(None),
    )
    row = (await db.execute(stmt)).one()
    return _subscription_to_detail(
        sub,
        now=now,
        total_restaurants=int(row.total or 0),
        active_restaurants=int(row.active or 0),
    )


def _request_to_resp(req: SubscriptionExtensionRequests) -> ExtensionRequestResp:
    """Маппинг ORM → Response. Невалидный статус из БД (legacy/ручной insert)
    мапим на `PENDING` вместо 500 — defensive.
    """
    try:
        status_enum = ExtensionRequestStatus(req.status or ExtensionRequestStatus.PENDING.value)
    except ValueError:
        status_enum = ExtensionRequestStatus.PENDING

    return ExtensionRequestResp(
        id=int(req.id),
        organization=OrganizationShort.model_validate(req.organization),
        user=UserShort.model_validate(req.user),
        name=req.name,
        phone=req.phone,
        email=req.email,
        period=req.period,
        requested_restaurant_limit=req.requested_restaurant_limit,
        comment=req.comment,
        status=status_enum,
        admin_comment=req.admin_comment,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


# ---------- internal: lookups ----------


async def _get_organization(
    db: AsyncSession, org_id: int, *, for_update: bool = False
) -> Organizations:
    """Загружает организацию. `for_update=True` блокирует строку до конца
    транзакции — используется в мутациях для сериализации параллельных запросов
    на одну орг (защита инварианта «≤ 1 активной подписки»).
    """
    stmt = select(Organizations).where(
        Organizations.id == org_id, Organizations.deleted_at.is_(None)
    )
    if for_update:
        stmt = stmt.with_for_update()
    org = (await db.scalars(stmt)).one_or_none()
    if org is None:
        raise OrganizationNotFound
    return org


async def _find_active_subscription(
    db: AsyncSession, organization_id: int, *, for_update: bool = False
) -> Subscriptions | None:
    """Активная подписка организации (`is_active IS NOT FALSE`, не soft-deleted)."""
    stmt = (
        select(Subscriptions)
        .options(selectinload(Subscriptions.organization))
        .where(
            Subscriptions.organization_id == organization_id,
            is_active_truthy(Subscriptions.is_active),
            Subscriptions.deleted_at.is_(None),
        )
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.scalars(stmt)).one_or_none()


async def _deactivate_active_for_org(
    db: AsyncSession,
    organization_id: int,
    *,
    now: datetime,
) -> None:
    """Деактивирует все «активные» (`is_active IS NOT FALSE`) подписки орг.

    Поддерживает инвариант «у орг ≤ 1 активной» — вызывается из
    `create_subscription` и `approve` IMMEDIATE_NEW. Конкурентов в этот же
    момент защищает `_get_organization(for_update=True)` на orgID.
    """
    _ = await db.execute(
        update(Subscriptions)
        .where(
            Subscriptions.organization_id == organization_id,
            is_active_truthy(Subscriptions.is_active),
            Subscriptions.deleted_at.is_(None),
        )
        .values(is_active=False, updated_at=now)
    )


async def _get_extension_request_loaded(
    db: AsyncSession, req_id: int, *, for_update: bool = False
) -> SubscriptionExtensionRequests:
    """Заявка с eager-loaded organization + user. 404 если нет/soft-deleted."""
    stmt = (
        select(SubscriptionExtensionRequests)
        .options(
            selectinload(SubscriptionExtensionRequests.organization),
            selectinload(SubscriptionExtensionRequests.user),
        )
        .where(
            SubscriptionExtensionRequests.id == req_id,
            SubscriptionExtensionRequests.deleted_at.is_(None),
        )
    )
    if for_update:
        stmt = stmt.with_for_update()
    req = (await db.scalars(stmt)).one_or_none()
    if req is None:
        raise ExtensionRequestNotFound
    return req


# ---------- subscriptions: public API ----------


async def list_subscriptions(
    db: AsyncSession,
    *,
    organization_id: int | None,
    is_active: bool | None,
    expired: bool | None,
    pagination: PaginationModel,
) -> tuple[list[SubscriptionResp], int]:
    """Список с фильтрами + пагинацией. Soft-deleted скрыты.

    Агрегаты по ресторанам считаются одним JOIN с subquery — без N+1 на
    `pageSize` элементов.
    """
    now = now_utc()

    filters: list[Any] = [Subscriptions.deleted_at.is_(None)]
    if organization_id is not None:
        filters.append(Subscriptions.organization_id == organization_id)
    if is_active is True:
        # NULL is_active в БД (server_default=true) трактуем как True.
        filters.append(is_active_truthy(Subscriptions.is_active))
    elif is_active is False:
        filters.append(is_active_falsy(Subscriptions.is_active))
    if expired is not None:
        filters.append(Subscriptions.end_date < now if expired else Subscriptions.end_date >= now)

    total = int(
        (
            await db.execute(select(func.count()).select_from(Subscriptions).where(and_(*filters)))
        ).scalar_one()
    )
    if total == 0:
        return [], 0

    # Подсчёт ресторанов одним JOIN'ом с агрегатной subquery — устраняет N+1.
    restaurant_counts = (
        select(
            Restaurants.organization_id.label("org_id"),
            func.count(Restaurants.id).label("total"),
            func.count(Restaurants.id).filter(Restaurants.is_active.is_(True)).label("active"),
        )
        .where(Restaurants.deleted_at.is_(None))
        .group_by(Restaurants.organization_id)
        .subquery()
    )
    rc = aliased(restaurant_counts)

    stmt = (
        select(
            Subscriptions,
            func.coalesce(rc.c.total, 0).label("total_restaurants"),
            func.coalesce(rc.c.active, 0).label("active_restaurants"),
        )
        .options(selectinload(Subscriptions.organization))
        .join(rc, Subscriptions.organization_id == rc.c.org_id, isouter=True)
        .where(and_(*filters))
        .order_by(Subscriptions.created_at.desc(), Subscriptions.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    rows = (await db.execute(stmt)).all()
    items = [
        _subscription_to_detail(
            row[0],
            now=now,
            total_restaurants=int(row.total_restaurants),
            active_restaurants=int(row.active_restaurants),
        )
        for row in rows
    ]
    return items, total


async def create_subscription(
    db: AsyncSession,
    *,
    payload: CreateSubscriptionReq,
    admin_id: int,
    client_ip: str | None,
) -> SubscriptionResp:
    """Создаёт подписку.

    Под `_get_organization(for_update=True)` параллельные create/approve для
    той же орг сериализуются — инвариант «≤ 1 активной» не нарушается даже
    при concurrent admin requests.

    Если новая `isActive != False` — деактивирует существующую активную.
    При явном `isActive=False` деактивацию НЕ делаем: новая не активна —
    инвариант не нарушается.
    """
    _ = await _get_organization(db, payload.organization_id, for_update=True)

    now = now_utc()
    is_active_final = True if payload.is_active is None else payload.is_active
    if is_active_final:
        await _deactivate_active_for_org(db, payload.organization_id, now=now)

    start = ensure_aware_utc(payload.start_date) if payload.start_date is not None else now
    end = add_months(start, payload.period)
    limit = payload.restaurant_limit or DEFAULT_RESTAURANT_LIMIT

    sub = Subscriptions(
        organization_id=payload.organization_id,
        period=payload.period,
        start_date=start,
        end_date=end,
        is_active=is_active_final,
        restaurant_limit=limit,
        created_at=now,
        updated_at=now,
    )
    db.add(sub)
    await db.flush()

    _ = await admin_log_service.log_action(
        db,
        admin_id=admin_id,
        action=AdminAction.CREATE,
        entity_type=EntityType.SUBSCRIPTION,
        entity_id=int(sub.id),
        details={
            "organizationId": payload.organization_id,
            "period": payload.period,
            "restaurantLimit": limit,
            "isActive": is_active_final,
        },
        ip_address=client_ip,
    )
    await db.commit()
    await db.refresh(sub, attribute_names=["organization"])
    return await _build_subscription_detail(db, sub, now=now)


# ---------- extension requests: public API ----------


async def list_extension_requests(
    db: AsyncSession,
    *,
    status: ExtensionRequestStatus | None,
    organization_id: int | None,
    pagination: PaginationModel,
) -> tuple[list[ExtensionRequestResp], int]:
    """Список заявок. По дефолту в роутере фильтр `status=pending`."""
    filters: list[Any] = [SubscriptionExtensionRequests.deleted_at.is_(None)]
    if status is not None:
        filters.append(SubscriptionExtensionRequests.status == status.value)
    if organization_id is not None:
        filters.append(SubscriptionExtensionRequests.organization_id == organization_id)

    total = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SubscriptionExtensionRequests)
                .where(and_(*filters))
            )
        ).scalar_one()
    )

    stmt = (
        select(SubscriptionExtensionRequests)
        .options(
            selectinload(SubscriptionExtensionRequests.organization),
            selectinload(SubscriptionExtensionRequests.user),
        )
        .where(and_(*filters))
        .order_by(
            SubscriptionExtensionRequests.created_at.desc(),
            SubscriptionExtensionRequests.id.desc(),
        )
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    reqs = list((await db.scalars(stmt)).all())
    return [_request_to_resp(r) for r in reqs], total


async def get_extension_request(db: AsyncSession, req_id: int) -> ExtensionRequestResp:
    req = await _get_extension_request_loaded(db, req_id)
    return _request_to_resp(req)


async def reject_extension_request(
    db: AsyncSession,
    *,
    req_id: int,
    payload: RejectExtensionRequestReq,
    admin_id: int,
    client_ip: str | None,
) -> ExtensionRequestResp:
    """Отклоняет pending-заявку. Подписку не трогает.

    Reject имеет смысл только из `pending` — иначе 400 `ExtensionRequestNotPending`.
    """
    validate_no_null_bytes(payload.admin_comment)
    req = await _get_extension_request_loaded(db, req_id)

    if req.status != ExtensionRequestStatus.PENDING.value:
        raise ExtensionRequestNotPending

    previous_status = req.status
    req.status = ExtensionRequestStatus.REJECTED.value
    req.admin_comment = payload.admin_comment
    req.updated_at = now_utc()

    _ = await admin_log_service.log_action(
        db,
        admin_id=admin_id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.SUBSCRIPTION_EXTENSION_REQUEST,
        entity_id=int(req.id),
        details={
            "previousStatus": previous_status,
            "newStatus": ExtensionRequestStatus.REJECTED.value,
            "adminComment": payload.admin_comment,
        },
        ip_address=client_ip,
    )
    await db.commit()
    await db.refresh(req, attribute_names=["organization", "user"])
    return _request_to_resp(req)


async def approve_extension_request(
    db: AsyncSession,
    *,
    req_id: int,
    payload: ApproveExtensionRequestReq,
    admin_id: int,
    client_ip: str | None,
) -> ApproveExtensionResp:
    """Атомарно: меняет заявку → completed И продлевает/создаёт подписку.

    `mode=seamless` без активной подписки фолбэчит в `immediate_new`,
    финальный `mode` всегда возвращается клиенту.

    Concurrency-защита (двойная):
    - `SELECT ... FOR UPDATE` на самой заявке — блокирует double-approve.
    - `_get_organization(for_update=True)` на orgID — сериализует параллельные
      approve/create для одной орг (защита инварианта «≤ 1 активной»).

    Один commit на всю транзакцию: бизнес или audit упал — откат всего.
    """
    validate_no_null_bytes(payload.admin_comment)

    request = await _get_extension_request_loaded(db, req_id, for_update=True)

    if request.status != ExtensionRequestStatus.PENDING.value:
        raise ExtensionRequestNotPending
    if payload.end_date_override is None and (request.period is None or request.period <= 0):
        raise ExtensionPeriodRequired

    # Lock на orgID — сериализует параллельные create/approve для этой орг.
    _ = await _get_organization(db, int(request.organization_id), for_update=True)

    now = now_utc()

    # 1) Определяем эффективный режим (seamless без активной → fallback).
    active_sub: Subscriptions | None = None
    if payload.mode == SubscriptionApprovalMode.SEAMLESS:
        active_sub = await _find_active_subscription(
            db, int(request.organization_id), for_update=True
        )
    effective_mode = (
        EffectiveApprovalMode.SEAMLESS_EXTEND
        if (payload.mode == SubscriptionApprovalMode.SEAMLESS and active_sub is not None)
        else EffectiveApprovalMode.IMMEDIATE_NEW
    )

    # 2) Строим целевое состояние подписки.
    result_sub: Subscriptions
    if effective_mode == EffectiveApprovalMode.SEAMLESS_EXTEND:
        if active_sub is None:
            # Инвариант на ветви: SEAMLESS_EXTEND означает, что мы нашли активную.
            # Если попали сюда — баг в логике определения effective_mode выше.
            raise RuntimeError("SEAMLESS_EXTEND branch entered without active_sub")
        validate_end_date_override(payload.end_date_override, active_sub.start_date, now)
        new_end = compute_new_end_date(
            override=payload.end_date_override,
            base=active_sub.end_date,
            period_months=request.period or 0,
        )
        # Override — окончательная правда; period НЕ инкрементим
        # (паритет с Go: end_date — источник истины).
        new_period = (
            active_sub.period
            if payload.end_date_override is not None
            else active_sub.period + (request.period or 0)
        )
        new_limit = resolve_limit(
            override=payload.restaurant_limit,
            requested=request.requested_restaurant_limit,
            fallback=active_sub.restaurant_limit or DEFAULT_RESTAURANT_LIMIT,
        )
        active_sub.period = new_period
        active_sub.end_date = new_end
        active_sub.is_active = True
        active_sub.restaurant_limit = new_limit
        active_sub.updated_at = now
        result_sub = active_sub
    else:  # IMMEDIATE_NEW
        validate_end_date_override(payload.end_date_override, now, now)
        new_end = compute_new_end_date(
            override=payload.end_date_override,
            base=now,
            period_months=request.period or 0,
        )
        new_limit = resolve_limit(
            override=payload.restaurant_limit,
            requested=request.requested_restaurant_limit,
            fallback=DEFAULT_RESTAURANT_LIMIT,
        )
        # Деактивируем все активные подписки целевой орг.
        await _deactivate_active_for_org(db, int(request.organization_id), now=now)
        result_sub = Subscriptions(
            organization_id=request.organization_id,
            period=request.period or 0,
            start_date=now,
            end_date=new_end,
            is_active=True,
            restaurant_limit=new_limit,
            created_at=now,
            updated_at=now,
        )
        db.add(result_sub)
        await db.flush()

    # 3) Заявка → completed.
    request.status = ExtensionRequestStatus.COMPLETED.value
    request.admin_comment = payload.admin_comment
    request.updated_at = now

    _ = await admin_log_service.log_action(
        db,
        admin_id=admin_id,
        action=AdminAction.UPDATE,
        entity_type=EntityType.SUBSCRIPTION_EXTENSION_REQUEST,
        entity_id=int(req_id),
        details=jsonify(
            {
                "mode": effective_mode.value,
                "subscriptionId": int(result_sub.id),
                "organizationId": int(request.organization_id),
                "adminComment": payload.admin_comment,
            }
        ),
        ip_address=client_ip,
    )

    await db.commit()
    await db.refresh(result_sub, attribute_names=["organization"])
    await db.refresh(request, attribute_names=["organization", "user"])

    return ApproveExtensionResp(
        extension_request=_request_to_resp(request),
        subscription=await _build_subscription_detail(db, result_sub, now=now),
        mode=effective_mode,
    )
