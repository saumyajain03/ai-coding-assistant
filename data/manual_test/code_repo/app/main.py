"""
Main Application Entrypoint
"""

import sys

from app.auth import AuthService


def run_application() -> int:
    """
    Initializes services and executes main application workflow.
    """
    auth_svc = AuthService(token_ttl_seconds=3600)
    auth_result = auth_svc.authenticate_user(
        user_id="admin_01",
        password_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    print(f"Application started successfully for user: {auth_result['user_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(run_application())
