"""Unit-тесты чистых helper-функций (`app.ai_topup.helpers`)."""

from datetime import UTC, datetime

import pytest

from app.ai_topup.exceptions import InvalidStringCharacters
from app.ai_topup.helpers import next_month_start, validate_no_null_bytes

# ---------- next_month_start ----------


def test_next_month_start_mid_month():
    """Середина месяца → 1-е число следующего месяца, 00:00 UTC."""
    now = datetime(2026, 6, 25, 14, 30, 5, tzinfo=UTC)
    assert next_month_start(now) == datetime(2026, 7, 1, tzinfo=UTC)


def test_next_month_start_december_rolls_to_january():
    """Декабрь → январь следующего года (граница года)."""
    now = datetime(2026, 12, 15, 23, 59, 59, tzinfo=UTC)
    assert next_month_start(now) == datetime(2027, 1, 1, tzinfo=UTC)


def test_next_month_start_first_of_month():
    """1-е число → 1-е число следующего месяца (не текущего)."""
    now = datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)
    assert next_month_start(now) == datetime(2026, 3, 1, tzinfo=UTC)


def test_next_month_start_result_is_utc_aware():
    now = datetime(2026, 6, 25, tzinfo=UTC)
    assert next_month_start(now).tzinfo == UTC


# ---------- validate_no_null_bytes ----------


def test_validate_no_null_bytes_passes_for_clean_string():
    validate_no_null_bytes("normal text")
    validate_no_null_bytes(None)
    validate_no_null_bytes("")


def test_validate_no_null_bytes_rejects_string_with_nul():
    with pytest.raises(InvalidStringCharacters):
        validate_no_null_bytes("bad\x00thing")
