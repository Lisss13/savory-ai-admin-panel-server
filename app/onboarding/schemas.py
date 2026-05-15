from datetime import datetime

from pydantic import EmailStr, Field

from app.onboarding.constants import Status
from app.schemas import CamelModel


class OnboardingRequestResp(CamelModel):
    id: int
    name: str
    status: Status
    phone: str
    email: str
    created_at: datetime


class OnboardingUpdateReq(CamelModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=256, description="Имя пользователя"
    )
    phone: str | None = Field(default=None, description="Телефон")
    email: EmailStr | None = Field(default=None, description="Email")
    status: Status | None = Field(default=None, description="Статус")
