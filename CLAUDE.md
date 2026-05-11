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

Глобальная админка работает с теми же сущностями, что и Go-`server/`, но с админской точки зрения. Ожидаемые ресурсы (по мере появления):

- Organizations / Users — управление, смена роли/статуса, аудит.
- Subscriptions + ExtensionRequests — одобрение продлений.
- OnboardingRequests — лиды с лендинга, pipeline `new → contacted → onboarding → installed`.
- SupportTickets — обработка обращений.
- AI Analytics — сводки по AI-запросам (источник — `AIRequestLog` на стороне `server/`, если будет интеграция).
- Dishes (модерация) — обзор/блокировка контента.
- AdminLogs — журнал админских действий.

Детальная модель и существующие endpoint'ы Go-сервера — `../server/docs/api/swagger.yaml` и `../CLAUDE.md` (раздел "Доменная модель").

## Стек

Python 3.12, FastAPI, SQLAlchemy 2.x (**asyncio-режим целиком**, не Sessions), asyncpg, Alembic (async-шаблон), pydantic-settings + TOML. Пакетный менеджер — **uv** (не pip/poetry). Линтер/форматтер — ruff. Тесты — pytest в `asyncio_mode = "auto"`.

## Конфигурация

Единственный источник правды — **`config/config.toml`**. Файл коммитится в репо с дефолтами для локального окружения; секреты/прод-значения переопределяются альтернативным файлом, путь к которому пробрасывается через переменную окружения `APP_CONFIG_FILE` (например, `APP_CONFIG_FILE=config/config.railway.toml`). По соглашению воркспейса (как у Go-`server/`) держим рядом `config.docker.toml` / `config.railway.toml`, если потребуются.

- Загрузка: `app/config.py` через `TomlConfigSettingsSource` (`pydantic-settings`).
- Структура — вложенные секции: `[app]` (name/environment/api_v1_prefix), `[database]` (url/echo/pool_size/max_overflow). Доступ из кода — `settings.app.name`, `settings.database.url` и т.п.
- Доменные конфиги по-прежнему живут в `app/{domain}/config.py` как свой `BaseSettings` (например, JWT-секрет — `app/auth/config.py`), но **тоже** читают TOML, а не `.env`. Никаких `os.getenv` и `.env`-файлов.
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

Структура — **по домену, не по типу файла** (паттерн из скилла `fastapi-best-practices`). Глобальные модули в корне `app/`, каждый bounded context — отдельный пакет:

```
app/
├── {domain}/           # health/, далее auth/, users/, organizations/, …
│   ├── router.py       # APIRouter + endpoints
│   ├── schemas.py      # Pydantic-модели IO
│   ├── models.py       # SQLAlchemy ORM (наследник app.models.Base)
│   ├── service.py      # бизнес-логика (создаётся по мере появления)
│   ├── dependencies.py # FastAPI-зависимости домена
│   ├── config.py       # доменный BaseSettings (своя TOML-секция)
│   ├── constants.py
│   └── exceptions.py
├── config.py           # загрузка config/config.toml через TomlConfigSettingsSource
├── database.py         # async engine + SessionFactory + get_db
├── models.py           # DeclarativeBase + MetaData с naming_convention для индексов
├── exceptions.py       # AppException (база HTTPException)
└── main.py             # create_app() + lifespan; openapi_url отключается вне local/staging
config/
└── config.toml         # единственный источник правды для настроек (см. раздел "Конфигурация")
```

Поток запроса:

```
HTTP → app/main.py (lifespan, prefix)
     → app/{domain}/router.py (Annotated[AsyncSession, Depends(get_db)])
     → app/{domain}/schemas.py (Pydantic v2 IO)
     → app/{domain}/service.py → app/{domain}/models.py (ORM)
     → app/database.py (async engine, SessionFactory)
```

`app/config.py` — глобальные `Settings`. Доменные настройки (JWT, внешние API, и т.п.) выносятся в `app/{domain}/config.py` со своим `BaseSettings`, который читает ту же TOML-секцию. Никаких `os.getenv` и `.env`-файлов — только через `Settings`.

`app/database.py` создаёт **глобальный** `engine` и `SessionFactory` при импорте; `get_db()` — FastAPI-зависимость, отдаёт `AsyncSession` per-request. Engine закрывается в lifespan `app/main.py`.

`app/models.py` экспортирует `Base` с предсконфигурированным `MetaData(naming_convention=…)` — все индексы/FK/PK получают предсказуемые имена. Все ORM-модели должны наследоваться от этого `Base`.

## Подводные камни

**Alembic autogenerate видит только импортированные модели.** `alembic/env.py` явно импортирует `app.health.models`. Каждый раз, когда появляется новый домен с моделями, дописывай его импорт туда (или централизуй через общий `app/models_registry.py`), иначе таблицы не попадут в миграцию.

**DSN для Alembic** берётся из `app.config.settings.database.url` (т.е. из `config/config.toml`, секция `[database]`), а не из `alembic.ini` (значение в ini — заглушка для offline-режима). Менять адрес БД — через `config/config.toml` (или альтернативный TOML, путь к которому проброшен в `APP_CONFIG_FILE`).

**Async везде.** Не миксуй sync-сессии SQLAlchemy и `psycopg2` — DSN-схема `postgresql+asyncpg://` требует асинхронного API. Внутри роутов: `await db.execute(...)`, `await db.commit()`.

**Стиль внедрения зависимостей — `Annotated[T, Depends(...)]`** (см. скилл). Образец — `app/health/router.py:DbSession`. Default-arg форма `db: AsyncSession = Depends(get_db)` — анти-паттерн.

**Не сочетай `response_model=Foo` и `-> Foo` одновременно** — модель сконструируется дважды. Полагайся на возвращаемый тип; `response_model` ставь, только если возвращаешь `dict`/ORM-row и нужна валидация.

**FastAPI `Depends()` в дефолтах аргументов — норма** для роутеров, когда нельзя обойтись `Annotated` (например, dependency без типа). Ruff-правило B008 отключено в `app/**/router.py` через `tool.ruff.lint.per-file-ignores`.

**Имена миграций** — date-prefixed slug (`2026-04-14_add_post_content_idx.py`), задаётся через `file_template` в `alembic.ini`.

**Pytest сконфигурирован в auto-режиме** (`asyncio_mode = "auto"`), но `@pytest.mark.asyncio` на тестах оставляй явно — так понятнее намерение. HTTP-клиент — `httpx.AsyncClient` + `ASGITransport`, фикстура `client` в `tests/conftest.py`. Свопать зависимости — через `app.dependency_overrides[dep] = fake`, не monkeypatch.

## Соглашения воркспейса (важное из `../CLAUDE.md`)

- Комментарии в коде и docstring-и тестов — **на русском** (правило для бэкендов воркспейса).
- Новые JSON-поля в API — **camelCase** (`createdAt`, `userId`). Старые `snake_case` не переименовываем.
- Все ответы оборачиваются в envelope `{data, messages, code}` (см. парный Go-`server/` в воркспейсе). Если этот сервис будет потреблять/отдавать данные тем же фронтам — придерживайся той же формы.
- Коммитить можно **только в ветку `test`**, в `main` — через PR.
