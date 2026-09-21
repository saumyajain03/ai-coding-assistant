"""
Phase 0 Verification: Centralized Configuration and Path Jail Tests
"""

from src.config import Settings, get_settings


def test_settings_defaults_and_env_loading():
    """Verify that settings load defaults and parse environment correctly."""
    settings = get_settings()
    assert settings.APP_NAME == "SentinelForge"
    assert settings.PORT in (8000, 8001)
    assert settings.SANDBOX_TIMEOUT_SEC > 0
    assert settings.SANDBOX_MAX_MEMORY_MB >= 128
    assert settings.SANDBOX_MAX_NPROC >= 1
    assert settings.REQUIRE_HUMAN_APPROVAL_FOR_PATCH is True


def test_runtime_directories_created(tmp_path):
    """Verify ensure_directories_exist creates required dirs."""
    test_settings = Settings(
        DATA_DIR=tmp_path / "data",
        WORKSPACE_ROOT=tmp_path / "data" / "workspace",
        VECTOR_DB_PATH=tmp_path / "data" / "chroma",
        SCRATCH_DIR=tmp_path / "data" / "scratch",
    )
    test_settings.ensure_directories_exist()

    assert test_settings.DATA_DIR.exists()
    assert test_settings.WORKSPACE_ROOT.exists()
    assert test_settings.VECTOR_DB_PATH.exists()
    assert test_settings.SCRATCH_DIR.exists()


def test_workspace_path_jail_security(tmp_path):
    """
    CRITICAL SECURITY INVARIANT:
    Verify that paths outside WORKSPACE_ROOT are strictly rejected.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = Settings(WORKSPACE_ROOT=workspace)

    # Valid in-workspace paths
    inside_file = workspace / "test.py"
    inside_file.touch()
    inside_sub = workspace / "src" / "deep"
    inside_sub.mkdir(parents=True)

    assert settings.is_path_in_workspace(inside_file) is True
    assert settings.is_path_in_workspace(inside_sub) is True
    assert settings.is_path_in_workspace(workspace) is True

    # Path traversal attempts
    outside_file = tmp_path / "outside.txt"
    outside_file.touch()
    traversal_path = workspace / ".." / "outside.txt"

    assert settings.is_path_in_workspace(outside_file) is False
    assert settings.is_path_in_workspace(traversal_path) is False
    assert settings.is_path_in_workspace("/etc/passwd") is False


def test_cors_parsing():
    """Verify CORS origins string/json parsing."""
    settings = Settings(CORS_ORIGINS='["https://example.com", "http://localhost:3000"]')
    assert "https://example.com" in settings.CORS_ORIGINS
    assert "http://localhost:3000" in settings.CORS_ORIGINS


def test_provider_key_validation():
    """Verify cloud providers demand API keys while mock/ollama do not."""
    # Synthetic mock does not require API key
    mock_settings = Settings(LLM_PROVIDER="synthetic_mock", LLM_API_KEY=None)
    valid, err = mock_settings.validate_provider_keys()
    assert valid is True
    assert err is None

    # Ollama does not require API key
    ollama_settings = Settings(LLM_PROVIDER="ollama", LLM_API_KEY=None)
    valid, err = ollama_settings.validate_provider_keys()
    assert valid is True
    assert err is None

    # Cloud provider without key fails validation
    groq_settings = Settings(LLM_PROVIDER="groq_free", LLM_API_KEY=None)
    valid, err = groq_settings.validate_provider_keys()
    assert valid is False
    assert "LLM_API_KEY is not configured" in err
