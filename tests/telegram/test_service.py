"""Unit-тесты `app/telegram/service.py`.

Гоняем `get_subscribers` напрямую на тестовой sqlite-сессии, без HTTP.
Проверяем:
- пустую таблицу → пустой список;
- сортировку по `chat_id ASC` (контракт сервиса);
- то, что возвращается ровно `TelegramSubscribers`-объект (не Pydantic).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramSubscribers
from app.telegram.service import get_subscribers

from .conftest import SubscriberFactory


async def test_returns_empty_list_when_no_subscribers(db_session: AsyncSession):
    """Без записей → пустой список (а не None и не исключение)."""
    result = await get_subscribers(db_session)
    assert result == []


async def test_orders_by_chat_id_ascending(
    db_session: AsyncSession, make_subscriber: SubscriberFactory
):
    """Контракт сервиса — сортировка `chat_id ASC` независимо от порядка вставки."""
    middle = await make_subscriber(chat_id=200)
    smallest = await make_subscriber(chat_id=100)
    largest = await make_subscriber(chat_id=300)

    result = await get_subscribers(db_session)

    assert [s.chat_id for s in result] == [100, 200, 300]
    # На всякий случай — id-шники тоже сходятся (сервис не теряет строки).
    assert {s.id for s in result} == {smallest.id, middle.id, largest.id}


async def test_returns_orm_objects(db_session: AsyncSession, make_subscriber: SubscriberFactory):
    """Сервис отдаёт ORM-объекты, маппинг в Pydantic — забота роутера."""
    await make_subscriber(chat_id=42, username="alice", first_name="Alice")

    result = await get_subscribers(db_session)

    assert len(result) == 1
    assert isinstance(result[0], TelegramSubscribers)
    assert result[0].username == "alice"


async def test_preserves_nullable_fields(
    db_session: AsyncSession, make_subscriber: SubscriberFactory
):
    """`username` / `first_name` в модели nullable — сервис не должен их фильтровать."""
    await make_subscriber(chat_id=1, username=None, first_name=None)

    result = await get_subscribers(db_session)

    assert len(result) == 1
    assert result[0].username is None
    assert result[0].first_name is None
