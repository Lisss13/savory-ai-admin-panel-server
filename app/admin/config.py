"""Настройки домена admin: JWT, rate-limit, bootstrap-учётка.

Источник правды — секция `[admin]` в `config/config.toml`. Путь к файлу,
как и для глобальных настроек, переопределяется переменной окружения
`APP_CONFIG_FILE` (см. `app/config.py`).

Дополнительно: `validate_admin_settings_for(environment)` — fail-fast,
если в production остались дефолтные секреты.
"""

from pathlib import Path
from typing import Any, cast

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from app.config import CONFIG_FILE

# Дефолтные значения вынесены константами, чтобы и `AdminSettings`, и
# `validate_admin_settings_for` смотрели на один и тот же список «небезопасных».
DEFAULT_JWT_SECRET = "change-me-in-production-please-rotate-32b"
DEFAULT_BOOTSTRAP_PASSWORD = "admin123"
PRODUCTION_ENVS = frozenset({"production", "prod"})


class _AdminTomlSource(TomlConfigSettingsSource):
    """Читает только секцию `[admin]` из TOML-файла."""

    def _read_file(self, file_path: Path) -> dict[str, Any]:
        data = super()._read_file(file_path)
        return cast(dict[str, Any], data.get("admin", {}))


class AdminSettings(BaseSettings):
    """Секция `[admin]` в config.toml."""

    model_config = SettingsConfigDict(
        toml_file=str(CONFIG_FILE),
        extra="ignore",
    )

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60

    # Rate-limit на /admin/auth/login (in-memory, per-email).
    login_max_attempts: int = 5
    login_window_minutes: int = 15
    login_lockout_minutes: int = 15

    bootstrap_email: str = "admin@savory.ai"
    bootstrap_password: str = DEFAULT_BOOTSTRAP_PASSWORD
    bootstrap_name: str = "Root Admin"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _AdminTomlSource(settings_cls),
            file_secret_settings,
        )


admin_settings = AdminSettings()


def validate_admin_settings_for(environment: str) -> None:
    """Fail-fast если в production остались дефолтные секреты.

    Зовётся из `create_app()` сразу после конструирования FastAPI — лучше
    упасть на старте, чем тихо запуститься со скомпрометированным `jwt_secret`
    или паролем `admin123`.
    """
    if environment not in PRODUCTION_ENVS:
        return
    insecure: list[str] = []
    if admin_settings.jwt_secret == DEFAULT_JWT_SECRET:
        insecure.append("admin.jwt_secret")
    if admin_settings.bootstrap_password == DEFAULT_BOOTSTRAP_PASSWORD:
        insecure.append("admin.bootstrap_password")
    if insecure:
        raise RuntimeError(
            f"Production deployment uses insecure default values: {', '.join(insecure)}. "
            "Override them in config.railway.toml / config.local.toml."
        )
