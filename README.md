# admin-panel-global-server

Бэкенд админ-панели на FastAPI + PostgreSQL. Управление зависимостями — через [uv](https://docs.astral.sh/uv/).

Структура и принципы — по скиллу `.claude/skills/fastapi-best-practices/SKILL.md` (организация по доменам, async-стек целиком, `Annotated`-зависимости, Pydantic v2, SQLAlchemy 2.0 async, PyJWT, ruff, pytest+httpx).

## Стек

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy 2.x (async) + asyncpg
- Alembic (async-шаблон, date-prefixed filenames)
- pydantic-settings + TOML (`config/config.toml`)
- pytest + pytest-asyncio + httpx (`ASGITransport`)
- ruff

## Структура

```
app/
├── {domain}/           # пакет на bounded context (сейчас: health/)
│   ├── router.py       # APIRouter
│   ├── schemas.py      # Pydantic IO
│   ├── models.py       # ORM (наследник app.models.Base)
│   ├── service.py      # бизнес-логика (по мере появления)
│   ├── dependencies.py
│   ├── config.py       # доменный BaseSettings (читает свою секцию TOML)
│   ├── constants.py
│   └── exceptions.py
├── config.py           # загрузка config/config.toml в Pydantic Settings
├── database.py         # async engine + SessionFactory + get_db
├── models.py           # Base + MetaData (naming_convention для индексов)
├── exceptions.py       # AppException
└── main.py             # create_app() + lifespan
alembic/                # миграции (file_template: YYYY-MM-DD_slug.py)
config/                 # config.toml — единственный источник правды для настроек
tests/                  # pytest, conftest c фикстурой `client`
```

## Установка

```bash
uv sync
# при необходимости отредактируй настройки:
$EDITOR config/config.toml
```

Альтернативный файл можно подсунуть через `APP_CONFIG_FILE=config/config.railway.toml`.

## Миграции

```bash
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
uv run alembic downgrade -1
```

При добавлении нового домена с ORM-моделями допиши его импорт в `alembic/env.py`, иначе autogenerate не увидит таблицы.

## Запуск

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- Healthcheck: `GET http://localhost:8000/api/v1/health`
- OpenAPI (только при `[app].environment` ∈ `{local, staging}`): `http://localhost:8000/docs`

## Тесты и линтер

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```
