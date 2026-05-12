from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OnboardingRequests
from app.onboarding.exceptions import OnboardingRequestNotFound
from app.onboarding.schemas import OnboardingUpdateReq


async def get_onboarding_request(
        db: AsyncSession,
        status: str | None = None
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


async def update_onboarding_request(
        db: AsyncSession,
        request_id: int,
        body: OnboardingUpdateReq
) -> OnboardingRequests:
    db_request: OnboardingRequests | None = await db.get(OnboardingRequests, request_id)
    if not db_request:
        raise OnboardingRequestNotFound

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_request, key, value)

    await db.commit()
    await db.refresh(db_request)
    return db_request
