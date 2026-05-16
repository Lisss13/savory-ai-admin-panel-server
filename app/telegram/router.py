from fastapi import APIRouter
from starlette import status

from app.admin.dependencies import CurrentAdmin, DbSession
from app.schemas import Envelope
from app.telegram.schemas import TelegramSubscriber
from app.telegram.service import get_subscribers

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Список людей которые подписаны на телеграмм",
)
async def get_telegrams_subscribers(
    db: DbSession,
    _admin: CurrentAdmin,
) -> Envelope[list[TelegramSubscriber]]:
    tg_s = await get_subscribers(db)
    return Envelope(data=tg_s, code=status.HTTP_200_OK)
