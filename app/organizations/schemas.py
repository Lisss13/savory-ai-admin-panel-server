from datetime import datetime

from app.schemas import CamelModel


class RestaurantResp(CamelModel):
    id: int
    name: str
    organization_id: int
    organization_name: str
    subscription_active: bool
    is_active: bool


class AdminResp(CamelModel):
    id: int
    name: str
    phone: str
    email: str


class SubscriptionResp(CamelModel):
    id: int
    end_date: datetime
    is_active: bool
    restaurants_count: int


class OrganizationResp(CamelModel):
    id: int
    name: str
    phone: str
    admin: AdminResp
    restaurants: list[RestaurantResp]
    restaurants_count: int
    subscriptions: list[SubscriptionResp]
