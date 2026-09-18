# Sample Security Microservice Codebase

This code repository is part of the SentinelForge Phase 2 manual validation suite.
It demonstrates a multi-tier Python application with explicit dependency flows:

- `app/main.py` -> imports and calls `app.auth.AuthService`
- `app/auth.py` -> imports and calls `app.database.get_user_from_db` and `app.cache.invalidate_cache`
- `tests/test_auth.py` -> imports and tests `app.auth.AuthService`
- `tests/test_database.py` -> imports and tests `app.database.get_user_from_db`
- `config/settings.json` -> defines application parameters and tokens
