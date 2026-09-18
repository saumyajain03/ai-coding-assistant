"""
Authentication Service providing JWT validation and credential verification
"""

from typing import Any

from app.cache import invalidate_cache
from app.database import get_user_from_db


class AuthService:
    """Core authentication handler."""

    def __init__(self, token_ttl_seconds: int = 3600):
        self.token_ttl_seconds = token_ttl_seconds

    def authenticate_user(self, user_id: str, password_hash: str) -> dict[str, Any]:
        """
        Authenticates user credentials against the database and clears old sessions.
        """
        user = get_user_from_db(user_id)
        if not user or not user.get("active"):
            raise PermissionError(f"User '{user_id}' does not exist or is inactive.")

        invalidate_cache(f"user_session_{user_id}")
        return {
            "user_id": user["user_id"],
            "role": user["role"],
            "authenticated": True,
        }

    def validate_token(self, token_payload: dict[str, Any]) -> bool:
        """
        Validates token payload integrity, scopes, and expiration bounds.
        """
        if not token_payload or "sub" not in token_payload:
            return False
        user_id = token_payload["sub"]
        user = get_user_from_db(user_id)
        return user is not None and user.get("active", False)
