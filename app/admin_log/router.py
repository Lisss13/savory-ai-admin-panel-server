"""HTTP-эндпоинты admin-audit-log модуля.

- `GET /admin/logs`    — весь журнал (страничная пагинация).
- `GET /admin/logs/me` — только записи текущего админа.

Оба требуют валидный JWT админа (см. `CurrentAdmin`).
Пагинация — через query-параметры `page` и `pageSize` (camelCase по контракту API).
"""

from fastapi import APIRouter, Query, status

from app.admin.dependencies import CurrentAdmin, DbSession
from app.admin_log import service
from app.admin_log.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.admin_log.schemas import AdminLogListResp, AdminLogResp
from app.schemas import Envelope

router = APIRouter(prefix="/admin/logs", tags=["admin-logs"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Журнал админ-действий",
    description=(
        "Постраничный список всех записей `admin_logs`, отсортированных по "
        "`created_at` DESC. Доступно только админам. Soft-deleted записи скрыты."
    ),
    response_model=Envelope[AdminLogListResp],
)
async def get_logs(
    _admin: CurrentAdmin,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
) -> Envelope[AdminLogListResp]:
    items, total = await service.list_logs(db, page=page, page_size=page_size)
    return Envelope(
        data=AdminLogListResp(
            items=[AdminLogResp.model_validate(i) for i in items],
            page=page,
            page_size=page_size,
            total=total,
        ),
        code=status.HTTP_200_OK,
    )


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Мои действия",
    description=(
        "Постраничный список записей `admin_logs` только текущего админа. "
        "Удобно для self-аудита (см. свой след)."
    ),
    response_model=Envelope[AdminLogListResp],
)
async def get_my_logs(
    admin: CurrentAdmin,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
) -> Envelope[AdminLogListResp]:
    items, total = await service.list_logs(
        db, page=page, page_size=page_size, admin_id_filter=admin.id
    )
    return Envelope(
        data=AdminLogListResp(
            items=[AdminLogResp.model_validate(i) for i in items],
            page=page,
            page_size=page_size,
            total=total,
        ),
        code=status.HTTP_200_OK,
    )
