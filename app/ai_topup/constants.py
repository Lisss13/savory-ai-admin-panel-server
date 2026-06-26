"""Константы и enum's модуля ai_topup."""

from enum import StrEnum


class TopUpRequestStatus(StrEnum):
    """Статус заявки на докупку AI-запросов.

    Жизненный цикл: `pending → (approved | rejected)`. После апрува заявка
    становится `approved` и порождает запись `ai_request_quotas`; реджект —
    `rejected` без побочных эффектов.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
