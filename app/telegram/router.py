from fastapi import APIRouter
from starlette import status

from app.admin.dependencies import CurrentAdmin, DbSession
from app.schemas import Envelope
from app.telegram.schemas import TelegramSubscriber
from app.telegram.service import delete_subscriber, get_subscribers

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
    return Envelope(
        data=[TelegramSubscriber.model_validate(tg) for tg in tg_s], code=status.HTTP_200_OK
    )


@router.delete(
    "/{tg_id}",
    status_code=status.HTTP_200_OK,
    summary="Удалить подписчика",
)
async def delete_telegram_subscriber(
    db: DbSession,
    _admin: CurrentAdmin,
    tg_id: int,
) -> Envelope[None]:
    is_deleted = await delete_subscriber(db, tg_id)
    if not is_deleted:
        return Envelope(code=status.HTTP_404_NOT_FOUND, messages=["Subscriber not found"])
    return Envelope(code=status.HTTP_200_OK)
