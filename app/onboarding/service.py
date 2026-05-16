from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_log import service as admin_log_service
from app.admin_log.constants import AdminAction, EntityType
from app.common.utils.diff import calculate_diff
from app.models import OnboardingRequests
from app.onboarding.exceptions import OnboardingRequestNotFound
from app.onboarding.schemas import OnboardingUpdateReq


async def get_onboarding_request(
    db: AsyncSession, status: str | None = None
) -> list[OnboardingRequests]:
    stmt = (
        select(OnboardingRequests)
        .where(OnboardingRequests.deleted_at.is_(None))
        .order_by(OnboardingRequests.updated_at.desc())
    )
    if status:
        stmt = stmt.where(OnboardingRequests.status == status)

    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_onboarding_request_by_id(db: AsyncSession, request_id: int) -> OnboardingRequests:
    stmt = (
        select(OnboardingRequests)
        .where(OnboardingRequests.id == request_id)
        .where(OnboardingRequests.deleted_at.is_(None))
    )
    res = await db.execute(stmt)
    onboarding_request = res.scalar_one_or_none()
    if onboarding_request is None:
        raise OnboardingRequestNotFound
    return onboarding_request


async def update_onboarding_request(
    db: AsyncSession,
    request_id: int,
    body: OnboardingUpdateReq,
    *,
    admin_id: int,
    client_ip: str | None,
) -> OnboardingRequests:
    # `db.get` не фильтрует soft-deleted — используем общий лукап,
    # который учитывает `deleted_at IS NULL` и сам кидает OnboardingRequestNotFound.
    db_request = await get_onboarding_request_by_id(db, request_id)

    update_data = body.model_dump(exclude_unset=True)
    before, after = calculate_diff(db_request, update_data)

    if before:
        await admin_log_service.log_action(
            db,
            admin_id=admin_id,
            action=AdminAction.UPDATE,
            entity_type=EntityType.ONBOARDING_REQUEST,
            entity_id=request_id,
            details={"before": before, "after": after},
            ip_address=client_ip,
        )

    await db.commit()
    await db.refresh(db_request)
    return db_request
