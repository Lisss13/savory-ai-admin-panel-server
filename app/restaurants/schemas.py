from datetime import datetime

from app.schemas import CamelModel


class RestaurantResponse(CamelModel):
    """Строка списка активных ресторанов для admin-дэшборда.

    `subscriptionActive` — флаг по организации (подписка лежит на уровне org).
    `tablesCount` — кол-во столиков этого ресторана (не soft-deleted).
    `aiRequestsLeft` — остаток месячного AI-лимита (25000 − использовано
    в текущем календарном месяце) считается по этому конкретному ресторану.
    """

    id: int
    name: str
    organization_id: int
    organization_name: str
    subscription_active: bool
    tables_count: int
    ai_requests_left: int
    percentage_of_used_ai_req: float


class RestaurantDetailResponse(RestaurantResponse):
    """Детальная карточка ресторана для страницы `/dashboard/restaurants/:id`.

    Расширяет `RestaurantResponse` фичефлагами, временными метками, полным
    AI-балансом (used + left) и счётчиками по меню. Используется только в
    GET `/restaurants/{id}`; список ресторанов остаётся на `RestaurantResponse`.
    """

    default_language: str | None = None
    show_dish_links: bool | None = None
    ai_suggestions_enabled: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ai_requests_used: int
    menu_categories_count: int
    dishes_count: int
    dishes_active_count: int
