"""Тестовые фикстуры.

Тестовая БД — `aiosqlite:///:memory:` (реальная БД, не мок). Явно указан
`poolclass=StaticPool`, чтобы все соединения видели один in-memory DB
(SQLite держит схему в рамках одного соединения).

Создаются только таблицы, нужные тестам (`admin`, `admin_login_log`,
`languages`). Остальная схема `Base.metadata` живёт в продакшен-Postgres
и в in-memory SQLite не поднимается.

`app.dependency_overrides[get_db]` подменяется на сессию из тестового движка,
поэтому `httpx.AsyncClient` ходит в SQLite, а не в реальный Postgres.
"""

from collections.abc import AsyncIterator
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, Table
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.admin.models import Admin, AdminLoginLog
from app.admin.rate_limit import login_rate_limiter
from app.admin_log.models import AdminLogs
from app.database import get_db
from app.main import app
from app.models import (
    AiRequestLogs,
    Languages,
    OnboardingRequests,
    Organizations,
    Restaurants,
    SubscriptionExtensionRequests,
    Subscriptions,
    SupportTickets,
    Tables,
    TelegramSubscribers,
    Users,
)

# `Languages.id` в `app/models.py` объявлен как BigInteger (под Postgres-sequence).
# SQLite автоинкрементит только `INTEGER PRIMARY KEY` — без этого все INSERT-ы
# падают с NOT NULL constraint failed. Подменяем тип PK для тестового engine'а.
# SQLAlchemy типизирует `__table__` как `FromClause`, поэтому касты к `Table`
# нужны и тут, и в фикстуре `test_engine`.
_admin_table = cast(Table, Admin.__table__)
_admin_login_log_table = cast(Table, AdminLoginLog.__table__)
_languages_table = cast(Table, Languages.__table__)
_languages_table.c.id.type = Integer()
# То же самое для support_tickets: id → Integer для SQLite, а server_default
# `'in_progress'::text` — Postgres-специфичный синтаксис, SQLite его не парсит,
# поэтому сбрасываем (в тестах статус задаём явно).
_support_tickets_table = cast(Table, SupportTickets.__table__)
_support_tickets_table.c.id.type = Integer()
_support_tickets_table.c.status.server_default = None
# `users` нужна для `selectinload(SupportTickets.user)` в `get_support_ticket`,
# даже если поле user в Response-схеме не используется. Сбрасываем те же
# Postgres-специфичные server_default-ы.
_users_table = cast(Table, Users.__table__)
_users_table.c.id.type = Integer()
_users_table.c.role.server_default = None
_users_table.c.is_active.server_default = None
# `onboarding_requests` нужен тестам интеграции с audit-логом.
_onboarding_requests_table = cast(Table, OnboardingRequests.__table__)
_onboarding_requests_table.c.id.type = Integer()
# `admin_logs` — таблица аудита; FK ссылается на `admin.id`, PK уже использует
# `with_variant(Integer, "sqlite")`, так что доп. оверрайды не нужны.
_admin_logs_table = cast(Table, AdminLogs.__table__)
# `telegram_subscribers` — id BigInteger, для SQLite-автоинкремента сводим к Integer.
_telegram_subscribers_table = cast(Table, TelegramSubscribers.__table__)
_telegram_subscribers_table.c.id.type = Integer()
# Связка для /restaurants — нужны organizations, restaurants, tables, subscriptions,
# ai_request_logs. У всех id — BigInteger (Postgres bigserial), для SQLite сводим
# к Integer, чтобы автоинкремент PK работал. Postgres-специфичные server_default
# (`'text'::text`, `true`, числовые литералы) SQLite парсит, но boolean-литералы
# приходится отключать (см. оверрайды ниже).
_organizations_table = cast(Table, Organizations.__table__)
_organizations_table.c.id.type = Integer()
_restaurants_table = cast(Table, Restaurants.__table__)
_restaurants_table.c.id.type = Integer()
# Postgres-defaults на бул-колонках с `::text` SQLite не понимает.
_restaurants_table.c.is_active.server_default = None
_restaurants_table.c.ordering_enabled.server_default = None
_restaurants_table.c.show_dish_links.server_default = None
_restaurants_table.c.ai_suggestions_enabled.server_default = None
_restaurants_table.c.currency.server_default = None
_restaurants_table.c.default_language.server_default = None
_tables_table = cast(Table, Tables.__table__)
_tables_table.c.id.type = Integer()
_subscriptions_table = cast(Table, Subscriptions.__table__)
_subscriptions_table.c.id.type = Integer()
_subscriptions_table.c.is_active.server_default = None
_ai_request_logs_table = cast(Table, AiRequestLogs.__table__)
_ai_request_logs_table.c.id.type = Integer()
# `subscription_extension_requests` — нужна тестам модуля subscriptions.
# Postgres-specific server_default `'pending'::text` SQLite не парсит — сбрасываем.
_subscription_extension_requests_table = cast(Table, SubscriptionExtensionRequests.__table__)
_subscription_extension_requests_table.c.id.type = Integer()
_subscription_extension_requests_table.c.status.server_default = None
_subscription_extension_requests_table.c.requested_restaurant_limit.server_default = None

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
async def test_engine():
    """Один движок на сессию pytest, in-memory SQLite на StaticPool."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: _admin_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _admin_login_log_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _languages_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _users_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _support_tickets_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _onboarding_requests_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _admin_logs_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _telegram_subscribers_table.create(c, checkfirst=True))
        # Порядок важен: организации ссылаются на users (admin_id),
        # рестораны — на организации, столики/подписки/AI-логи — на рестораны.
        await conn.run_sync(lambda c: _organizations_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _restaurants_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _tables_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _subscriptions_table.create(c, checkfirst=True))
        await conn.run_sync(lambda c: _ai_request_logs_table.create(c, checkfirst=True))
        await conn.run_sync(
            lambda c: _subscription_extension_requests_table.create(c, checkfirst=True)
        )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    """Чистая сессия на тест: после теста все строки удаляются."""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    async with test_engine.begin() as conn:
        await conn.run_sync(lambda c: c.execute(_admin_logs_table.delete()))
        await conn.run_sync(lambda c: c.execute(_admin_login_log_table.delete()))
        await conn.run_sync(lambda c: c.execute(_onboarding_requests_table.delete()))
        await conn.run_sync(lambda c: c.execute(_support_tickets_table.delete()))
        await conn.run_sync(lambda c: c.execute(_languages_table.delete()))
        # Дочерние таблицы сносим до родительских, иначе FK на restaurants/orgs
        # не дадут удалить родителя.
        await conn.run_sync(lambda c: c.execute(_ai_request_logs_table.delete()))
        await conn.run_sync(lambda c: c.execute(_subscription_extension_requests_table.delete()))
        await conn.run_sync(lambda c: c.execute(_subscriptions_table.delete()))
        await conn.run_sync(lambda c: c.execute(_tables_table.delete()))
        await conn.run_sync(lambda c: c.execute(_restaurants_table.delete()))
        await conn.run_sync(lambda c: c.execute(_organizations_table.delete()))
        await conn.run_sync(lambda c: c.execute(_admin_table.delete()))
        await conn.run_sync(lambda c: c.execute(_users_table.delete()))
        await conn.run_sync(lambda c: c.execute(_telegram_subscribers_table.delete()))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Сбрасываем in-memory rate-limiter между тестами — иначе фейлы накапливаются."""
    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент с подменённым `get_db`: ходит в тестовую SQLite."""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
