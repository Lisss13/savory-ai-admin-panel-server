# admin-panel-global-server

FastAPI-бэкенд глобальной админки Savory AI. Часть воркспейса `../` — основной потребитель API это Next.js фронт `../admin_panel_global/` на `:3040`. Не путать с Go-`../server/` — это два независимых сервиса. Управление зависимостями — через [uv](https://docs.astral.sh/uv/).

Принципы — по скиллу `.claude/skills/fastapi-best-practices/SKILL.md` (организация по доменам, async-стек целиком, `Annotated`-зависимости, Pydantic v2, SQLAlchemy 2.0 async, PyJWT, ruff, pytest+httpx). Контекст по проекту и подводным камням — в [CLAUDE.md](CLAUDE.md).

## Стек

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy 2.x (async) + asyncpg
- Alembic (async-шаблон, date-prefixed filenames)
- pydantic-settings + TOML (`config/config.toml`, без `.env`)
- PyJWT (HS256) + bcrypt — JWT-аутентификация админа
- pytest + pytest-asyncio + httpx (`ASGITransport`) + aiosqlite (in-memory тестовая БД)
- ruff + mypy

## Структура

```
app/
├── {domain}/                 # admin, admin_log, dashboard, organizations,
│   ├── router.py             # restaurants, subscriptions, onboarding,
│   ├── schemas.py            # support, languages, telegram, health
│   ├── service.py
│   ├── dependencies.py       # опционально
│   ├── constants.py          # опционально
│   ├── exceptions.py         # опционально
│   └── models.py             # ORM только у доменов со своими таблицами
│
├── common/                   # переиспользуемое между доменами
│   ├── database/soft_delete.py
│   └── utils/{pagination,diff}.py
│
├── lib/                      # generic-обёртки, не знают о домене
│   └── security/{jwt,passwords}.py
│
├── config.py                 # загрузка config/config.toml в Settings
├── database.py               # async engine + SessionFactory + get_db
├── models.py                 # Base + MetaData (naming_convention)
├── schemas.py                # Envelope[T] + CamelModel (snake → camel)
├── exceptions.py             # AppException + handlers (всё → envelope)
└── main.py                   # create_app() + lifespan + CORS + роутеры

alembic/                      # миграции, file_template: YYYY-MM-DD_slug.py
config/config.toml            # единственный источник правды для настроек
tests/<domain>/               # тесты зеркалят структуру app/
```

## Установка

```bash
uv sync
$EDITOR config/config.toml            # настроить под себя, прежде всего [database].url
```

Альтернативный TOML — через `APP_CONFIG_FILE=config/config.railway.toml`. Локальный личный оверрайд (в `.gitignore`) — `config/config.local.toml`. Переменные окружения сознательно не подмешиваются — единственным источником правды остаётся файл.

## Конфигурация

Секции `config/config.toml`:

- `[app]` — `environment` (`local`/`staging`/`production`/`prod`), `api_v1_prefix`.
- `[database]` — DSN с `postgresql+asyncpg://`, `echo`, `pool_size`, `max_overflow`.
- `[cors]` — список origin'ов для фронта (`http://localhost:3040` по умолчанию). При `allow_credentials = true` нельзя `"*"` — браузер заблокирует ответ.
- `[admin]` — `jwt_secret`, `jwt_algorithm`, `jwt_expires_minutes`, rate-limit логина (`login_max_attempts`/`window`/`lockout` в минутах), bootstrap-учётка (`bootstrap_email`/`bootstrap_password`/`bootstrap_name`).

**В production обязательно переопредели `[admin].jwt_secret` и `[admin].bootstrap_password`** — `validate_admin_settings_for` падает на старте, если они остались дефолтными.

## Миграции

```bash
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
uv run alembic downgrade -1
```

`alembic/env.py` читает DSN из `app.config.settings.database.url` (значение в `alembic.ini` — заглушка). При добавлении нового домена с ORM-моделями допиши импорт `from app.<domain> import models as _<domain>_models  # noqa: F401` в `alembic/env.py`, иначе autogenerate не увидит таблицы.

## Запуск

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- Healthcheck: `GET http://localhost:8000/api/v1/health`
- OpenAPI (только при `[app].environment` ∈ `{local, staging}`): `http://localhost:8000/docs`
- Логин админа: `POST /api/v1/admin/auth/login` (bootstrap-учётка из `[admin]`), затем JWT в `Authorization: Bearer …`.

При первом старте `lifespan` идемпотентно создаёт bootstrap-админа из `[admin].bootstrap_*` — отдельный seed запускать не надо.

## Проверки (тесты, линтер, типы)

```bash
uv run pytest                      # тесты (in-memory SQLite через aiosqlite)
uv run pytest tests/admin -v       # тесты одного домена
uv run ruff check .                # линтер
uv run ruff format --check .       # форматирование (без правок)
uv run mypy                        # статические типы (app + tests)
```

Автофиксы:

```bash
uv run ruff check --fix .
uv run ruff format .
```

Прогон всего разом перед коммитом:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

## Контракт API (наследуется от воркспейса)

- Все ответы в envelope: `{ "data": ..., "messages": [...], "code": 200 }`. Ошибки — в той же форме через `register_exception_handlers`.
- JSON-поля наружу — **camelCase** (`createdAt`, `userId`). Response-схемы наследуются от `CamelModel`, snake_case в коде остаётся.
- HTTP-коды: `400` (валидация), `401` (нет/невалидный JWT), `403` (недостаточно прав), `404` (не найдено), `429` (rate-limit).
- Авторизация: JWT HS256, фронт хранит токен в cookie `savory_admin_token`. Любой защищённый endpoint вешает `_admin: CurrentAdmin`.
- Комментарии в коде и docstring-и тестов — на русском.
- Коммитить только в ветку `test`, в `main` — через PR.

## Доменные endpoints (кратко)

| Префикс | Что покрывает |
|---------|----------------|
| `/health` | Liveness/readiness — единственный публичный |
| `/admin/auth` | Логин, `/me`, `/create-admin` |
| `/admin/logs` | Аудит-журнал (полный + `/me`) |
| `/dashboard` | Сводные счётчики |
| `/organizations` | Список орг с админом и ресторанами |
| `/restaurants` | Список/детали ресторанов, фильтр по активной подписке, AI-лимит |
| `/admin/subscriptions` + `/subscriptions/extension-requests` | Подписки и заявки на продление (approve/reject) |
| `/onboarding` | Заявки с лендинга, статусы `new → contacted → onboarding → installed` |
| `/support` | Тикеты поддержки |
| `/languages` | Справочник языков |
| `/telegram` | Подписчики Telegram-уведомлений |
