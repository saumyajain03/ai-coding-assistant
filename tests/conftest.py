"""
Pytest configuration and shared fixtures for Project SentinelForge.
Provides isolated workspace, settings, audit state, API test clients,
and benchmark sample data fixtures.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import get_approval_manager


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Provides a temporary, isolated workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Provides an isolated Settings instance utilizing temporary paths."""
    data_dir = tmp_path / "data"
    workspace = data_dir / "workspace"
    chroma = data_dir / "chroma"
    scratch = data_dir / "scratch"

    settings = Settings(
        DATA_DIR=data_dir,
        WORKSPACE_ROOT=workspace,
        VECTOR_DB_PATH=chroma,
        SCRATCH_DIR=scratch,
        LLM_PROVIDER="synthetic_mock",
        OFFLINE_MODE=True,
    )
    settings.ensure_directories_exist()
    return settings


@pytest.fixture
def api_client() -> TestClient:
    """Provides a fresh FastAPI TestClient for platform endpoint testing."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def clean_security_state():
    """Resets audit logs and approval tokens to guarantee test isolation."""
    audit = get_audit_logger()
    approvals = get_approval_manager()
    audit.clear()
    approvals.clear()
    yield
    audit.clear()
    approvals.clear()
