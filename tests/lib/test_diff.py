"""Тесты для `app/lib/logs/diff.py`.

Хелпер работает только с атрибутами объекта (`getattr`/`setattr`), поэтому
БД и сессия не нужны — достаточно сконструировать ORM-инстанс в памяти и
проверить инвариант: в diff попадают только реально изменённые поля, а
`setattr` применяется к самому объекту.
"""

from app.common.utils.diff import calculate_diff, calculate_diff_dict, is_diff
from app.models import OnboardingRequests


def _make_request(**overrides) -> OnboardingRequests:
    """Минимальный onboarding-инстанс с дефолтами; не персистится."""
    defaults = {
        "id": 1,
        "name": "Acme",
        "phone": "+971500000000",
        "email": "owner@acme.ae",
        "status": "new",
    }
    defaults.update(overrides)
    return OnboardingRequests(**defaults)


class TestCalculateDiff:
    """Логика `calculate_diff`: считает diff, мутирует объект, фильтрует совпадения."""

    def test_returns_only_changed_fields(self):
        """В before/after попадает только поле, у которого новое значение отличается."""
        req = _make_request(status="new", name="Acme")

        before, after = calculate_diff(req, {"status": "contacted", "name": "Acme"})

        assert before == {"status": "new"}
        assert after == {"status": "contacted"}

    def test_applies_changes_to_instance(self):
        """`calculate_diff` мутирует объект — после вызова атрибут обновлён."""
        req = _make_request(status="new")

        calculate_diff(req, {"status": "contacted"})

        assert req.status == "contacted"

    def test_returns_empty_dicts_when_no_changes(self):
        """Если значения совпадают — diff пустой, ничего не пишем в audit-лог."""
        req = _make_request(status="new", name="Acme")

        before, after = calculate_diff(req, {"status": "new", "name": "Acme"})

        assert before == {}
        assert after == {}

    def test_does_not_mutate_when_no_changes(self):
        """Совпадающие значения не вызывают setattr — объект остаётся прежним."""
        req = _make_request(status="new")

        calculate_diff(req, {"status": "new"})

        assert req.status == "new"

    def test_empty_update_data(self):
        """Пустой dict → пустой diff, никаких ошибок."""
        req = _make_request()

        before, after = calculate_diff(req, {})

        assert before == {}
        assert after == {}

    def test_detects_none_to_value_transition(self):
        """Поле было None, стало значением — попадает в diff."""
        req = _make_request()
        req.created_at = None

        before, after = calculate_diff(req, {"created_at": "2026-05-15"})

        assert before == {"created_at": None}
        assert after == {"created_at": "2026-05-15"}
        assert req.created_at == "2026-05-15"

    def test_detects_value_to_none_transition(self):
        """Поле было значением, обнулили — diff фиксирует переход."""
        req = _make_request(status="contacted")

        before, after = calculate_diff(req, {"status": None})

        assert before == {"status": "contacted"}
        assert after == {"status": None}
        assert req.status is None

    def test_multiple_fields_changed(self):
        """Все изменённые поля попадают в diff и применяются к объекту."""
        req = _make_request(status="new", name="Acme", phone="+1")

        before, after = calculate_diff(
            req,
            {"status": "contacted", "name": "Acme Corp", "phone": "+1"},
        )

        assert before == {"status": "new", "name": "Acme"}
        assert after == {"status": "contacted", "name": "Acme Corp"}
        assert req.status == "contacted"
        assert req.name == "Acme Corp"
        assert req.phone == "+1"

    def test_before_after_have_same_keys(self):
        """`before` и `after` всегда содержат один и тот же набор ключей."""
        req = _make_request(status="new", name="Acme")

        before, after = calculate_diff(req, {"status": "contacted", "name": "Other"})

        assert set(before.keys()) == set(after.keys())


class TestIsDiff:
    """`is_diff` — короткая проверка, есть ли что логировать."""

    def test_true_when_both_non_empty(self):
        assert is_diff({"status": "new"}, {"status": "contacted"}) is True

    def test_false_when_both_empty(self):
        """Главный кейс: пропускаем log_action, когда реальных изменений нет."""
        assert is_diff({}, {}) is False

    def test_true_when_only_before_non_empty(self):
        """Защита от ассимметрии — на практике такого не бывает, но проверка через `or`."""
        assert is_diff({"x": 1}, {}) is True

    def test_true_when_only_after_non_empty(self):
        assert is_diff({}, {"x": 1}) is True


class TestCalculateDiffDict:
    """`calculate_diff_dict` — обёртка, возвращающая `{before, after}`."""

    def test_returns_dict_with_before_and_after_keys(self):
        req = _make_request(status="new")

        result = calculate_diff_dict(req, {"status": "contacted"})

        assert result == {
            "before": {"status": "new"},
            "after": {"status": "contacted"},
        }

    def test_applies_changes_to_instance(self):
        """Обёртка делегирует в `calculate_diff` — мутация объекта сохраняется."""
        req = _make_request(status="new")

        calculate_diff_dict(req, {"status": "contacted"})

        assert req.status == "contacted"

    def test_empty_when_no_changes(self):
        """Нет изменений → обе секции пустые; вызывающий код пропустит log_action."""
        req = _make_request(status="new")

        result = calculate_diff_dict(req, {"status": "new"})

        assert result == {"before": {}, "after": {}}
