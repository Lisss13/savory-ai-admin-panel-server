"""Фикстуры для тестов модуля telegram.

Фабрика `make_subscriber` нужна, чтобы тесты не плодили ручные INSERT-ы:
`chat_id` уникальный, `created_at` — tz-aware, остальные поля по умолчанию
заполнены реалистичными значениями, но при необходимости перебиваются
через kwargs (в т.ч. `username=None` для проверки nullable-полей).
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramSubscribers

SubscriberFactory = Callable[..., Awaitable[TelegramSubscribers]]


@pytest.fixture
def make_subscriber(db_session: AsyncSession) -> SubscriberFactory:
    """Создаёт подписчика с разумными дефолтами и кладёт в БД.

    `chat_id` инкрементируется, чтобы уникальный индекс не падал.
    `created_at` сдвигается на минуту назад для каждого следующего вызова —
    так стабилен порядок сортировки в тестах.
    """

    counter = {"n": 0}

    async def _factory(
        *,
        chat_id: int | None = None,
        username: str | None = "tester",
        first_name: str | None = "Test",
        created_at: datetime | None = None,
    ) -> TelegramSubscribers:
        idx = counter["n"]
        counter["n"] += 1

        subscriber = TelegramSubscribers(
            chat_id=chat_id if chat_id is not None else 1_000_000 + idx,
            username=username,
            first_name=first_name,
            created_at=created_at or datetime.now(tz=UTC) - timedelta(minutes=idx),
        )
        db_session.add(subscriber)
        await db_session.commit()
        await db_session.refresh(subscriber)
        return subscriber

    return _factory
