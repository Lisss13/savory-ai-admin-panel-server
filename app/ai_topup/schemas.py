"""Pydantic-схемы IO для модуля ai_topup.

Все Response-модели наследуют `CamelModel` → JSON в camelCase (контракт API
воркспейса). Request-модели — тоже на `CamelModel`, благодаря
`populate_by_name=True` принимают на вход и camelCase, и snake_case.

`pricePerPack` / `totalPrice` объявлены как `float`: в БД это `NUMERIC`
(`decimal.Decimal`), но фронт ждёт число — Pydantic коэрсит Decimal → float
при валидации из ORM-атрибутов, в JSON уходит число (не строка).
"""

from datetime import datetime

from pydantic import Field

from app.ai_topup.constants import TopUpRequestStatus
from app.schemas import CamelModel


class OrganizationShort(CamelModel):
    """Компактная организация для вложенных ответов."""

    id: int
    name: str
    phone: str


class RestaurantShort(CamelModel):
    """Компактный ресторан — целевой ресторан докупки."""

    id: int
    name: str


class UserShort(CamelModel):
    """Компактный пользователь — автор заявки."""

    id: int
    name: str
    email: str


class TopUpRequestResp(CamelModel):
    """Заявка на докупку AI-запросов — детальный ответ."""

    id: int
    organization: OrganizationShort
    restaurant: RestaurantShort
    user: UserShort
    name: str
    phone: str
    email: str
    packs_count: int
    requests_per_pack: int
    price_per_pack: float
    currency: str
    total_price: float
    comment: str
    status: TopUpRequestStatus
    admin_comment: str
    created_at: datetime | None
    processed_at: datetime | None


class QuotaResp(CamelModel):
    """Выданная квота — результат апрува заявки.

    `requestsGranted` = `packsCount * requestsPerPack`. `expiresAt` — начало
    следующего календарного месяца (UTC): момент, когда квота сгорает.
    """

    requests_granted: int
    period_start: datetime
    expires_at: datetime


class ApproveTopUpRequestReq(CamelModel):
    """Тело POST /ai-topup/requests/{id}/approve."""

    admin_comment: str | None = Field(default=None, max_length=4096)


class RejectTopUpRequestReq(CamelModel):
    """Тело POST /ai-topup/requests/{id}/reject."""

    admin_comment: str | None = Field(default=None, max_length=4096)


class ApproveTopUpResp(CamelModel):
    """Ответ approve: обновлённая заявка + созданная квота.

    Квоту возвращаем, чтобы фронт показал реальную дату сгорания (`expiresAt`)
    и выданный объём (`requestsGranted`) из БД, а не пересчитывал на клиенте.
    """

    top_up_request: TopUpRequestResp
    quota: QuotaResp
