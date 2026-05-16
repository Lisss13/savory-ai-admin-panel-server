from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramSubscribers


async def get_subscribers(db: AsyncSession) -> list[TelegramSubscribers]:
    stmt = select(TelegramSubscribers).order_by(TelegramSubscribers.chat_id.asc())
    res = await db.execute(stmt)
    return list(res.scalars().all())
