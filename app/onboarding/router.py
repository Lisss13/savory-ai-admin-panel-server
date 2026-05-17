from fastapi import APIRouter
from fastapi import status as status_http

from app.admin.dependencies import ClientIp, CurrentAdmin
from app.database import DbSession
from app.onboarding import service
from app.onboarding.constants import Status as StatusEnum
from app.onboarding.schemas import OnboardingRequestResp, OnboardingUpdateReq
from app.schemas import Envelope

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get(
    "",
    status_code=status_http.HTTP_200_OK,
    summary="Список онбординг-заявок",
    description=(
        "Возвращает все активные (не soft-deleted) онбординг-заявки. "
        "Опционально фильтрует по статусу через query-параметр `status` "
        "(значения: `new`, `contacted`, `onboarding`, `installed`)."
    ),
    response_model=Envelope[list[OnboardingRequestResp]],
)
async def get_onboarding_request(
    _admin: CurrentAdmin,
    db: DbSession,
    status: StatusEnum | None = None,
) -> Envelope[list[OnboardingRequestResp]]:
    resp = await service.get_onboarding_request(db, status.value if status else None)
    return Envelope(
        data=[OnboardingRequestResp.model_validate(r) for r in resp],
        code=status_http.HTTP_200_OK,
    )


@router.get(
    "/{or_id}",
    status_code=status_http.HTTP_200_OK,
)
async def get_onboarding_request_by_id(
    or_id: int, _admin: CurrentAdmin, db: DbSession
) -> Envelope[OnboardingRequestResp]:
    resp = await service.get_onboarding_request_by_id(db, or_id)
    return Envelope(
        data=OnboardingRequestResp.model_validate(resp),
        code=status_http.HTTP_200_OK,
    )


@router.patch(
    "/{or_id}",
    status_code=status_http.HTTP_200_OK,
    summary="Обновить онбординг-заявку",
    description=(
        "Обновляет поля онбординг-заявки по id из пути. "
        "Возвращает 404, если заявка не найдена или soft-deleted."
    ),
    response_model=Envelope[OnboardingRequestResp],
)
async def patch_onboarding_request(
    admin: CurrentAdmin,
    db: DbSession,
    client_ip: ClientIp,
    or_id: int,
    body: OnboardingUpdateReq,
) -> Envelope[OnboardingRequestResp]:
    resp = await service.update_onboarding_request(
        db,
        or_id,
        body,
        admin_id=admin.id,
        client_ip=client_ip,
    )
    return Envelope(data=OnboardingRequestResp.model_validate(resp), code=status_http.HTTP_200_OK)
