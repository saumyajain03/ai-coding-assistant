"""
SentinelForge Official FastAPI Application Core
Exposes OpenAPI 3.1 documentation, interactive Swagger UI, and defensive middlewares.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware import (
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from src.api.routes.platform import router as platform_router
from src.config import get_settings


def create_app() -> FastAPI:
    """Creates and configures the production-ready FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="SentinelForge AI Developer Platform",
        description="Privacy-First Autonomous Engineering & Security Platform with 7-Stage Verifiable Agent Loops",
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. Register Defending Middlewares in reverse execution order
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.RATE_LIMIT_PER_MINUTE)

    # 2. CORS allowlist (strict configuration)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS or ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # 3. Mount Platform API Routers
    app.include_router(platform_router)

    return app


# Default application instance
app = create_app()
