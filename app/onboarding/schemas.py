from datetime import datetime

from pydantic import EmailStr, Field
from pydantic_extra_types.phone_numbers import PhoneNumber

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
    id: int
    name: str = Field(min_length=1, max_length=256)
    phone: PhoneNumber
    email: EmailStr
    status: Status
