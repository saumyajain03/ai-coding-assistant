"""
Unit tests for authentication service
"""

import pytest
from app.auth import AuthService


def test_auth_service_success():
    auth_svc = AuthService()
    res = auth_svc.authenticate_user("admin_01", "hash_val")
    assert res["authenticated"] is True
    assert res["role"] == "admin"


def test_auth_service_inactive_user():
    auth_svc = AuthService()
    with pytest.raises(PermissionError):
        auth_svc.authenticate_user("unknown_user", "hash_val")


def test_validate_token():
    auth_svc = AuthService()
    assert auth_svc.validate_token({"sub": "admin_01"}) is True
    assert auth_svc.validate_token({"sub": "missing"}) is False
