import datetime
import decimal
from typing import Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Double,
    ForeignKeyConstraint,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Languages(Base):
    __tablename__ = "languages"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="languages_pkey"),
        Index("idx_languages_code", "code", unique=True),
        Index("idx_languages_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    description: Mapped[str | None] = mapped_column(Text)

    questions: Mapped[list["Questions"]] = relationship("Questions", back_populates="language")


class OnboardingRequests(Base):
    __tablename__ = "onboarding_requests"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="onboarding_requests_pkey"),
        Index("idx_onboarding_requests_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))


class OrganizationLanguages(Base):
    __tablename__ = "organization_languages"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "language_id", name="organization_languages_pkey"),
    )

    organization_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    language_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class SchemaMigrations(Base):
    __tablename__ = "schema_migrations"
    __table_args__ = (PrimaryKeyConstraint("version", name="schema_migrations_pkey"),)

    version: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dirty: Mapped[bool] = mapped_column(Boolean, nullable=False)


class TelegramSubscribers(Base):
    __tablename__ = "telegram_subscribers"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="telegram_subscribers_pkey"),
        Index("idx_telegram_subscribers_chat_id", "chat_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))


class Users(Base):
    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="users_pkey"),
        UniqueConstraint("email", name="uni_users_email"),
        Index("idx_users_deleted_at", "deleted_at"),
        Index("idx_users_google_id", "google_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    google_id: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text, server_default=text("'user'::text"))
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))

    admin_logs: Mapped[list["AdminLogs"]] = relationship("AdminLogs", back_populates="admin")
    organizations: Mapped[list["Organizations"]] = relationship(
        "Organizations", back_populates="admin"
    )
    organization: Mapped[list["Organizations"]] = relationship(
        "Organizations", secondary="organization_users", back_populates="user"
    )
    password_reset_codes: Mapped[list["PasswordResetCodes"]] = relationship(
        "PasswordResetCodes", back_populates="user"
    )
    support_tickets: Mapped[list["SupportTickets"]] = relationship(
        "SupportTickets", back_populates="user"
    )
    subscription_extension_requests: Mapped[list["SubscriptionExtensionRequests"]] = relationship(
        "SubscriptionExtensionRequests", back_populates="user"
    )
    staff_invites: Mapped[list["StaffInvites"]] = relationship(
        "StaffInvites", back_populates="invited_by"
    )
    staffs: Mapped[list["Staffs"]] = relationship("Staffs", back_populates="user")


class AdminLogs(Base):
    __tablename__ = "admin_logs"
    __table_args__ = (
        ForeignKeyConstraint(["admin_id"], ["users.id"], name="fk_admin_logs_admin"),
        PrimaryKeyConstraint("id", name="admin_logs_pkey"),
        Index("idx_admin_logs_admin_id", "admin_id"),
        Index("idx_admin_logs_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(Text)

    admin: Mapped["Users"] = relationship("Users", back_populates="admin_logs")


class Organizations(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        ForeignKeyConstraint(["admin_id"], ["users.id"], name="fk_organizations_admin"),
        PrimaryKeyConstraint("id", name="organizations_pkey"),
        Index("idx_organizations_admin_id", "admin_id"),
        Index("idx_organizations_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))

    admin: Mapped["Users"] = relationship("Users", back_populates="organizations")
    user: Mapped[list["Users"]] = relationship(
        "Users", secondary="organization_users", back_populates="organization"
    )
    questions: Mapped[list["Questions"]] = relationship("Questions", back_populates="organization")
    restaurants: Mapped[list["Restaurants"]] = relationship(
        "Restaurants", back_populates="organization"
    )
    subscription_extension_requests: Mapped[list["SubscriptionExtensionRequests"]] = relationship(
        "SubscriptionExtensionRequests", back_populates="organization"
    )
    subscriptions: Mapped[list["Subscriptions"]] = relationship(
        "Subscriptions", back_populates="organization"
    )
    staff_invites: Mapped[list["StaffInvites"]] = relationship(
        "StaffInvites", back_populates="organization"
    )
    staffs: Mapped[list["Staffs"]] = relationship("Staffs", back_populates="organization")


class PasswordResetCodes(Base):
    __tablename__ = "password_reset_codes"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_password_reset_codes_user"),
        PrimaryKeyConstraint("id", name="password_reset_codes_pkey"),
        Index("idx_password_reset_codes_code", "code"),
        Index("idx_password_reset_codes_deleted_at", "deleted_at"),
        Index("idx_password_reset_codes_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))

    user: Mapped["Users"] = relationship("Users", back_populates="password_reset_codes")


class SupportTickets(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_support_tickets_user"),
        PrimaryKeyConstraint("id", name="support_tickets_pkey"),
        Index("idx_support_tickets_deleted_at", "deleted_at"),
        Index("idx_support_tickets_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'in_progress'::text")
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    phone: Mapped[str | None] = mapped_column(Text)

    user: Mapped["Users"] = relationship("Users", back_populates="support_tickets")


t_organization_users = Table(
    "organization_users",
    Base.metadata,
    Column("organization_id", BigInteger, primary_key=True),
    Column("user_id", BigInteger, primary_key=True),
    ForeignKeyConstraint(
        ["organization_id"], ["organizations.id"], name="fk_organization_users_organization"
    ),
    ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_organization_users_user"),
    PrimaryKeyConstraint("organization_id", "user_id", name="organization_users_pkey"),
)


class Questions(Base):
    __tablename__ = "questions"
    __table_args__ = (
        ForeignKeyConstraint(["language_id"], ["languages.id"], name="fk_questions_language"),
        ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_questions_organization"
        ),
        PrimaryKeyConstraint("id", name="questions_pkey"),
        Index("idx_questions_deleted_at", "deleted_at"),
        Index("idx_questions_organization_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    language_id: Mapped[int | None] = mapped_column(BigInteger)
    chat_type: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'menu'::character varying")
    )
    display_order: Mapped[int | None] = mapped_column(BigInteger, server_default=text("0"))

    language: Mapped[Optional["Languages"]] = relationship("Languages", back_populates="questions")
    organization: Mapped["Organizations"] = relationship(
        "Organizations", back_populates="questions"
    )


class Restaurants(Base):
    __tablename__ = "restaurants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_restaurants_organization"
        ),
        PrimaryKeyConstraint("id", name="restaurants_pkey"),
        Index("idx_restaurants_deleted_at", "deleted_at"),
        Index("idx_restaurants_organization_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    table_turnover_minutes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("15")
    )
    slot_interval: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("30")
    )
    ordering_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    website: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    image_key: Mapped[str | None] = mapped_column(Text)
    menu: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(Text, server_default=text("'USD'::text"))
    reservation_duration: Mapped[int | None] = mapped_column(BigInteger, server_default=text("90"))
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    show_dish_links: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    ai_suggestions_enabled: Mapped[bool | None] = mapped_column(
        Boolean, server_default=text("false")
    )
    default_language: Mapped[str | None] = mapped_column(Text, server_default=text("'en'::text"))
    yandex_maps_url: Mapped[str | None] = mapped_column(Text)
    google_maps_url: Mapped[str | None] = mapped_column(Text)
    waze_url: Mapped[str | None] = mapped_column(Text)
    instagram_url: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organizations"] = relationship(
        "Organizations", back_populates="restaurants"
    )
    ai_request_logs: Mapped[list["AiRequestLogs"]] = relationship(
        "AiRequestLogs", back_populates="restaurant"
    )
    menu_categories: Mapped[list["MenuCategories"]] = relationship(
        "MenuCategories", back_populates="restaurant"
    )
    restaurant_chat_sessions: Mapped[list["RestaurantChatSessions"]] = relationship(
        "RestaurantChatSessions", back_populates="restaurant"
    )
    restaurant_infos: Mapped[list["RestaurantInfos"]] = relationship(
        "RestaurantInfos", back_populates="restaurant"
    )
    staff_invites: Mapped[list["StaffInvites"]] = relationship(
        "StaffInvites", back_populates="restaurant"
    )
    staffs: Mapped[list["Staffs"]] = relationship("Staffs", back_populates="restaurant")
    tables: Mapped[list["Tables"]] = relationship("Tables", back_populates="restaurant")
    working_hours: Mapped[list["WorkingHours"]] = relationship(
        "WorkingHours", back_populates="restaurant"
    )
    bills: Mapped[list["Bills"]] = relationship("Bills", back_populates="restaurant")
    dishes: Mapped[list["Dishes"]] = relationship("Dishes", back_populates="restaurant")
    orders: Mapped[list["Orders"]] = relationship("Orders", back_populates="restaurant")
    reservations: Mapped[list["Reservations"]] = relationship(
        "Reservations", back_populates="restaurant"
    )
    restaurant_chat_messages: Mapped[list["RestaurantChatMessages"]] = relationship(
        "RestaurantChatMessages", back_populates="restaurant"
    )
    table_chat_sessions: Mapped[list["TableChatSessions"]] = relationship(
        "TableChatSessions", back_populates="restaurant"
    )
    table_chat_messages: Mapped[list["TableChatMessages"]] = relationship(
        "TableChatMessages", back_populates="restaurant"
    )


class SubscriptionExtensionRequests(Base):
    __tablename__ = "subscription_extension_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_subscription_extension_requests_organization",
        ),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_subscription_extension_requests_user"
        ),
        PrimaryKeyConstraint("id", name="subscription_extension_requests_pkey"),
        Index("idx_subscription_extension_requests_deleted_at", "deleted_at"),
        Index("idx_subscription_extension_requests_organization_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    period: Mapped[int | None] = mapped_column(BigInteger)
    requested_restaurant_limit: Mapped[int | None] = mapped_column(
        BigInteger, server_default=text("0")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text, server_default=text("'pending'::text"))
    admin_comment: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organizations"] = relationship(
        "Organizations", back_populates="subscription_extension_requests"
    )
    user: Mapped["Users"] = relationship("Users", back_populates="subscription_extension_requests")


class Subscriptions(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_organizations_subscription"
        ),
        PrimaryKeyConstraint("id", name="subscriptions_pkey"),
        Index("idx_subscriptions_deleted_at", "deleted_at"),
        Index("idx_subscriptions_organization_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_date: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    end_date: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    restaurant_limit: Mapped[int | None] = mapped_column(BigInteger, server_default=text("1"))

    organization: Mapped["Organizations"] = relationship(
        "Organizations", back_populates="subscriptions"
    )


class AiRequestLogs(Base):
    __tablename__ = "ai_request_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_ai_request_logs_restaurant"
        ),
        PrimaryKeyConstraint("id", name="ai_request_logs_pkey"),
        Index("idx_ai_request_logs_deleted_at", "deleted_at"),
        Index("idx_ai_request_logs_restaurant_id", "restaurant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    tokens_used: Mapped[int | None] = mapped_column(BigInteger, server_default=text("0"))

    restaurant: Mapped["Restaurants"] = relationship(
        "Restaurants", back_populates="ai_request_logs"
    )


class MenuCategories(Base):
    __tablename__ = "menu_categories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_menu_categories_restaurant"
        ),
        PrimaryKeyConstraint("id", name="menu_categories_pkey"),
        Index("idx_menu_categories_deleted_at", "deleted_at"),
        Index("idx_menu_categories_restaurant_id", "restaurant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    name_i18n: Mapped[dict | None] = mapped_column(JSONB)
    sort_order: Mapped[int | None] = mapped_column(BigInteger, server_default=text("0"))

    restaurant: Mapped["Restaurants"] = relationship(
        "Restaurants", back_populates="menu_categories"
    )
    dishes: Mapped[list["Dishes"]] = relationship("Dishes", back_populates="menu_category")


class RestaurantChatSessions(Base):
    __tablename__ = "restaurant_chat_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_restaurant_chat_sessions_restaurant"
        ),
        PrimaryKeyConstraint("id", name="restaurant_chat_sessions_pkey"),
        Index("idx_restaurant_chat_sessions_deleted_at", "deleted_at"),
        Index("idx_restaurant_chat_sessions_restaurant_id", "restaurant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_active: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    chat_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'reservation'::text")
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    last_suggestions: Mapped[list[str] | None] = mapped_column(ARRAY(Text()))

    restaurant: Mapped["Restaurants"] = relationship(
        "Restaurants", back_populates="restaurant_chat_sessions"
    )
    restaurant_chat_messages: Mapped[list["RestaurantChatMessages"]] = relationship(
        "RestaurantChatMessages", back_populates="chat_session"
    )


class RestaurantInfos(Base):
    __tablename__ = "restaurant_infos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_restaurant_infos_restaurant"
        ),
        PrimaryKeyConstraint("id", name="restaurant_infos_pkey"),
        Index("idx_restaurant_infos_deleted_at", "deleted_at"),
        Index("idx_restaurant_infos_restaurant_id", "restaurant_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    directions: Mapped[str | None] = mapped_column(Text)
    directions_i18n: Mapped[dict | None] = mapped_column(JSONB)
    parking: Mapped[str | None] = mapped_column(Text)
    parking_i18n: Mapped[dict | None] = mapped_column(JSONB)
    kitchen_hours: Mapped[str | None] = mapped_column(Text)
    kitchen_hours_i18n: Mapped[dict | None] = mapped_column(JSONB)
    terrace: Mapped[str | None] = mapped_column(Text)
    terrace_i18n: Mapped[dict | None] = mapped_column(JSONB)
    noise_level: Mapped[str | None] = mapped_column(Text)
    noise_level_i18n: Mapped[dict | None] = mapped_column(JSONB)
    kids_policy: Mapped[str | None] = mapped_column(Text)
    kids_policy_i18n: Mapped[dict | None] = mapped_column(JSONB)
    pets_policy: Mapped[str | None] = mapped_column(Text)
    pets_policy_i18n: Mapped[dict | None] = mapped_column(JSONB)
    dress_code: Mapped[str | None] = mapped_column(Text)
    dress_code_i18n: Mapped[dict | None] = mapped_column(JSONB)
    evening_vibe: Mapped[str | None] = mapped_column(Text)
    evening_vibe_i18n: Mapped[dict | None] = mapped_column(JSONB)
    halal: Mapped[str | None] = mapped_column(Text)
    halal_i18n: Mapped[dict | None] = mapped_column(JSONB)
    alcohol: Mapped[str | None] = mapped_column(Text)
    alcohol_i18n: Mapped[dict | None] = mapped_column(JSONB)
    dietary_options: Mapped[str | None] = mapped_column(Text)
    dietary_options_i18n: Mapped[dict | None] = mapped_column(JSONB)
    kids_dietary: Mapped[str | None] = mapped_column(Text)
    kids_dietary_i18n: Mapped[dict | None] = mapped_column(JSONB)
    dietary_adaptation: Mapped[str | None] = mapped_column(Text)
    dietary_adaptation_i18n: Mapped[dict | None] = mapped_column(JSONB)
    business_lunch: Mapped[str | None] = mapped_column(Text)
    business_lunch_i18n: Mapped[dict | None] = mapped_column(JSONB)
    smoking_area: Mapped[str | None] = mapped_column(Text)
    smoking_area_i18n: Mapped[dict | None] = mapped_column(JSONB)
    delivery: Mapped[str | None] = mapped_column(Text)
    delivery_i18n: Mapped[dict | None] = mapped_column(JSONB)
    private_events: Mapped[str | None] = mapped_column(Text)
    private_events_i18n: Mapped[dict | None] = mapped_column(JSONB)
    reservation_policy: Mapped[str | None] = mapped_column(Text)
    reservation_policy_i18n: Mapped[dict | None] = mapped_column(JSONB)
    accessibility: Mapped[str | None] = mapped_column(Text)
    accessibility_i18n: Mapped[dict | None] = mapped_column(JSONB)
    loyalty: Mapped[str | None] = mapped_column(Text)
    loyalty_i18n: Mapped[dict | None] = mapped_column(JSONB)
    payment: Mapped[str | None] = mapped_column(Text)
    payment_i18n: Mapped[dict | None] = mapped_column(JSONB)

    restaurant: Mapped["Restaurants"] = relationship(
        "Restaurants", back_populates="restaurant_infos"
    )


class StaffInvites(Base):
    __tablename__ = "staff_invites"
    __table_args__ = (
        ForeignKeyConstraint(["invited_by_id"], ["users.id"], name="fk_staff_invites_invited_by"),
        ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_staff_invites_organization"
        ),
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_staff_invites_restaurant"
        ),
        PrimaryKeyConstraint("id", name="staff_invites_pkey"),
        Index("idx_staff_invites_deleted_at", "deleted_at"),
        Index("idx_staff_invites_token", "token", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    invited_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    permissions: Mapped[list[str] | None] = mapped_column(ARRAY(Text()))
    accepted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    accepted_by_id: Mapped[int | None] = mapped_column(BigInteger)

    invited_by: Mapped["Users"] = relationship("Users", back_populates="staff_invites")
    organization: Mapped["Organizations"] = relationship(
        "Organizations", back_populates="staff_invites"
    )
    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="staff_invites")


class Staffs(Base):
    __tablename__ = "staffs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name="fk_staffs_organization"
        ),
        ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], name="fk_staffs_restaurant"),
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_staffs_user"),
        PrimaryKeyConstraint("id", name="staffs_pkey"),
        Index("idx_restaurant_user", "restaurant_id", "user_id", unique=True),
        Index("idx_staffs_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    permissions: Mapped[list[str] | None] = mapped_column(ARRAY(Text()))

    organization: Mapped["Organizations"] = relationship("Organizations", back_populates="staffs")
    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="staffs")
    user: Mapped["Users"] = relationship("Users", back_populates="staffs")


class Tables(Base):
    __tablename__ = "tables"
    __table_args__ = (
        ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], name="fk_tables_restaurant"),
        PrimaryKeyConstraint("id", name="tables_pkey"),
        Index("idx_tables_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    guest_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    menu: Mapped[str | None] = mapped_column(Text)

    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="tables")
    bills: Mapped[list["Bills"]] = relationship("Bills", back_populates="table")
    orders: Mapped[list["Orders"]] = relationship("Orders", back_populates="table")
    reservations: Mapped[list["Reservations"]] = relationship(
        "Reservations", back_populates="table"
    )
    table_chat_sessions: Mapped[list["TableChatSessions"]] = relationship(
        "TableChatSessions", back_populates="table"
    )
    table_chat_messages: Mapped[list["TableChatMessages"]] = relationship(
        "TableChatMessages", back_populates="table"
    )


class WorkingHours(Base):
    __tablename__ = "working_hours"
    __table_args__ = (
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_restaurants_working_hours"
        ),
        PrimaryKeyConstraint("id", name="working_hours_pkey"),
        Index("idx_working_hours_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day_of_week: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open_time: Mapped[str] = mapped_column(Text, nullable=False)
    close_time: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    is_overnight: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))

    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="working_hours")


class Bills(Base):
    __tablename__ = "bills"
    __table_args__ = (
        ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], name="fk_bills_restaurant"),
        ForeignKeyConstraint(["table_id"], ["tables.id"], name="fk_bills_table"),
        PrimaryKeyConstraint("id", name="bills_pkey"),
        Index(
            "idx_bills_active_per_table",
            "table_id",
            postgresql_where=(
                "((status = ANY (ARRAY['open'::text, 'awaiting_payment'::text]))"
                " AND (deleted_at IS NULL))"
            ),
            unique=True,
        ),
        Index("idx_bills_deleted_at", "deleted_at"),
        Index("idx_bills_restaurant_id", "restaurant_id"),
        Index("idx_bills_status", "status"),
        Index("idx_bills_table_id", "table_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    table_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'::text"))
    total_amount: Mapped[float] = mapped_column(
        Double(53), nullable=False, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'USD'::text"))
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    notes: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    closed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    closed_by_user_id: Mapped[int | None] = mapped_column(BigInteger)

    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="bills")
    table: Mapped["Tables"] = relationship("Tables", back_populates="bills")
    bill_items: Mapped[list["BillItems"]] = relationship("BillItems", back_populates="bill")


class Dishes(Base):
    __tablename__ = "dishes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["menu_category_id"], ["menu_categories.id"], name="fk_dishes_menu_category"
        ),
        ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], name="fk_dishes_restaurant"),
        PrimaryKeyConstraint("id", name="dishes_pkey"),
        Index("idx_dishes_deleted_at", "deleted_at"),
        Index("idx_dishes_restaurant_id", "restaurant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    menu_category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)
    image_key: Mapped[str | None] = mapped_column(Text)
    is_dish_of_day: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    is_available: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    cooking_time: Mapped[int | None] = mapped_column(BigInteger, server_default=text("0"))
    is_vegetarian: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    proteins: Mapped[decimal.Decimal | None] = mapped_column(Numeric, server_default=text("0"))
    fats: Mapped[decimal.Decimal | None] = mapped_column(Numeric, server_default=text("0"))
    carbohydrates: Mapped[decimal.Decimal | None] = mapped_column(Numeric, server_default=text("0"))
    calories: Mapped[decimal.Decimal | None] = mapped_column(Numeric, server_default=text("0"))
    name_i18n: Mapped[dict | None] = mapped_column(JSONB)
    description_i18n: Mapped[dict | None] = mapped_column(JSONB)

    menu_category: Mapped["MenuCategories"] = relationship(
        "MenuCategories", back_populates="dishes"
    )
    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="dishes")
    allergens: Mapped[list["Allergens"]] = relationship("Allergens", back_populates="dish")
    ingredients: Mapped[list["Ingredients"]] = relationship("Ingredients", back_populates="dish")
    order_items: Mapped[list["OrderItems"]] = relationship("OrderItems", back_populates="dish")
    bill_items: Mapped[list["BillItems"]] = relationship("BillItems", back_populates="dish")


class Orders(Base):
    __tablename__ = "orders"
    __table_args__ = (
        ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], name="fk_orders_restaurant"),
        ForeignKeyConstraint(["table_id"], ["tables.id"], name="fk_orders_table"),
        PrimaryKeyConstraint("id", name="orders_pkey"),
        Index("idx_orders_chat_session_id", "chat_session_id"),
        Index("idx_orders_deleted_at", "deleted_at"),
        Index("idx_orders_restaurant_id", "restaurant_id"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_table_id", "table_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    table_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'new'::text"))
    total_amount: Mapped[float] = mapped_column(
        Double(53), nullable=False, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'USD'::text"))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'cart'::text"))
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    chat_session_id: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)

    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="orders")
    table: Mapped["Tables"] = relationship("Tables", back_populates="orders")
    order_items: Mapped[list["OrderItems"]] = relationship("OrderItems", back_populates="order")


class Reservations(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_reservations_restaurant"
        ),
        ForeignKeyConstraint(["table_id"], ["tables.id"], name="fk_reservations_table"),
        PrimaryKeyConstraint("id", name="reservations_pkey"),
        Index("idx_reservations_deleted_at", "deleted_at"),
        Index("idx_reservations_reservation_date", "reservation_date"),
        Index("idx_reservations_restaurant_id", "restaurant_id"),
        Index("idx_reservations_table_id", "table_id"),
        Index(
            "uq_reservations_active_slot",
            "table_id",
            "reservation_date",
            "start_time",
            postgresql_where="((status <> 'cancelled'::text) AND (deleted_at IS NULL))",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    table_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_phone: Mapped[str] = mapped_column(Text, nullable=False)
    guest_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reservation_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[str] = mapped_column(Text, nullable=False)
    end_time: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'::text")
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    customer_email: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    chat_session_id: Mapped[int | None] = mapped_column(BigInteger)

    restaurant: Mapped["Restaurants"] = relationship("Restaurants", back_populates="reservations")
    table: Mapped["Tables"] = relationship("Tables", back_populates="reservations")


class RestaurantChatMessages(Base):
    __tablename__ = "restaurant_chat_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chat_session_id"],
            ["restaurant_chat_sessions.id"],
            name="fk_restaurant_chat_sessions_messages",
        ),
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_restaurant_chat_messages_restaurant"
        ),
        PrimaryKeyConstraint("id", name="restaurant_chat_messages_pkey"),
        Index("idx_restaurant_chat_messages_chat_session_id", "chat_session_id"),
        Index("idx_restaurant_chat_messages_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_session_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))

    chat_session: Mapped["RestaurantChatSessions"] = relationship(
        "RestaurantChatSessions", back_populates="restaurant_chat_messages"
    )
    restaurant: Mapped["Restaurants"] = relationship(
        "Restaurants", back_populates="restaurant_chat_messages"
    )


class TableChatSessions(Base):
    __tablename__ = "table_chat_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_table_chat_sessions_restaurant"
        ),
        ForeignKeyConstraint(["table_id"], ["tables.id"], name="fk_table_chat_sessions_table"),
        PrimaryKeyConstraint("id", name="table_chat_sessions_pkey"),
        Index("idx_table_chat_sessions_deleted_at", "deleted_at"),
        Index("idx_table_chat_sessions_restaurant_id", "restaurant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_active: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    last_suggestions: Mapped[list[str] | None] = mapped_column(ARRAY(Text()))

    restaurant: Mapped["Restaurants"] = relationship(
        "Restaurants", back_populates="table_chat_sessions"
    )
    table: Mapped["Tables"] = relationship("Tables", back_populates="table_chat_sessions")
    table_chat_messages: Mapped[list["TableChatMessages"]] = relationship(
        "TableChatMessages", back_populates="chat_session"
    )


class Allergens(Base):
    __tablename__ = "allergens"
    __table_args__ = (
        ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_dishes_allergens"),
        PrimaryKeyConstraint("id", name="allergens_pkey"),
        Index("idx_allergens_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dish_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    description: Mapped[str | None] = mapped_column(Text)

    dish: Mapped["Dishes"] = relationship("Dishes", back_populates="allergens")


class Ingredients(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_dishes_ingredients"),
        PrimaryKeyConstraint("id", name="ingredients_pkey"),
        Index("idx_ingredients_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dish_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))

    dish: Mapped["Dishes"] = relationship("Dishes", back_populates="ingredients")


class OrderItems(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dish_id"], ["dishes.id"], ondelete="RESTRICT", name="fk_order_items_dish"
        ),
        ForeignKeyConstraint(
            ["order_id"], ["orders.id"], ondelete="CASCADE", name="fk_order_items_order"
        ),
        PrimaryKeyConstraint("id", name="order_items_pkey"),
        Index("idx_order_items_deleted_at", "deleted_at"),
        Index("idx_order_items_dish_id", "dish_id"),
        Index("idx_order_items_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dish_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))
    price_at_order: Mapped[float] = mapped_column(
        Double(53), nullable=False, server_default=text("0")
    )
    dish_name_at_order: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''::text")
    )
    currency_at_order: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''::text")
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))

    dish: Mapped["Dishes"] = relationship("Dishes", back_populates="order_items")
    order: Mapped["Orders"] = relationship("Orders", back_populates="order_items")
    bill_items: Mapped[list["BillItems"]] = relationship(
        "BillItems", back_populates="source_order_item"
    )


class TableChatMessages(Base):
    __tablename__ = "table_chat_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chat_session_id"], ["table_chat_sessions.id"], name="fk_table_chat_sessions_messages"
        ),
        ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], name="fk_table_chat_messages_restaurant"
        ),
        ForeignKeyConstraint(["table_id"], ["tables.id"], name="fk_table_chat_messages_table"),
        PrimaryKeyConstraint("id", name="table_chat_messages_pkey"),
        Index("idx_table_chat_messages_chat_session_id", "chat_session_id"),
        Index("idx_table_chat_messages_deleted_at", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_session_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))

    chat_session: Mapped["TableChatSessions"] = relationship(
        "TableChatSessions", back_populates="table_chat_messages"
    )
    restaurant: Mapped["Restaurants"] = relationship(
        "Restaurants", back_populates="table_chat_messages"
    )
    table: Mapped["Tables"] = relationship("Tables", back_populates="table_chat_messages")


class BillItems(Base):
    __tablename__ = "bill_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bill_id"], ["bills.id"], ondelete="CASCADE", name="fk_bill_items_bill"
        ),
        ForeignKeyConstraint(
            ["dish_id"], ["dishes.id"], ondelete="RESTRICT", name="fk_bill_items_dish"
        ),
        ForeignKeyConstraint(
            ["source_order_item_id"],
            ["order_items.id"],
            ondelete="SET NULL",
            name="fk_bill_items_source_order_item",
        ),
        PrimaryKeyConstraint("id", name="bill_items_pkey"),
        Index("idx_bill_items_bill_id", "bill_id"),
        Index("idx_bill_items_chat_session", "chat_session_id_at_item"),
        Index("idx_bill_items_deleted_at", "deleted_at"),
        Index("idx_bill_items_dish_id", "dish_id"),
        Index("idx_bill_items_source_order_item", "source_order_item_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dish_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))
    price_at_bill: Mapped[float] = mapped_column(
        Double(53), nullable=False, server_default=text("0")
    )
    dish_name_at_bill: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''::text")
    )
    currency_at_bill: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''::text")
    )
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(True))
    source_order_item_id: Mapped[int | None] = mapped_column(BigInteger)
    chat_session_id_at_item: Mapped[int | None] = mapped_column(BigInteger)
    added_by_user_id: Mapped[int | None] = mapped_column(BigInteger)

    bill: Mapped["Bills"] = relationship("Bills", back_populates="bill_items")
    dish: Mapped["Dishes"] = relationship("Dishes", back_populates="bill_items")
    source_order_item: Mapped[Optional["OrderItems"]] = relationship(
        "OrderItems", back_populates="bill_items"
    )
