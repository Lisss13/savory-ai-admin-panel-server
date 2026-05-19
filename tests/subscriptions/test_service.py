"""Unit-тесты чистых helper-функций (`app.subscriptions.helpers`).

HTTP не задействован — тестируем pure functions и edge cases, которые сложно
покрыть только через router-тесты.
"""

from datetime import UTC, datetime

import pytest

from app.subscriptions.exceptions import InvalidEndDateOverride, InvalidStringCharacters
from app.subscriptions.helpers import (
    add_months,
    compute_new_end_date,
    ensure_aware_utc,
    resolve_limit,
    validate_end_date_override,
    validate_no_null_bytes,
)

# ---------- add_months ----------


def test_add_months_jan_31_plus_1_clamps_to_feb_28_or_29():
    """31 янв + 1 мес → 28/29 фев (паритет с Go-`time.AddDate`)."""
    dt = datetime(2025, 1, 31, 12, 0, tzinfo=UTC)
    result = add_months(dt, 1)
    assert result == datetime(2025, 2, 28, 12, 0, tzinfo=UTC)


def test_add_months_jan_31_plus_1_leap_year():
    """В високосный год 31 янв + 1 мес → 29 фев."""
    dt = datetime(2024, 1, 31, tzinfo=UTC)
    assert add_months(dt, 1) == datetime(2024, 2, 29, tzinfo=UTC)


def test_add_months_may_31_plus_1_clamps_to_jun_30():
    """31 мая + 1 мес → 30 июня (в июне 30 дней)."""
    dt = datetime(2025, 5, 31, tzinfo=UTC)
    assert add_months(dt, 1) == datetime(2025, 6, 30, tzinfo=UTC)


def test_add_months_12_months_advances_year():
    """+12 мес = тот же день через год."""
    dt = datetime(2025, 3, 15, 9, 30, tzinfo=UTC)
    assert add_months(dt, 12) == datetime(2026, 3, 15, 9, 30, tzinfo=UTC)


def test_add_months_preserves_tzinfo_for_aware_datetime():
    dt = datetime(2025, 7, 10, tzinfo=UTC)
    assert add_months(dt, 3).tzinfo == UTC


def test_add_months_zero_returns_same_datetime():
    dt = datetime(2025, 1, 31, tzinfo=UTC)
    assert add_months(dt, 0) == dt


# ---------- resolve_limit ----------


def test_resolve_limit_prefers_override():
    """Override > 0 — высший приоритет."""
    assert resolve_limit(override=5, requested=3, fallback=1) == 5


def test_resolve_limit_falls_to_requested_when_no_override():
    """Override None → берётся requested > 0."""
    assert resolve_limit(override=None, requested=4, fallback=1) == 4


def test_resolve_limit_falls_to_fallback_when_both_empty():
    """Нет override, requested = 0/None → fallback."""
    assert resolve_limit(override=None, requested=0, fallback=7) == 7
    assert resolve_limit(override=None, requested=None, fallback=2) == 2


# ---------- validate_end_date_override ----------


def test_validate_end_date_override_accepts_future_after_start():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    future = datetime(2026, 6, 1, tzinfo=UTC)
    validate_end_date_override(future, start, now)


def test_validate_end_date_override_rejects_before_now():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    past = datetime(2025, 6, 1, tzinfo=UTC)
    with pytest.raises(InvalidEndDateOverride):
        validate_end_date_override(past, start, now)


def test_validate_end_date_override_rejects_before_start():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    override = datetime(2026, 3, 1, tzinfo=UTC)
    with pytest.raises(InvalidEndDateOverride):
        validate_end_date_override(override, start, now)


def test_validate_end_date_override_none_is_noop():
    validate_end_date_override(None, datetime.now(UTC), datetime.now(UTC))


# ---------- validate_no_null_bytes ----------


def test_validate_no_null_bytes_passes_for_clean_string():
    validate_no_null_bytes("normal text")
    validate_no_null_bytes(None)
    validate_no_null_bytes("")


def test_validate_no_null_bytes_rejects_string_with_nul():
    with pytest.raises(InvalidStringCharacters):
        validate_no_null_bytes("bad\x00thing")


# ---------- ensure_aware_utc ----------


def test_ensure_aware_utc_keeps_aware_datetime():
    dt = datetime(2025, 1, 1, tzinfo=UTC)
    assert ensure_aware_utc(dt) == dt


def test_ensure_aware_utc_assigns_utc_to_naive():
    naive = datetime(2025, 1, 1, 12, 0)
    assert ensure_aware_utc(naive).tzinfo == UTC


# ---------- compute_new_end_date ----------


def test_compute_new_end_date_uses_override_when_provided():
    """Override побеждает — base/period_months игнорируются."""
    override = datetime(2030, 5, 1, tzinfo=UTC)
    base = datetime(2025, 1, 1, tzinfo=UTC)
    assert compute_new_end_date(override=override, base=base, period_months=12) == override


def test_compute_new_end_date_no_override_uses_base_plus_months():
    """Без override → `add_months(base, period_months)`."""
    base = datetime(2025, 1, 31, tzinfo=UTC)
    result = compute_new_end_date(override=None, base=base, period_months=1)
    assert result == datetime(2025, 2, 28, tzinfo=UTC)
