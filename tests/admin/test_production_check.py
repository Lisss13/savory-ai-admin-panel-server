"""Тест prod-валидатора: в проде запрещены дефолтные секреты."""

import pytest

from app.admin.config import (
    DEFAULT_BOOTSTRAP_PASSWORD,
    DEFAULT_JWT_SECRET,
    admin_settings,
    validate_admin_settings_for,
)


def test_validate_passes_for_local_environment():
    """В local-окружении дефолты допустимы — иначе локальная разработка ломается."""
    validate_admin_settings_for("local")


def test_validate_fails_for_production_with_default_secret(monkeypatch: pytest.MonkeyPatch):
    """В production дефолтный jwt_secret → `RuntimeError` на старте приложения."""
    monkeypatch.setattr(admin_settings, "jwt_secret", DEFAULT_JWT_SECRET)
    monkeypatch.setattr(admin_settings, "bootstrap_password", "strong-password-XyZ-123")

    with pytest.raises(RuntimeError, match="jwt_secret"):
        validate_admin_settings_for("production")


def test_validate_fails_for_production_with_default_password(monkeypatch: pytest.MonkeyPatch):
    """В production дефолтный bootstrap_password → `RuntimeError`."""
    monkeypatch.setattr(admin_settings, "jwt_secret", "kustom-secret-32-bytes-or-more!")
    monkeypatch.setattr(admin_settings, "bootstrap_password", DEFAULT_BOOTSTRAP_PASSWORD)

    with pytest.raises(RuntimeError, match="bootstrap_password"):
        validate_admin_settings_for("production")


def test_validate_passes_for_production_with_overridden_values(monkeypatch: pytest.MonkeyPatch):
    """Когда оба секрета переопределены — валидатор молчит."""
    monkeypatch.setattr(admin_settings, "jwt_secret", "kustom-secret-32-bytes-or-more!")
    monkeypatch.setattr(admin_settings, "bootstrap_password", "strong-password-XyZ-123")

    validate_admin_settings_for("production")
