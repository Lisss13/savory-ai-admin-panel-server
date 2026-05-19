"""Тесты для `app/common/utils/percentage.py`.

Функция простая, но используется в финансовых/лимитных полях API
(см. `percentageOfUsedAiReq` в `/restaurants`), поэтому фиксируем
контракт явно: значение, граничные случаи и округление.
"""

import pytest

from app.restaurants.utils import percentage


class TestPercentage:
    def test_basic_case(self):
        """50 из 100 → 50.0%."""
        assert percentage(50, 100) == 50.0

    def test_zero_value(self):
        """0 / total → 0.0% (используется для свежих ресторанов без AI-логов)."""
        assert percentage(0, 25_000) == 0.0

    def test_full_usage(self):
        """value == total → 100.0%."""
        assert percentage(25_000, 25_000) == 100.0

    def test_total_zero_returns_zero(self):
        """Деление на 0 не должно валить процесс — возвращаем 0.0 (контракт)."""
        assert percentage(10, 0) == 0.0

    def test_total_zero_with_zero_value(self):
        """И 0/0 тоже не падает — это `total=0` ветка, value игнорируется."""
        assert percentage(0, 0) == 0.0

    def test_rounds_to_two_decimals_by_default(self):
        """`decimals=2` по умолчанию — нужно для стабильного UI и JSON."""
        # 1/3 ≈ 33.3333... → 33.33
        assert percentage(1, 3) == 33.33

    def test_respects_custom_decimals(self):
        """`decimals=4` — округление до 4 знаков."""
        assert percentage(1, 3, decimals=4) == 33.3333

    def test_decimals_zero_returns_integer_float(self):
        """`decimals=0` — округление до целого, но тип остаётся float."""
        result = percentage(1, 3, decimals=0)
        assert result == 33.0
        assert isinstance(result, float)

    def test_value_greater_than_total_exceeds_100(self):
        """Перерасход (value > total) — процент > 100, а не клампится.

        Применимо к AI-лимиту: если рестораны как-то превысили 25000 запросов
        (race на проверке), считать всё равно нужно — это сигнал админу.
        """
        assert percentage(50_000, 25_000) == 200.0

    def test_negative_value(self):
        """Отрицательное значение — отрицательный процент (не падает).

        Сейчас в /restaurants `ai_requests_left` может уйти в минус при
        перерасходе, и функция не должна на это ругаться.
        """
        assert percentage(-100, 1_000) == -10.0

    def test_returns_float_for_integer_inputs(self):
        """Тип возвращаемого значения — всегда `float`, даже если входы целые."""
        result = percentage(10, 100)
        assert isinstance(result, float)

    @pytest.mark.parametrize(
        ("value", "total", "expected"),
        [
            (1, 25_000, 0.0),  # округление вниз → 0.0
            (125, 25_000, 0.5),  # ровно 0.5%
            (250, 25_000, 1.0),  # ровно 1% (фикс баг-кейса из /restaurants)
            (12_500, 25_000, 50.0),
            (25_000, 25_000, 100.0),
        ],
    )
    def test_ai_limit_real_world_values(self, value: int, total: int, expected: float) -> None:
        """Реальные значения из контекста AI-лимита (`MONTHLY_AI_REQUEST_LIMIT=25000`).

        Фиксируем именно эти точки — они проверяются и в HTTP-тестах
        `/restaurants`, и здесь, чтобы при изменении формулы регрессия
        ловилась в нескольких слоях сразу.
        """
        assert percentage(value, total) == expected
