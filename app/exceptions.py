"""Глобальные исключения и обработчики ошибок.

Все ответы (включая ошибки) обёрнуты в envelope `{data, messages, code}` —
единый контракт API для всех бэкендов Savory (см. ../CLAUDE.md, "Контракт API").

Доменные исключения — в `<domain>/exceptions.py`.
"""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppException(HTTPException):
    """Базовое HTTP-исключение приложения."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(status_code=self.status_code, detail=detail or self.detail)


def _envelope(status_code: int, messages: list[str]) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "messages": messages, "code": status_code},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Приводит все ошибки к форме envelope `{data, messages, code}`."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # detail может быть произвольным — приводим к строке для messages.
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _envelope(exc.status_code, [detail])

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Формируем "поле: причина" для каждого нарушения.
        messages = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        ]
        return _envelope(status.HTTP_400_BAD_REQUEST, messages)
