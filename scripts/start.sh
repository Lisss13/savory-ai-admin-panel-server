#!/usr/bin/env bash
# Entrypoint для Railway: рендерит config, накатывает миграции, запускает uvicorn.
set -euo pipefail

# Путь к отрендеренному TOML — тот же, что в render_railway_config.py.
export APP_CONFIG_FILE="${APP_CONFIG_FILE:-/tmp/config.railway.toml}"

# 1. Конфиг из Railway env → TOML, который ждёт app/config.py.
python scripts/render_railway_config.py

# 2. Миграции до запуска веб-процесса.
alembic upgrade head

# 3. Сам uvicorn. Railway пробрасывает порт через $PORT.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
