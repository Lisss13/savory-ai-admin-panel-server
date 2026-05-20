# Деплой на Railway

Этот сервис разворачивается отдельным сервисом в Railway-проекте Savory AI. Ниже — что нужно сделать руками после того, как код запушен в репозиторий.

## Что уже подготовлено в репо

- `railway.toml` — builder = Nixpacks, healthcheck `/api/v1/health`, restart on failure.
- `scripts/start.sh` — entrypoint: рендерит конфиг → накатывает миграции → запускает uvicorn на `$PORT`.
- `scripts/render_railway_config.py` — собирает `config/config.railway.toml` из переменных окружения. Приложение продолжает читать только TOML (правило воркспейса), bootstrap-скрипт превращает Railway-ENV в этот TOML.
- Nixpacks автоматически подхватит `pyproject.toml` + `uv.lock` и поставит зависимости через uv (Python 3.12 из `.python-version`).

## Пошагово — что сделать в Railway

### 1. Создать сервисы

В существующем Railway-проекте Savory AI (тот же, где живёт Go-`server/`) добавь:

1. **Postgres** — `+ New → Database → Add PostgreSQL`. Railway сам создаст переменную `DATABASE_URL`.
2. **Сервис из этого репо** — `+ New → GitHub Repo → admin_panel_global_server` (ветка `main` или `test` — что катите в прод).

### 2. Подключить базу к сервису

В сервисе admin_panel_global_server открой **Variables** и через **Add Reference** забери `DATABASE_URL` от Postgres (`${{Postgres.DATABASE_URL}}`). Это даст сервису синхронный DSN — startup-скрипт сам приведёт его к `postgresql+asyncpg://...`.

### 3. Задать переменные окружения

Обязательные (без них сервис не стартует):

| Переменная | Что |
|---|---|
| `DATABASE_URL` | ссылка на Postgres (см. шаг 2). |
| `ADMIN_JWT_SECRET` | случайная строка ≥ 32 байт. Сгенерь локально: `openssl rand -hex 32`. |
| `ADMIN_BOOTSTRAP_EMAIL` | email первой админ-учётки (создастся при первом старте). |
| `ADMIN_BOOTSTRAP_PASSWORD` | пароль той же учётки. После первого логина — смени, либо удали запись в БД. |
| `CORS_ALLOW_ORIGINS` | CSV-список разрешённых origin'ов, **без `"*"`** (т.к. `allow_credentials=true`). Минимум — URL фронта `admin_panel_global`, например `https://admin.savory.ai,https://admin-panel-global-production.up.railway.app`. |

Опциональные (есть дефолты в `scripts/render_railway_config.py`):

| Переменная | Дефолт | Назначение |
|---|---|---|
| `APP_ENVIRONMENT` | `production` | Под `production`/`prod` сработает fail-fast проверка из `app/admin/config.py` — поднимет ошибку, если оставлены дефолтные секреты. |
| `APP_NAME` | `admin-panel-global-server` | |
| `API_V1_PREFIX` | `/api/v1` | Влияет на healthcheck (если меняешь — поправь и `railway.toml`). |
| `DB_ECHO` | `false` | SQL-логирование SQLAlchemy. |
| `DB_POOL_SIZE` | `5` | |
| `DB_MAX_OVERFLOW` | `10` | |
| `ADMIN_JWT_ALGORITHM` | `HS256` | |
| `ADMIN_JWT_EXPIRES_MINUTES` | `60` | |
| `ADMIN_LOGIN_MAX_ATTEMPTS` | `5` | per-email rate-limit. |
| `ADMIN_LOGIN_WINDOW_MINUTES` | `15` | |
| `ADMIN_LOGIN_LOCKOUT_MINUTES` | `15` | |
| `ADMIN_BOOTSTRAP_NAME` | `Root Admin` | |
| `CORS_ALLOW_CREDENTIALS` | `true` | |
| `CORS_ALLOW_METHODS` | `*` | CSV. |
| `CORS_ALLOW_HEADERS` | `*` | CSV. |

### 4. Открыть публичный домен

В сервисе → **Settings → Networking → Generate Domain**. Railway сгенерит `admin-panel-global-server-production.up.railway.app` (или дай свой через **Custom Domain**). Сервис слушает порт из `$PORT`, Railway проксирует на `:443`.

После того как домен поднимется — добавь его в `CORS_ALLOW_ORIGINS` фронта `admin_panel_global` (`NEXT_PUBLIC_API_URL`) и в свой собственный `CORS_ALLOW_ORIGINS` (URL фронта).

### 5. Задеплоить

Railway автодеплоит по push в выбранную ветку. На первом деплое в логах должно быть:

```
[render_railway_config] wrote /tmp/config.railway.toml
INFO  [alembic.runtime.migration] Running upgrade ...
INFO:     Uvicorn running on http://0.0.0.0:<port>
Bootstrap admin ensured: <email>
```

Затем healthcheck `/api/v1/health` должен ответить `200`.

### 6. Проверить руками

```bash
# Healthcheck
curl https://<your-domain>/api/v1/health

# Логин bootstrap-учёткой
curl -X POST https://<your-domain>/api/v1/admin/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<ADMIN_BOOTSTRAP_EMAIL>","password":"<ADMIN_BOOTSTRAP_PASSWORD>"}'
```

В ответе должен прийти `{"data":{"accessToken": "..."}, ...}`.

### 7. После деплоя

- **Смени пароль root-админа** (или создай нового через `/admin/auth/create-admin` и удали bootstrap).
- **Подключи фронт** `admin_panel_global` — задеплой его отдельным Railway-сервисом и поставь его `NEXT_PUBLIC_API_URL = https://<api-domain>`.
- **CORS:** убедись, что URL фронта вошёл в `CORS_ALLOW_ORIGINS` (без trailing slash).
- **Production URLs** допиши в `../CLAUDE.md` (раздел "Production URLs на Railway") и в `CLAUDE.md` этого репо.

## Локально проверить, что entrypoint работает

```bash
DATABASE_URL=postgresql://savory_admin:savory_password@localhost:5432/savory_db \
ADMIN_JWT_SECRET="$(openssl rand -hex 32)" \
ADMIN_BOOTSTRAP_EMAIL=admin@local.test \
ADMIN_BOOTSTRAP_PASSWORD=local-only \
CORS_ALLOW_ORIGINS="http://localhost:3040" \
APP_CONFIG_FILE=/tmp/config.railway.toml \
python scripts/render_railway_config.py && cat /tmp/config.railway.toml
```

— должен напечатать корректный TOML без пустых обязательных полей.

## Подводные камни

- **`CORS_ALLOW_ORIGINS = "*"` несовместим с cookie-аутентификацией.** Браузер тихо дропнет ответ, фронт получит CORS-ошибку. Всегда конкретные origin'ы.
- **`DATABASE_URL` от Railway-Postgres** — формата `postgresql://...`. Конвертация в `postgresql+asyncpg://` — в `render_railway_config.py:normalize_dsn`.
- **Bootstrap-админ создаётся идемпотентно** в `lifespan` (`app/main.py` → `admin_service.seed_default_admin`). Если БД упала на старте — приложение поднимется, но без админа; повторный рестарт создаст.
- **Production fail-fast** — если `APP_ENVIRONMENT=production` и `ADMIN_JWT_SECRET` либо `ADMIN_BOOTSTRAP_PASSWORD` остались дефолтными из `app/admin/config.py`, сервис упадёт при старте. Это не баг.
- **Миграции** накатываются на каждый деплой (`alembic upgrade head` в `start.sh`). Откат — только руками: `railway run alembic downgrade -1`.
- **Nixpacks vs Docker** — сейчас используется Nixpacks. Если понадобится свой Dockerfile, поменяй `[build].builder` в `railway.toml` на `DOCKERFILE`.
