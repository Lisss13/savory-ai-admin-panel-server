"""Pydantic-схемы IO для admin-модуля.

Все поля JSON — camelCase (см. общий контракт API в `../CLAUDE.md`).
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas import CamelModel


class TokenPayload(BaseModel):
    """Полезная нагрузка JWT. `sub` — id админа в строковом виде."""

    sub: int
    exp: int


class LoginRequest(BaseModel):
    """Тело запроса логина."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class AdminResponse(CamelModel):
    """Публичное представление админа — без хеша пароля."""

    id: int
    email: EmailStr
    name: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LoginResponse(CamelModel):
    """Ответ на успешный логин."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # секунды до истечения
    admin: AdminResponse
