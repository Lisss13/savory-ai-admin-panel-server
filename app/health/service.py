"""Бизнес-логика домена health."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.health.schemas import HealthResponse


async def check_health(db: AsyncSession) -> HealthResponse:
    """Возвращает агрегированный статус сервиса и доступность Postgres.

    Здесь сознательно ловим широкий `Exception`: смысл probe — *не падать*
    и сообщать статус БД. Драйверные ошибки могут прилетать как из SQLAlchemy
    (`SQLAlchemyError`), так и напрямую из asyncpg (`InvalidPasswordError` и
    другие подклассы `asyncpg.PostgresError`), которые НЕ наследуются от
    `SQLAlchemyError`. Try-блок намеренно охватывает только один вызов
    `SELECT 1` — это исключение из правила «не лови `Exception` в роуте»,
    оно живёт здесь, в сервисе, и не маскирует бизнес-логику.
    """
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"
    return HealthResponse(status="ok", database=db_status)
