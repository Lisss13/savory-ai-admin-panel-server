"""HTTP-эндпоинты admin-модуля.

- `POST /admin/auth/login` — выдаёт JWT. С rate-limit и audit-логом.
- `GET  /admin/auth/me`    — возвращает текущего админа по токену.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import security, service
from app.admin.config import admin_settings
from app.admin.dependencies import CurrentAdmin
from app.admin.exceptions import InvalidCredentials, TooManyLoginAttempts
from app.admin.rate_limit import login_rate_limiter
from app.admin.schemas import AdminResponse, LoginRequest, LoginResponse
from app.database import get_db
from app.schemas import Envelope

router = APIRouter(prefix="/admin/auth", tags=["admin"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _client_ip(request: Request) -> str | None:
    """Берёт IP клиента. За прокси/Railway лучше использовать X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Первый адрес в цепочке — оригинальный клиент.
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    summary="Логин админа",
    description=(
        "Принимает email/пароль, возвращает JWT (HS256) и публичные данные админа. "
        "После нескольких подряд неудачных попыток на один email возвращает 429."
    ),
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
) -> Envelope[LoginResponse]:
    email = payload.email
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")

    # 1) Rate-limit. Срабатывание тоже пишем в audit.
    try:
        login_rate_limiter.check(email)
    except TooManyLoginAttempts:
        await service.record_login_attempt(
            db,
            email=email,
            success=False,
            ip_address=ip,
            user_agent=user_agent,
            failure_reason="rate_limited",
        )
        raise

    # 2) Аутентификация.
    try:
        admin = await service.authenticate_admin(db, email=email, password=payload.password)
    except InvalidCredentials:
        login_rate_limiter.record_failure(email)
        await service.record_login_attempt(
            db,
            email=email,
            success=False,
            ip_address=ip,
            user_agent=user_agent,
            failure_reason="invalid_credentials",
        )
        raise

    # 3) Успех — выдаём токен, фиксируем в audit, сбрасываем счётчик.
    login_rate_limiter.record_success(email)
    await service.record_login_attempt(
        db,
        email=email,
        success=True,
        admin_id=admin.id,
        ip_address=ip,
        user_agent=user_agent,
    )

    token = security.create_access_token(subject=admin.id)
    data = LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=admin_settings.jwt_expires_minutes * 60,
        admin=AdminResponse.model_validate(admin),
    )
    return Envelope(data=data, code=status.HTTP_200_OK)


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Текущий админ",
    description="Возвращает данные админа, чей JWT передан в заголовке `Authorization`.",
)
async def me(admin: CurrentAdmin) -> Envelope[AdminResponse]:
    return Envelope(data=AdminResponse.model_validate(admin), code=status.HTTP_200_OK)
