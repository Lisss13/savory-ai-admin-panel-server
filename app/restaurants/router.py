from typing import Annotated

from fastapi import APIRouter, Query
from starlette import status

from app.admin.dependencies import CurrentAdmin, DbSession
from app.common.utils.pagination import PaginationParams
from app.restaurants.schemas import RestaurantDetailResponse, RestaurantResponse
from app.restaurants.service import get_restaurant_by_id, list_restaurants
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
    subscription_is: Annotated[bool | None, Query(alias="subscriptionActive")] = None,
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


@router.get(
    "/{restaurant_id}",
    status_code=status.HTTP_200_OK,
    summary="Получить ресторан по ID",
    response_model=Envelope[RestaurantDetailResponse],
)
async def get_restaurant(
    db: DbSession,
    _admin: CurrentAdmin,
    restaurant_id: int,
) -> Envelope[RestaurantDetailResponse]:
    restaurant = await get_restaurant_by_id(db, restaurant_id)
    if not restaurant:
        return Envelope(
            messages=["Restaurant not found"],
            code=status.HTTP_404_NOT_FOUND,
        )
    return Envelope(
        data=restaurant,
        code=status.HTTP_200_OK,
    )
