from fastapi import APIRouter
from starlette import status

from app.admin.dependencies import CurrentAdmin, DbSession
from app.common.utils.pagination import PaginationParams
from app.organizations.schemas import OrganizationResp
from app.organizations.service import get_organizations
from app.schemas import Envelope

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Список организаций с админом и ресторанами",
)
async def list_organizations(
    db: DbSession,
    _admin: CurrentAdmin,
    pagination: PaginationParams,
) -> Envelope[list[OrganizationResp]]:
    """Возвращает активные (не soft-deleted) организации с админом
    и вложенным списком их ресторанов. `subscriptionActive` — флаг
    активной подписки организации, продублирован в каждом ресторане.
    Пагинация через `limit` (default 10, max 100) и `offset` (default 0)."""
    rows = await get_organizations(db, pagination)
    return Envelope(
        data=[OrganizationResp.model_validate(r) for r in rows],
        code=status.HTTP_200_OK,
    )
