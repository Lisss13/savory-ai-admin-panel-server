"""Рендерит config.railway.toml из переменных окружения Railway.

Приложение читает настройки только из TOML (см. `app/config.py`,
`app/admin/config.py`). Railway, наоборот, инжектит переменные окружения.
Этот скрипт стартует до uvicorn — собирает TOML из ENV и кладёт его по пути
`APP_CONFIG_FILE` (по умолчанию `/tmp/config.railway.toml`). Дальше pydantic-
settings подхватывает файл штатным `TomlConfigSettingsSource`.

Зачем отдельный шаг рендера, а не env-source: в коде приложения принят
правилом «никаких os.getenv» (см. CLAUDE.md). Этот скрипт — bootstrap вне
рантайма приложения, в нём env-vars читать можно.

Список ожидаемых переменных и значения по умолчанию — см. `RAILWAY.md`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Дефолтный путь для отрендеренного конфига. Тот же путь зашит в start.sh.
DEFAULT_OUT_PATH = Path("/tmp/config.railway.toml")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    """Читает переменную окружения с понятной ошибкой, если она обязательна."""
    val = os.environ.get(name, default)
    if required and (val is None or val == ""):
        _ = sys.stderr.write(f"[render_railway_config] missing required env var: {name}\n")
        sys.exit(1)
    return val or ""


def normalize_dsn(url: str) -> str:
    """Приводит DSN к asyncpg-форме, которую ждёт app/database.py."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        _ = sys.stderr.write(f"[render_railway_config] {name} must be int: {exc}\n")
        sys.exit(1)


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    """Парсит CSV-список (пробелы триммим, пустые элементы выбрасываем)."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


def toml_value(value: object) -> str:
    """Минимальный TOML-сериализатор для типов, которые мы реально используем."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def render(config: dict[str, dict[str, object]]) -> str:
    lines: list[str] = ["# Сгенерировано scripts/render_railway_config.py — не редактируй руками."]
    for section, fields in config.items():
        lines.append("")
        lines.append(f"[{section}]")
        for key, value in fields.items():
            lines.append(f"{key} = {toml_value(value)}")
    return "\n".join(lines) + "\n"


def build_config() -> dict[str, dict[str, object]]:
    return {
        "app": {
            "name": env("APP_NAME", "admin-panel-global-server"),
            "environment": env("APP_ENVIRONMENT", "production"),
            "api_v1_prefix": env("API_V1_PREFIX", "/api/v1"),
        },
        "database": {
            "url": normalize_dsn(env("DATABASE_URL", required=True)),
            "echo": env_bool("DB_ECHO", False),
            "pool_size": env_int("DB_POOL_SIZE", 5),
            "max_overflow": env_int("DB_MAX_OVERFLOW", 10),
        },
        "cors": {
            "allow_origins": env_list("CORS_ALLOW_ORIGINS"),
            "allow_credentials": env_bool("CORS_ALLOW_CREDENTIALS", True),
            "allow_methods": env_list("CORS_ALLOW_METHODS", ["*"]),
            "allow_headers": env_list("CORS_ALLOW_HEADERS", ["*"]),
        },
        "admin": {
            "jwt_secret": env("ADMIN_JWT_SECRET", required=True),
            "jwt_algorithm": env("ADMIN_JWT_ALGORITHM", "HS256"),
            "jwt_expires_minutes": env_int("ADMIN_JWT_EXPIRES_MINUTES", 60),
            "login_max_attempts": env_int("ADMIN_LOGIN_MAX_ATTEMPTS", 5),
            "login_window_minutes": env_int("ADMIN_LOGIN_WINDOW_MINUTES", 15),
            "login_lockout_minutes": env_int("ADMIN_LOGIN_LOCKOUT_MINUTES", 15),
            "bootstrap_email": env("ADMIN_BOOTSTRAP_EMAIL", required=True),
            "bootstrap_password": env("ADMIN_BOOTSTRAP_PASSWORD", required=True),
            "bootstrap_name": env("ADMIN_BOOTSTRAP_NAME", "Root Admin"),
        },
    }


def main() -> None:
    out_path = Path(os.environ.get("APP_CONFIG_FILE", str(DEFAULT_OUT_PATH)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _ = out_path.write_text(render(build_config()), encoding="utf-8")
    _ = sys.stdout.write(f"[render_railway_config] wrote {out_path}\n")


if __name__ == "__main__":
    main()
