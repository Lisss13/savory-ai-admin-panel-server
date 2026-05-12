"""Unit-тесты для `app.admin.security`: хеш пароля и JWT."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.admin import security
from app.admin.config import admin_settings
from app.admin.exceptions import InvalidToken


def test_hash_password_produces_different_hashes_for_same_input():
    """Bcrypt каждый раз подмешивает свежую соль — два хеша одного пароля разные."""
    h1 = security.hash_password("s3cret")
    h2 = security.hash_password("s3cret")
    assert h1 != h2
    assert h1 != "s3cret"


def test_verify_password_accepts_correct_password():
    """`verify_password` подтверждает корректный пароль."""
    h = security.hash_password("correct horse battery staple")
    assert security.verify_password("correct horse battery staple", h) is True


def test_verify_password_rejects_wrong_password():
    """Неправильный пароль не должен пройти проверку."""
    h = security.hash_password("right")
    assert security.verify_password("wrong", h) is False


def test_verify_password_returns_false_for_garbage_hash():
    """Сломанный хеш — это `False`, а не исключение наружу."""
    assert security.verify_password("anything", "not-a-bcrypt-hash") is False


def test_create_access_token_roundtrips_through_decode():
    """Закодированный токен декодируется в ту же полезную нагрузку."""
    token = security.create_access_token(subject=42)
    payload = security.decode_access_token(token)
    assert payload.sub == 42
    assert payload.exp > int(datetime.now(tz=UTC).timestamp())


def test_decode_access_token_rejects_wrong_signature():
    """Токен, подписанный чужим секретом, отвергается."""
    bad = jwt.encode(
        {"sub": "1", "exp": int((datetime.now(tz=UTC) + timedelta(hours=1)).timestamp())},
        "totally-different-secret-of-sufficient-length-32b",
        algorithm=admin_settings.jwt_algorithm,
    )
    with pytest.raises(InvalidToken):
        security.decode_access_token(bad)


def test_decode_access_token_rejects_expired_token():
    """Истёкший токен отвергается с `InvalidToken`."""
    expired = jwt.encode(
        {"sub": "1", "exp": int((datetime.now(tz=UTC) - timedelta(seconds=1)).timestamp())},
        admin_settings.jwt_secret,
        algorithm=admin_settings.jwt_algorithm,
    )
    with pytest.raises(InvalidToken):
        security.decode_access_token(expired)


def test_decode_access_token_rejects_malformed_token():
    """Бессмысленная строка — это `InvalidToken`."""
    with pytest.raises(InvalidToken):
        security.decode_access_token("not.a.jwt")
