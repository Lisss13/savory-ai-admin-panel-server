from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.exceptions import register_exception_handlers
from app.health.router import router as health_router

SHOW_DOCS_IN = {"local", "staging"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app_kwargs: dict = {
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
    return app


app = create_app()
