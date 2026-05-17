from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field


class PaginationParamsM(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"limit": 10, "offset": 0}})

    limit: int = Field(10, ge=1, le=100)
    offset: int = Field(0, ge=0)


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


def get_pagination_params(
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginationParamsM:
    return PaginationParamsM(limit=limit, offset=offset)


PaginationParams = Annotated[PaginationParamsM, Depends(get_pagination_params)]
