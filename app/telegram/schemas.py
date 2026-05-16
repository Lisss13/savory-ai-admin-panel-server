from datetime import datetime

from app.schemas import CamelModel


class TelegramSubscriber(CamelModel):
    id: int
    chat_id: int
    username: str | None = None
    first_name: str | None = None
    created_at: datetime | None = None
