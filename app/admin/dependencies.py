"""FastAPI-зависимости admin-модуля."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import security, service
from app.admin.exceptions import AdminNotFound, InvalidToken
from app.admin.models import Admin
from app.database import get_db

# `auto_error=False` — мы сами решаем, что отдать при отсутствии заголовка
# (`InvalidToken` → 401 в нашем envelope-формате, а не дефолтная 403 от HTTPBearer).
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]
BearerCreds = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def get_current_admin(db: DbSession, creds: BearerCreds) -> Admin:
    """Извлекает текущего админа из Bearer-токена.

    Любая проблема (нет заголовка, мусорный/истёкший токен, удалённый или
    деактивированный админ) → `InvalidToken` (401).
    """
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise InvalidToken()

    payload = security.decode_access_token(creds.credentials)
    try:
        admin = await service.get_admin_by_id(db, payload.sub)
    except AdminNotFound as exc:
        raise InvalidToken() from exc

    if not admin.is_active:
        raise InvalidToken()
    return admin


CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]
