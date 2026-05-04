"""Tests for lipmm.control.auth — JWT issuance + verification."""

from __future__ import annotations

import os
import time

import pytest

from lipmm.control.auth import (
    AuthMisconfigured,
    SECRET_ENV_VAR,
    constant_time_secret_compare,
    get_secret,
    issue_token,
    verify_token,
)


SECRET = "0123456789abcdef0123456789abcdef"  # 32-char hex


def test_issue_and_verify_round_trip() -> None:
    token = issue_token(SECRET, actor="alice")
    claims = verify_token(token, SECRET)
    assert claims["sub"] == "alice"
    assert "iat" in claims
    assert "exp" in claims
    assert claims["exp"] > time.time()


def test_default_actor() -> None:
    token = issue_token(SECRET)
    claims = verify_token(token, SECRET)
    assert claims["sub"] == "operator"


def test_verify_rejects_wrong_secret() -> None:
    from fastapi import HTTPException
    token = issue_token(SECRET)
    with pytest.raises(HTTPException) as exc_info:
        verify_token(token, "different-secret-also-32-chars-long")
    assert exc_info.value.status_code == 401


def test_verify_rejects_expired_token() -> None:
    from fastapi import HTTPException
    # Issue with negative TTL → expires immediately
    token = issue_token(SECRET, ttl_seconds=-1)
    with pytest.raises(HTTPException) as exc_info:
        verify_token(token, SECRET)
    assert exc_info.value.status_code == 401


def test_verify_rejects_garbage() -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        verify_token("not-a-jwt", SECRET)


def test_constant_time_compare() -> None:
    assert constant_time_secret_compare("abc123", "abc123") is True
    assert constant_time_secret_compare("abc123", "abc124") is False
    # Different lengths still safely return False
    assert constant_time_secret_compare("abc", "abcdef") is False


def test_get_secret_requires_env_var(monkeypatch) -> None:
    monkeypatch.delenv(SECRET_ENV_VAR, raising=False)
    with pytest.raises(AuthMisconfigured):
        get_secret()


def test_get_secret_rejects_short_secret(monkeypatch) -> None:
    monkeypatch.setenv(SECRET_ENV_VAR, "short")
    with pytest.raises(AuthMisconfigured):
        get_secret()


def test_get_secret_accepts_strong_secret(monkeypatch) -> None:
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
    assert get_secret() == SECRET


def test_unique_jti_per_token() -> None:
    """Each token has a unique jti (JWT ID) for audit traceability."""
    token1 = issue_token(SECRET)
    token2 = issue_token(SECRET)
    claims1 = verify_token(token1, SECRET)
    claims2 = verify_token(token2, SECRET)
    assert claims1["jti"] != claims2["jti"]
