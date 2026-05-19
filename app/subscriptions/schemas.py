"""Pydantic-схемы IO для модуля subscriptions.

Все Response-модели наследуют `CamelModel` → JSON в camelCase (правило
контракта API воркспейса, см. ../CLAUDE.md). Request-модели — тоже на
`CamelModel`, благодаря `populate_by_name=True` на вход принимают как
camelCase (`organizationId`), так и snake_case.
"""

from datetime import datetime

from pydantic import Field

from app.schemas import CamelModel
from app.subscriptions.constants import (
    EffectiveApprovalMode,
    ExtensionRequestStatus,
    SubscriptionApprovalMode,
)

# ---------- подписки ----------


class OrganizationShort(CamelModel):
    """Компактная организация для вложенных ответов (подписка, заявка)."""

    id: int
    name: str
    phone: str


class UserShort(CamelModel):
    """Компактный пользователь — автор заявки на продление."""

    id: int
    name: str
    email: str


class SubscriptionResp(CamelModel):
    """Детальный ответ по подписке.

    `daysLeft`, `isExpired`, `activeRestaurants`, `totalRestaurants` —
    вычисляются на лету в сервисе (не хранятся в БД).
    """

    id: int
    organization: OrganizationShort
    period: int
    start_date: datetime
    end_date: datetime
    is_active: bool
    restaurant_limit: int
    active_restaurants: int
    total_restaurants: int
    days_left: int
    is_expired: bool
    created_at: datetime | None
    updated_at: datetime | None


class CreateSubscriptionReq(CamelModel):
    """Тело POST /admin/subscriptions.

    `startDate=None` → текущая `datetime.now(UTC)`.
    `restaurantLimit=None` → `DEFAULT_RESTAURANT_LIMIT` (1).
    `isActive=None` → True. Если явно `False` — НЕ деактивируем существующую
    активную (инвариант «≤1 активной» не нарушается).
    """

    organization_id: int = Field(..., gt=0)
    period: int = Field(..., ge=1)
    start_date: datetime | None = None
    restaurant_limit: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class ExtensionRequestResp(CamelModel):
    """Заявка на продление подписки — детальный ответ."""

    id: int
    organization: OrganizationShort
    user: UserShort
    name: str
    phone: str
    email: str
    period: int | None
    requested_restaurant_limit: int | None
    comment: str | None
    status: ExtensionRequestStatus
    admin_comment: str | None
    created_at: datetime | None
    updated_at: datetime | None


class RejectExtensionRequestReq(CamelModel):
    """Тело POST /subscriptions/extension-requests/{id}/reject.

    Переводит заявку в `rejected` с обязательной возможностью оставить
    комментарий админа. Подписку не трогает.
    """

    admin_comment: str | None = Field(default=None, max_length=4096)


class ApproveExtensionRequestReq(CamelModel):
    """Тело POST /subscriptions/extension-requests/{id}/approve.

    `mode=seamless` без активной подписки автоматически фолбэчит в
    `immediate_new` — это отражается в `mode` ответа.

    `endDateOverride`, если задан, заменяет вычисленный `endDate` и:
    - в seamless-режиме НЕ инкрементит `period` (override считается
      окончательной правдой);
    - в immediate-режиме `start_date=now`, `period=request.period`.

    `restaurantLimit` — override; при отсутствии берётся
    `request.requestedRestaurantLimit` (>0), потом текущий лимит подписки
    (seamless) или DEFAULT_RESTAURANT_LIMIT (immediate).
    """

    mode: SubscriptionApprovalMode
    end_date_override: datetime | None = None
    restaurant_limit: int | None = Field(default=None, ge=1)
    admin_comment: str | None = Field(default=None, max_length=4096)


class ApproveExtensionResp(CamelModel):
    """Ответ approve: обновлённая заявка + затронутая подписка + факт. режим.

    `mode` может отличаться от запрошенного: при `seamless` без активной
    подписки фактически создаётся новая (mode=`immediate_new`).
    """

    extension_request: ExtensionRequestResp
    subscription: SubscriptionResp
    mode: EffectiveApprovalMode
