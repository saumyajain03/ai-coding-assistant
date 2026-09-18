"""
Pytest configuration and shared fixtures for Project SentinelForge.
"""

from pathlib import Path

import pytest

from src.config import Settings


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
