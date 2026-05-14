"""Фикстуры для тестов модуля support.

Содержит фабрику `make_ticket`, чтобы в каждом тесте не плодить ручные
INSERT-ы со всем набором обязательных полей.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SupportTickets, Users

TicketFactory = Callable[..., Awaitable[SupportTickets]]


@pytest.fixture
async def default_user(db_session: AsyncSession) -> Users:
    """Один пользователь-владелец тикетов на тест.

    Нужен, потому что `SupportTicketResp.user` теперь обязательное вложенное
    поле — без строки в `users` сериализация падает.
    """
    user = Users(
        name="Default Tester",
        company="Acme",
        email="tester@example.com",
        phone="+10000000000",
        password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def make_ticket(db_session: AsyncSession, default_user: Users) -> TicketFactory:
    """Создаёт тикет с разумными дефолтами; кладёт в БД и возвращает объект.

    Все поля можно переопределить через kwargs. `updated_at` по умолчанию —
    `now()` минус `index * 1 минута`, чтобы порядок создания совпадал с
    порядком сортировки `updated_at DESC`.
    """

    counter = {"n": 0}

    async def _factory(
        *,
        status: str = "new",
        title: str | None = None,
        description: str = "Описание тестового тикета",
        email: str = "tester@example.com",
        phone: str | None = None,
        user_id: int | None = None,
        deleted_at: datetime | None = None,
        updated_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> SupportTickets:
        idx = counter["n"]
        counter["n"] += 1
        now = datetime.now(tz=UTC)
        upd = updated_at or now - timedelta(minutes=idx)
        cr = created_at or upd - timedelta(hours=1)

        ticket = SupportTickets(
            user_id=user_id if user_id is not None else default_user.id,
            title=title or f"ticket #{idx}",
            description=description,
            email=email,
            phone=phone,
            status=status,
            created_at=cr,
            updated_at=upd,
            deleted_at=deleted_at,
        )
        db_session.add(ticket)
        await db_session.commit()
        await db_session.refresh(ticket)
        return ticket

    return _factory
