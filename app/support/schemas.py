from datetime import datetime

from pydantic import Field, EmailStr

from app.schemas import CamelModel
from app.support.constants import TicketStatus


class UserResp(CamelModel):
    id: int
    email: str
    phone: str | None
    name: str | None
    company: str | None


class SupportTicketResp(CamelModel):
    id: int
    title: str
    description: str
    email: str
    phone: str | None
    user: UserResp
    status: TicketStatus
    created_at: datetime
    updated_at: datetime


class SupportTicketUpdateReq(CamelModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = Field(None, min_length=1, max_length=2024)
    email: EmailStr | None = Field(None)
    phone: str | None = Field(None)
    status: TicketStatus | None = Field(
        default=None,
        description="Новый статус тикета",
    )
