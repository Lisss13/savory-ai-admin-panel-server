from fastapi import APIRouter, Query
from starlette import status

from app.admin.dependencies import CurrentAdmin, DbSession
from app.common.utils.pagination import PaginationParams
from app.restaurants.schemas import RestaurantResponse
from app.restaurants.service import list_restaurants
from app.schemas import Envelope

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Список активных ресторанов",
    response_model=Envelope[list[RestaurantResponse]],
)
async def get_restaurants(
        db: DbSession,
        _admin: CurrentAdmin,
        pagination: PaginationParams,
        subscription_is: bool | None = Query(default=None, alias="subscriptionActive"),
) -> Envelope[list[RestaurantResponse]]:
    """Возвращает активные (не soft-deleted, `is_active=true`) рестораны
        с названием организации, флагом активной подписки у организации,
        количеством столиков и остатком месячного AI-лимита.
        Опциональный `subscription_is` фильтрует по наличию активной подписки.
        Сортировка `id ASC`, пагинация через `limit`/`offset`."""

    rows = await list_restaurants(db, pagination, subscription_is)
    return Envelope(
        data=[RestaurantResponse.model_validate(r) for r in rows],
        code=status.HTTP_200_OK,
    )
