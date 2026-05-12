"""Константы языкового модуля."""

# Код языка по умолчанию (ISO 639-1). Защищён от удаления — на него опираются
# остальные сервисы воркспейса (см. Restaurants.default_language).
DEFAULT_LANGUAGE_CODE: str = "en"

# Длины полей. Согласованы с моделью БД (Text-колонки без ограничений), но в API
# мы валидируем явно, чтобы не принимать мусор.
LANGUAGE_CODE_LENGTH: int = 2
MAX_NAME_LENGTH: int = 256
MAX_DESCRIPTION_LENGTH: int = 256
