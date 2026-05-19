from pydantic import BaseModel


class AppStats(BaseModel):
    total_organizations: int
    total_restaurants: int
    total_subscriptions: int
