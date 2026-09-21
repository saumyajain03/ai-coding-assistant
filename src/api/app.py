"""
SentinelForge Official FastAPI Application Core
Exposes OpenAPI 3.1 documentation, interactive Swagger UI, and defensive middlewares.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

    # 4. Mount Production Frontend (React SPA) if dist exists
    dist_dir = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist_dir.exists() and (dist_dir / "index.html").exists():
        assets_dir = dist_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static_assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            candidate = dist_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(dist_dir / "index.html"))

    return app


# Default application instance
app = create_app()
