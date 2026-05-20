# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Это отдельный Python-репозиторий внутри воркспейса Savory AI. Верхнеуровневый контекст — в `../CLAUDE.md` (роль каждого сервиса, общий контракт API, бизнес-флоу). Здесь — только то, что специфично для этого backend'а.

## Обязательный скилл

**Перед любой работой с кодом в этом репозитории вызови скилл `fastapi-best-practices`** (project-level, лежит в `.claude/skills/fastapi-best-practices/SKILL.md`). Он содержит правила версий, async/sync decision rule, Pydantic v2 паттерны, dependency injection через `Annotated`, SQLAlchemy 2.0 async, JWT (PyJWT), pytest+httpx, миграции Alembic и таблицу анти-паттернов.

Вызов: `Skill(skill="fastapi-best-practices")`.

Триггерится на: добавление/правка роутов, Pydantic-моделей, ORM-моделей, dependencies, миграций, JWT-логики, фоновых задач, тестов — **даже если пользователь не упомянул FastAPI явно**. Также вызывай его при ревью diff'а, чтобы проверить чек-лист анти-паттернов. Если скилл уже был загружен в текущей сессии, повторно не вызывай — его содержимое уже в контексте.

## Место в системе

**Что это:** выделенный FastAPI-бэкенд для глобальной админки Savory (`../admin_panel_global/`). Появился как отдельный сервис, потому что основной Go-бэкенд (`../server/`) обслуживает ресторанные сценарии (гости, столики, AI-чат, меню, бронирования), а админская часть (управление орг/пользователями, модерация, аналитика, обработка заявок) выделяется в собственный сервис со своей БД и своим темпом разработки.

**Продукт:** Savory AI — AI-цифровой официант для ресторанов (QR-меню + AI-заказы/бронирования, B2B в ОАЭ).

**Воркспейс целиком** (`../`) состоит из независимых git-репозиториев:

| Каталог | Роль | Стек | Dev порт |
|---------|------|------|----------|
| `server/` | Основной REST API для ресторанной части | Go + Fiber v3 + GORM + PostgreSQL + Uber FX + Claude | `:4000` |
| **`admin_panel_global_server/`** (этот) | **REST API для глобальной админки Savory** | **Python 3.12 + FastAPI + SQLAlchemy async + asyncpg + Alembic** | **`:8000`** |
| `admin_panel_global/` | Frontend глобальной админки — основной потребитель этого API | Next.js 16 + shadcn/ui + Zustand + TanStack Query + Axios | `:3040` |
| `restaurant-dashboard/` | Админка ресторатора (общается с `server/`, не с этим сервисом) | Next.js 16 + shadcn/ui + Zustand + Axios | `:3030` |
| `savary_ai_chat/` | Гостевой чат по QR (общается с `server/`) | Next.js 16 + React Context + fetch | `:3000` |
| `savory-landing/` | Маркетинговый лендинг | Next.js 16 + Tailwind v4 | `:3000` |

**Схема взаимодействия:**

```
admin_panel_global (:3040, Next.js)            ←  основной потребитель этого API
  ├── Axios с JWT в cookie `savory_admin_token`
  │   role === 'admin' (gate)
  ▼
admin_panel_global_server (:8000, FastAPI)     ←  этот сервис
  └── PostgreSQL (своя схема)

server (:4000, Go)                              ←  отдельный домен (рестораны, гости, AI)
  ├── restaurant-dashboard (:3030)
  └── savary_ai_chat (:3000)
```

Сервис **не** заменяет `server/` — это отдельный backend для админских сценариев. Если потребуется делиться данными между ними, делать это через REST/события, а не через общую БД.

## Контракт API (наследуется от воркспейса)

Эти правила едины для всех бэкендов Savory — соблюдаем их и здесь, чтобы клиенты не плодили адаптеры под каждый сервис.

- **Envelope ответа:** все ответы оборачиваются в `{ "data": ..., "messages": [...], "code": 200 }`. Парный Go-`server/` использует тот же формат — frontend ожидает его одинаково.
- **Именование JSON-полей:** новые поля — **camelCase** (`createdAt`, `userId`, `organizationId`). Старые `snake_case`, если такие появятся при интеграции с Go-сервером, не переименовываем.
- **HTTP-коды ошибок:** `400` (валидация), `401` (нет/невалидный JWT), `403` (недостаточно прав), `404` (не найдено), `429` (rate-limit).
- **Аутентификация:** JWT, потребитель (`admin_panel_global`) хранит токен в cookie `savory_admin_token`. Доступ — только для роли `admin`.
- **Комментарии в коде и docstring-и тестов — на русском** (правило для бэкендов воркспейса).
- **Коммитить можно только в ветку `test`**, в `main` — через PR.

## Доменная область

Глобальная админка работает с теми же сущностями, что и Go-`server/`, но с админской точки зрения. Текущий набор доменов в `app/`:

| Домен | Префикс | Назначение |
|-------|---------|-----------|
| `health` | `/health` | Liveness/readiness — единственный публичный домен |
| `admin` | `/admin/auth` | Логин/`/me`/`/create-admin`. JWT (HS256), rate-limit на login per-email, bootstrap-учётка из `[admin]` config |
| `admin_log` | `/admin/logs` | Аудит-журнал админских действий (полный + `/me`), пагинация |
| `dashboard` | `/dashboard` | Сводные счётчики для главной фронта |
| `organizations` | `/organizations` | Список организаций с админом, ресторанами и флагом активной подписки |
| `restaurants` | `/restaurants` | Список/детали ресторанов с подпиской и остатком AI-лимита, фильтр `subscriptionActive` |
| `subscriptions` | `/admin/subscriptions` + `/subscriptions/extension-requests` | Список и ручное создание подписок; список/детали заявок на продление, approve/reject |
| `onboarding` | `/onboarding` | Заявки с лендинга — list/update, пайплайн `new → contacted → onboarding → installed` |
| `support` | `/support` | Тикеты поддержки — list, фильтр по статусу, update |
| `languages` | `/languages` | Справочник языков |
| `telegram` | `/telegram` | Подписчики Telegram-уведомлений (list, delete) |

Все endpoints, кроме `health`, требуют валидный JWT админа (`CurrentAdmin`). Soft-deleted записи скрыты в выдаче. Детальная модель Go-сервера и его endpoint'ы — `../server/docs/api/swagger.yaml` и `../CLAUDE.md` (раздел "Доменная модель").

## Стек

Python 3.12, FastAPI, SQLAlchemy 2.x (**asyncio-режим целиком**, не Sessions), asyncpg, Alembic (async-шаблон), pydantic-settings + TOML. Пакетный менеджер — **uv** (не pip/poetry). Линтер/форматтер — ruff. Тесты — pytest в `asyncio_mode = "auto"`.

## Конфигурация

Единственный источник правды — **`config/config.toml`**. Файл коммитится в репо с дефолтами для локального окружения; секреты/прод-значения переопределяются альтернативным файлом, путь к которому пробрасывается через переменную окружения `APP_CONFIG_FILE` (например, `APP_CONFIG_FILE=config/config.railway.toml`). По соглашению воркспейса (как у Go-`server/`) держим рядом `config.docker.toml` / `config.railway.toml`, если потребуются.

- Загрузка: `app/config.py` через `TomlConfigSettingsSource` (`pydantic-settings`). Переменные окружения **не** подмешиваются — единственный источник правды это TOML.
- Структура — вложенные секции:
  - `[app]` — `name`, `environment` (`local` / `staging` / `production` / `prod`), `api_v1_prefix`.
  - `[database]` — `url` (DSN с `postgresql+asyncpg://`), `echo`, `pool_size`, `max_overflow`.
  - `[cors]` — `allow_origins`, `allow_credentials`, `allow_methods`, `allow_headers`. **При `allow_credentials = true` нельзя указывать `"*"`** — браузер блокирует. По умолчанию открыт фронт `admin_panel_global` на `:3040`.
  - `[admin]` — JWT (`jwt_secret`, `jwt_algorithm`, `jwt_expires_minutes`), rate-limit логина (`login_max_attempts`, `login_window_minutes`, `login_lockout_minutes`) и bootstrap-учётка (`bootstrap_email`/`bootstrap_password`/`bootstrap_name`).
- Доступ из кода — `settings.app.name`, `settings.database.url`, `settings.cors.allow_origins`. Доменные настройки живут отдельно: `app/admin/config.py:admin_settings` читает свою секцию `[admin]` через подкласс `_AdminTomlSource`. Тот же паттерн используй для будущих доменных настроек — **никаких** `os.getenv`/`.env`.
- **Fail-fast в production:** `app/admin/config.py:validate_admin_settings_for(environment)` зовётся из `create_app()` и падает на старте, если `environment ∈ {production, prod}` и в `[admin]` остались дефолтные `jwt_secret` / `bootstrap_password`. Не глуши проверку — переопределяй секреты в `config.railway.toml` / `config.local.toml`.
- **Bootstrap-админ:** при старте `lifespan` в `app/main.py` зовёт `admin_service.seed_default_admin(db)` — идемпотентно создаёт первую учётку по `[admin].bootstrap_*`. Если БД недоступна (миграции не накатаны на свежем Railway), исключение логируется, но приложение поднимается.
- Локальный личный оверрайд (если очень нужен) — `config/*.local.toml`, он в `.gitignore`.

## Команды

```bash
uv sync                                           # установить deps из uv.lock
$EDITOR config/config.toml                        # настроить конфиг (DSN БД и т.п.)

uv run uvicorn app.main:app --reload              # dev-сервер (по умолчанию :8000)
uv run pytest                                     # все тесты
uv run pytest tests/test_health.py::test_health_endpoint_returns_ok_status -v   # один тест
uv run ruff check . && uv run ruff format .       # lint + format
uv run ruff check --fix .                         # автофикс

uv run alembic revision --autogenerate -m "msg"   # сгенерить миграцию из моделей
uv run alembic upgrade head                       # накатить
uv run alembic downgrade -1                       # откатить шаг

uv add <pkg>                                      # добавить зависимость
uv add --dev <pkg>                                # dev-зависимость
```

Не запускай команды напрямую (`pytest`, `alembic …`) без `uv run` — без активного venv они не увидят зависимости.

## Архитектура

Структура — **по домену, не по типу файла** (паттерн из скилла `fastapi-best-practices`). Глобальные модули в корне `app/`, каждый bounded context — отдельный пакет, общие хелперы — в `app/common/` и `app/lib/`:

```
app/
├── {domain}/           # admin/, admin_log/, dashboard/, languages/, onboarding/,
│   │                   # organizations/, restaurants/, subscriptions/, support/,
│   │                   # telegram/, health/
│   ├── router.py       # APIRouter + endpoints
│   ├── schemas.py      # Pydantic-модели IO (Response-модели — на CamelModel)
│   ├── service.py      # бизнес-логика
│   ├── dependencies.py # FastAPI-зависимости домена (опционально)
│   ├── config.py       # доменный BaseSettings (опционально, своя TOML-секция)
│   ├── constants.py    # перечисления, лимиты
│   ├── exceptions.py   # доменные исключения (наследники AppException)
│   ├── helpers.py      # внутренние утилиты домена (опционально)
│   └── (models.py)     # ORM — только у доменов с своими таблицами (admin, admin_log)
│
├── common/             # переиспользуемые хелперы между доменами
│   ├── database/
│   │   └── soft_delete.py   # soft_delete(instance), not_deleted(col) — единый паттерн
│   └── utils/
│       ├── pagination.py    # PaginationParams (limit/offset) + PaginatedResponse[T]
│       └── diff.py          # calculate_diff(orm, payload) — diff для PATCH + audit-лога
│
├── lib/                # generic-обёртки над библиотеками, не знают о домене
│   └── security/
│       ├── jwt.py            # encode_token/decode_token поверх PyJWT
│       └── passwords.py      # bcrypt hash/verify
│
├── config.py           # Settings (AppSettings, DatabaseSettings, CorsSettings) из config.toml
├── database.py         # async engine + SessionFactory + get_db + DbSession alias
├── models.py           # DeclarativeBase + MetaData с naming_convention для индексов
├── schemas.py          # Envelope[T], CamelModel (alias_generator → camelCase)
├── exceptions.py       # AppException + register_exception_handlers (всё → envelope)
└── main.py             # create_app() + lifespan + CORS + регистрация роутеров
config/
└── config.toml         # единственный источник правды для настроек (см. "Конфигурация")
alembic/
├── env.py              # импортирует ORM-модели каждого домена для autogenerate
└── versions/           # миграции (file_template: YYYY-MM-DD_slug.py)
```

Поток запроса:

```
HTTP → app/main.py (CORS → exception handlers → routers с prefix=/api/v1)
     → app/{domain}/router.py (CurrentAdmin gate + Annotated DbSession + PaginationParams)
     → app/{domain}/service.py (бизнес-логика, soft_delete, calculate_diff, audit log)
     → ORM-модели (app/{domain}/models.py или общая app/models.py)
     → app/database.py (async engine, SessionFactory, expire_on_commit=False)
     ← Envelope(data=…, code=…) обратно через FastAPI
```

`app/config.py` — глобальные `Settings`. Доменные настройки выносятся в `app/{domain}/config.py` со своим `BaseSettings`, который читает свою секцию того же TOML (см. `app/admin/config.py:_AdminTomlSource`). Никаких `os.getenv` и `.env`-файлов — только через `Settings`.

`app/database.py` создаёт **глобальный** `engine` и `SessionFactory` при импорте; `get_db()` — FastAPI-зависимость, отдаёт `AsyncSession` per-request. Engine закрывается в lifespan `app/main.py`. Удобный псевдоним — `DbSession = Annotated[AsyncSession, Depends(get_db)]` (есть и в `app/database.py`, и продублирован в `app/admin/dependencies.py`).

`app/models.py` экспортирует `Base` с предсконфигурированным `MetaData(naming_convention=…)` — все индексы/FK/PK получают предсказуемые имена. Все ORM-модели должны наследоваться от этого `Base`.

`app/schemas.py` — два кирпича, которые должны быть в каждом домене:
- `Envelope[T]` — все ответы возвращаются как `Envelope(data=…, code=…)`. Ошибки приходят в той же форме через `register_exception_handlers` (`StarletteHTTPException` + `RequestValidationError`).
- `CamelModel` — база для **Response**-схем (`alias_generator=to_camel`, `serialize_by_alias=True`, `from_attributes=True`, `populate_by_name=True`). Поля в коде — `snake_case`, в JSON — `camelCase`. Request-схемы могут наследоваться от `BaseModel` напрямую.

**Аутентификация и аудит:**
- `app/admin/dependencies.py:CurrentAdmin` — `Annotated[Admin, Depends(get_current_admin)]`. Подмешивается в любой защищённый endpoint (`_admin: CurrentAdmin`). Внутри — `HTTPBearer(auto_error=False)` + `decode_access_token` + проверка `is_active`. На любой проблеме — `InvalidToken` (401 в envelope).
- `app/admin/dependencies.py:ClientIp` — IP клиента, корректно вытаскивает первый адрес из `X-Forwarded-For` за Railway-прокси. Прокидывается в audit (`record_login_attempt`, `admin_log.service.log_action`).
- `app/admin/rate_limit.py:login_rate_limiter` — in-memory per-email лимит на `/admin/auth/login`.

**Пагинация:**
- `app/common/utils/pagination.py:PaginationParams` — `Annotated[PaginationModel, Depends(get_pagination_params)]`. Query — `limit` (default 10, max 100) + `offset` (default 0).
- `PaginatedResponse[T]` — единая форма страницы `{items, total, limit, offset}` для модулей с большими списками (subscriptions).
- В простых list-эндпоинтах возвращаем плоский `Envelope[list[Resp]]`, пагинация всё равно ограничивает выборку на стороне сервиса.

**Soft delete и diff:**
- `app/common/database/soft_delete.py` — `soft_delete(instance)` ставит `deleted_at = updated_at = now(UTC)` без commit, `not_deleted(col)` даёт WHERE-условие. Все list-эндпоинты обязаны фильтровать удалённые записи.
- `app/common/utils/diff.py:calculate_diff` — за один проход применяет `update_data` к ORM-объекту и возвращает `(before, after)` только по реально изменившимся полям. Используется в PATCH-эндпоинтах, чтобы повторный запрос с тем же телом не плодил пустые записи в `admin_logs`.

## Подводные камни

**Alembic autogenerate видит только импортированные модели.** `alembic/env.py` сейчас импортирует `app.admin.models` и `app.admin_log.models`. Каждый раз, когда появляется новый домен с persistent-моделями, дописывай туда строку `from app.<domain> import models as _<domain>_models  # noqa: F401`, иначе таблицы не попадут в миграцию.

**DSN для Alembic** берётся из `app.config.settings.database.url` (т.е. из `config/config.toml`, секция `[database]`), а не из `alembic.ini` (значение в ini — заглушка для offline-режима). Менять адрес БД — через `config/config.toml` (или альтернативный TOML, путь к которому проброшен в `APP_CONFIG_FILE`).

**Async везде.** Не миксуй sync-сессии SQLAlchemy и `psycopg2` — DSN-схема `postgresql+asyncpg://` требует асинхронного API. Внутри роутов: `await db.execute(...)`, `await db.commit()`.

**Стиль внедрения зависимостей — `Annotated[T, Depends(...)]`** (см. скилл). Образцы — `app/database.py:DbSession`, `app/admin/dependencies.py:CurrentAdmin`/`ClientIp`, `app/common/utils/pagination.py:PaginationParams`. Default-arg форма `db: AsyncSession = Depends(get_db)` — анти-паттерн.

**Не сочетай `response_model=Foo` и `-> Foo` одновременно** — модель сконструируется дважды. Полагайся на возвращаемый тип; `response_model` ставь, только если возвращаешь `dict`/ORM-row и нужна валидация.

**FastAPI `Depends()` в дефолтах аргументов — норма** для роутеров, когда нельзя обойтись `Annotated` (например, dependency без типа). Ruff-правило B008 отключено в `app/**/router.py` через `tool.ruff.lint.per-file-ignores`.

**Имена миграций** — date-prefixed slug (`2026-04-14_add_post_content_idx.py`), задаётся через `file_template` в `alembic.ini`. Текущие миграции — в `alembic/versions/2026-05-12_create_admin_table.py`, `..._create_admin_login_log.py`, `2026-05-15_create_admin_logs.py`.

**Все ответы — через `Envelope`.** Возвращай `Envelope(data=…, code=…)` руками, **не** `JSONResponse`/`dict`. Исключения обрабатывает `register_exception_handlers` — оно конвертирует `HTTPException` (включая доменные `AppException`-наследники) и `RequestValidationError` в ту же envelope-форму с массивом `messages`. Бросай доменные исключения, а не возвращай 500.

**Response-модели — на `CamelModel`,** Request — обычный `BaseModel`. Не дублируй `alias`-ы вручную — `to_camel` уже стоит как `alias_generator`. JSON-поля наружу всегда camelCase, query-параметры в роутерах задавай через `Query(alias="...")` (см. `restaurants/router.py:subscription_is`).

**JWT — только PyJWT,** через generic-обёртку `app/lib/security/jwt.py`. `python-jose` не использовать. Доменная обёртка — `app/admin/security.py` (подставляет `admin_settings.jwt_secret`/`jwt_algorithm`/`jwt_expires_minutes`).

**Пароли — bcrypt** через `app/lib/security/passwords.py`. Не использовать `passlib`.

**CORS и cookie-токены:** фронт `admin_panel_global` ходит с `withCredentials`. Поэтому в `[cors]` `allow_origins` — конкретные origin-ы (`http://localhost:3040` и т.п.), не `"*"`. Эта связка ломается беззвучно — браузер тихо дропает ответ.

**Pytest сконфигурирован в auto-режиме** (`asyncio_mode = "auto"`), но `@pytest.mark.asyncio` на тестах оставляй явно — так понятнее намерение. HTTP-клиент — `httpx.AsyncClient` + `ASGITransport`, фикстура `client` в `tests/conftest.py`. Свопать зависимости — через `app.dependency_overrides[dep] = fake`, не monkeypatch.

**Тесты сгруппированы по доменам** в `tests/<domain>/` (см. `tests/admin/`, `tests/subscriptions/`, …) — структура зеркалит `app/`. Общая конфтест-фикстура `client` подменяет `get_db` на in-memory SQLite через `aiosqlite`.

## Соглашения воркспейса (важное из `../CLAUDE.md`)

- Комментарии в коде и docstring-и тестов — **на русском** (правило для бэкендов воркспейса).
- Новые JSON-поля в API — **camelCase** (`createdAt`, `userId`). Старые `snake_case` не переименовываем.
- Все ответы оборачиваются в envelope `{data, messages, code}` (см. парный Go-`server/` в воркспейсе). Если этот сервис будет потреблять/отдавать данные тем же фронтам — придерживайся той же формы.
- Коммитить можно **только в ветку `test`**, в `main` — через PR.
