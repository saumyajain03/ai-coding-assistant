"""
In-memory session and credential cache
"""

from typing import Any

CACHE_STORE: dict[str, Any] = {}


def invalidate_cache(session_key: str) -> bool:
    """
    Invalidates session key from the cache store.
    """
    if session_key in CACHE_STORE:
        del CACHE_STORE[session_key]
        return True
    return False
