from typing import Annotated, ClassVar

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PaginationModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"example": {"limit": 10, "offset": 0}}
    )

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
) -> PaginationModel:
    return PaginationModel(limit=limit, offset=offset)


PaginationParams = Annotated[PaginationModel, Depends(get_pagination_params)]
