"""Unit-тесты `app/onboarding/service.py`.

Гоняем функции сервиса напрямую, без HTTP. Фокус — `get_onboarding_request_by_id`
(выбранный пользователем) + смежные методы листинга.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.onboarding import service
from app.onboarding.exceptions import OnboardingRequestNotFound

from .conftest import RequestFactory

# ---------- get_onboarding_request_by_id ----------


async def test_get_by_id_returns_existing(db_session: AsyncSession, make_request: RequestFactory):
    """Базовый случай — нашли заявку по id."""
    request = await make_request(status="new", name="findable")

    result = await service.get_onboarding_request_by_id(db_session, request.id)

    assert result.id == request.id
    assert result.name == request.name
    assert result.status == "new"


async def test_get_by_id_raises_when_missing(db_session: AsyncSession):
    """Несуществующий id → `OnboardingRequestNotFound` (HTTP 404 в роутере)."""
    with pytest.raises(OnboardingRequestNotFound):
        await service.get_onboarding_request_by_id(db_session, 999_999)


async def test_get_by_id_treats_soft_deleted_as_missing(
    db_session: AsyncSession, make_request: RequestFactory
):
    """Soft-deleted строка (`deleted_at IS NOT NULL`) не должна выдаваться."""
    request = await make_request(status="new", deleted_at=datetime.now(tz=UTC))

    with pytest.raises(OnboardingRequestNotFound):
        await service.get_onboarding_request_by_id(db_session, request.id)


async def test_get_by_id_does_not_match_other_records(
    db_session: AsyncSession, make_request: RequestFactory
):
    """При нескольких записях в БД сервис возвращает ровно одну — по id."""
    await make_request(status="new")
    target = await make_request(status="contacted")
    await make_request(status="installed")

    result = await service.get_onboarding_request_by_id(db_session, target.id)

    assert result.id == target.id
    assert result.status == "contacted"


# ---------- get_onboarding_request (листинг — смежная функция) ----------


async def test_list_returns_empty_when_no_records(db_session: AsyncSession):
    """Пустая таблица → пустой список (а не None и не исключение)."""
    result = await service.get_onboarding_request(db_session)
    assert result == []


async def test_list_excludes_soft_deleted(db_session: AsyncSession, make_request: RequestFactory):
    """`deleted_at IS NOT NULL` — строка не должна возвращаться."""
    active = await make_request(status="new")
    await make_request(status="new", deleted_at=datetime.now(tz=UTC))

    result = await service.get_onboarding_request(db_session)

    assert [r.id for r in result] == [active.id]


async def test_list_orders_by_updated_at_desc(
    db_session: AsyncSession, make_request: RequestFactory
):
    """Сортировка `updated_at DESC` — самые свежие сверху."""
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    older = await make_request(status="new", updated_at=now - timedelta(hours=2))
    newest = await make_request(status="new", updated_at=now)
    middle = await make_request(status="new", updated_at=now - timedelta(hours=1))

    result = await service.get_onboarding_request(db_session)

    assert [r.id for r in result] == [newest.id, middle.id, older.id]


async def test_list_filters_by_status(db_session: AsyncSession, make_request: RequestFactory):
    """Передан `status='contacted'` — возвращаются только заявки этого статуса."""
    await make_request(status="new")
    contacted = await make_request(status="contacted")
    await make_request(status="installed")

    result = await service.get_onboarding_request(db_session, status="contacted")

    assert [r.id for r in result] == [contacted.id]


async def test_list_without_status_returns_all_statuses(
    db_session: AsyncSession, make_request: RequestFactory
):
    """`status=None` — возвращаются заявки со всеми статусами."""
    await make_request(status="new")
    await make_request(status="contacted")
    await make_request(status="installed")

    result = await service.get_onboarding_request(db_session, status=None)

    statuses = {r.status for r in result}
    assert statuses == {"new", "contacted", "installed"}
