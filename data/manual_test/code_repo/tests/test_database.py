"""
Unit tests for database module
"""

from app.database import get_user_from_db


def test_get_user_from_db():
    user = get_user_from_db("admin_01")
    assert user is not None
    assert user["role"] == "admin"

    missing = get_user_from_db("non_existent")
    assert missing is None
