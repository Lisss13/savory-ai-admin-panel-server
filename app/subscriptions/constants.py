"""Константы и enum's модуля subscriptions."""

from enum import StrEnum

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
# По умолчанию у новой подписки лимит = 1 ресторан (соответствует server_default
# колонки `restaurant_limit` в БД и Go-`storage.Subscription.RestaurantLimit`).
DEFAULT_RESTAURANT_LIMIT = 1


class ExtensionRequestStatus(StrEnum):
    """Статус заявки на продление подписки.

    Жизненный цикл: `pending → (rejected | completed)`. `approved` —
    промежуточный статус, на практике редко используется (после одобрения
    через `/approve` мы переходим сразу в `completed`).
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class SubscriptionApprovalMode(StrEnum):
    """Режим одобрения заявки админом.

    `seamless` — продлить текущую активную подписку (если активной нет —
    falls back на `immediate` создание новой).
    `immediate` — всегда создать новую подписку с `start_date=now`,
    деактивировав предыдущие активные.
    """

    SEAMLESS = "seamless"
    IMMEDIATE = "immediate"


class EffectiveApprovalMode(StrEnum):
    """Фактический режим, который был применён к подписке при approve.

    Отличается от `SubscriptionApprovalMode`: показывает, что именно
    произошло (а не что запрошено). При запросе `seamless` без активной
    подписки итог будет `IMMEDIATE_NEW` — фронт это отображает.
    """

    SEAMLESS_EXTEND = "seamless_extend"
    IMMEDIATE_NEW = "immediate_new"
