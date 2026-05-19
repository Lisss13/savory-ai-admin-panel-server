from fastapi import APIRouter, status

from app.admin.dependencies import CurrentAdmin, DbSession
from app.dashboard.schemas import AppStats
from app.dashboard.service import calculate_app_stats
from app.schemas import Envelope

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", status_code=status.HTTP_200_OK)
async def get_stats(
    _admin: CurrentAdmin,
    db: DbSession,
) -> Envelope[AppStats]:
    stats = await calculate_app_stats(db)
    return Envelope(data=stats)
