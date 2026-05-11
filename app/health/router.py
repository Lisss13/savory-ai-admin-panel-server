from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.health.schemas import HealthResponse
from app.health.service import check_health
from app.schemas import Envelope

router = APIRouter(tags=["health"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Liveness + DB probe",
    description="Возвращает статус сервиса и доступность Postgres (через `SELECT 1`).",
)
async def health(db: DbSession) -> Envelope[HealthResponse]:
    data = await check_health(db)
    return Envelope(data=data, code=status.HTTP_200_OK)
