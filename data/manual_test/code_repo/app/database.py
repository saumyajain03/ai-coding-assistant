"""
Database Access Layer for User Records
"""

from typing import Any


def get_user_from_db(user_id: str) -> dict[str, Any] | None:
    """
    Retrieves user record from database by user_id.
    """
    db_records = {
        "admin_01": {"user_id": "admin_01", "role": "admin", "active": True},
        "analyst_02": {"user_id": "analyst_02", "role": "analyst", "active": True},
    }
    return db_records.get(user_id)
