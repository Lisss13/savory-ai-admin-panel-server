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
