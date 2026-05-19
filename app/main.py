import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin import service as admin_service
from app.admin.config import validate_admin_settings_for
from app.admin.router import router as admin_router
from app.admin_log.router import router as admin_log_router
from app.config import settings
from app.dashboard.router import router as dashboard_router
from app.database import SessionFactory, engine
from app.exceptions import register_exception_handlers
from app.health.router import router as health_router
from app.languages.router import router as languages_router
from app.onboarding.router import router as onboarding_router
from app.organizations.router import router as organizations_router
from app.restaurants.router import router as restaurants_router
from app.support.router import router as support_router
from app.telegram.router import router as telegram_router

logger = logging.getLogger(__name__)

SHOW_DOCS_IN = {"local", "staging"}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # При старте — гарантируем существование bootstrap-админа (см. [admin] в config.toml).
    # Идемпотентно: если админ уже создан, ничего не делает.
    async with SessionFactory() as session:
        try:
            await admin_service.seed_default_admin(session)
        except Exception:
            # БД может быть недоступна (Railway, миграции не накатаны) — падать на
            # старте нельзя, но молчать тоже нельзя. Логируем, чтобы оператор увидел.
            logger.exception("seed_default_admin failed during startup")
            await session.rollback()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    # Fail-fast: в production запрещены дефолтные секреты.
    validate_admin_settings_for(settings.app.environment)

    app_kwargs: dict[str, Any] = {
        "title": settings.app.name,
        "lifespan": lifespan,
    }
    if settings.app.environment not in SHOW_DOCS_IN:
        app_kwargs["openapi_url"] = None  # отключает /docs и /redoc на проде

    app = FastAPI(**app_kwargs)

    # CORS для фронта admin_panel_global (см. секцию [cors] в config.toml).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
    )

    # Все ошибки приводятся к envelope {data, messages, code}.
    register_exception_handlers(app)

    app.include_router(health_router, prefix=settings.app.api_v1_prefix)
    app.include_router(admin_router, prefix=settings.app.api_v1_prefix)
    app.include_router(admin_log_router, prefix=settings.app.api_v1_prefix)
    app.include_router(languages_router, prefix=settings.app.api_v1_prefix)
    app.include_router(onboarding_router, prefix=settings.app.api_v1_prefix)
    app.include_router(support_router, prefix=settings.app.api_v1_prefix)
    app.include_router(telegram_router, prefix=settings.app.api_v1_prefix)
    app.include_router(restaurants_router, prefix=settings.app.api_v1_prefix)
    app.include_router(organizations_router, prefix=settings.app.api_v1_prefix)
    app.include_router(dashboard_router, prefix=settings.app.api_v1_prefix)
    return app


app = create_app()
