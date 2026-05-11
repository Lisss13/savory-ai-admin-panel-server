"""Глобальные настройки приложения.

Источник правды — `config/config.toml`. Путь можно переопределить переменной
окружения `APP_CONFIG_FILE` (например, на проде указать `config/config.railway.toml`).

Доменные настройки выносятся в `app/{domain}/config.py` со своим BaseSettings.
"""

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "config.toml"
CONFIG_FILE = Path(os.environ.get("APP_CONFIG_FILE", DEFAULT_CONFIG_FILE))

# Единый нейтральный DSN: используется и как fallback здесь, и как заглушка
# в alembic.ini, и как дефолт в config/config.toml. Реальные креды задаются
# через альтернативный TOML (config.local.toml / config.railway.toml).
DEFAULT_DATABASE_URL = "postgresql+asyncpg://savory_admin:savory_password@localhost:5432/savory_db"


class AppSettings(BaseModel):
    """Секция `[app]` в config.toml."""

    name: str = "admin-panel-global-server"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"


class DatabaseSettings(BaseModel):
    """Секция `[database]` в config.toml."""

    url: str = DEFAULT_DATABASE_URL
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10


class CorsSettings(BaseModel):
    """Секция `[cors]` в config.toml — настройки CORS-мидлвари.

    Дефолты соответствуют локальному фронту admin_panel_global на :3040.
    """

    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = True
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class Settings(BaseSettings):
    """Корневая модель конфигурации. Загружается из TOML-файла."""

    model_config = SettingsConfigDict(
        toml_file=str(CONFIG_FILE),
        extra="ignore",
    )

    app: AppSettings = AppSettings()
    database: DatabaseSettings = DatabaseSettings()
    cors: CorsSettings = CorsSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Только TOML + init/secret. Переменные окружения сознательно
        # не подмешиваем, чтобы единственным источником правды был файл.
        return (
            init_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()
