"""Доменные исключения модуля онбординг-заявок."""

from typing import final

from fastapi import status

from app.exceptions import AppException


@final
class OnboardingRequestNotFound(AppException):
    """Заявка с таким id не найдена (или soft-deleted)."""

    status_code = status.HTTP_404_NOT_FOUND
    detail = "onboarding request not found"
