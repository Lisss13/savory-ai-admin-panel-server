from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramSubscribers


async def get_subscribers(db: AsyncSession) -> list[TelegramSubscribers]:
    stmt = select(TelegramSubscribers).order_by(TelegramSubscribers.chat_id.asc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def delete_subscriber(db: AsyncSession, tg_id: int) -> bool:
    stmt = select(TelegramSubscribers).where(TelegramSubscribers.id == tg_id)
    res = await db.execute(stmt)
    subscriber = res.scalars().first()
    if subscriber:
        await db.delete(subscriber)
        await db.commit()
        return True
    return False
