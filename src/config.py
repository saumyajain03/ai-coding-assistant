"""
Project SentinelForge: Centralized Configuration System
Validates all environment settings dynamically using Pydantic Settings.
Enforces filesystem path jails, resource limits, and provider configurations.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Runtime & Server ---
    APP_NAME: str = "SentinelForge"
    APP_VERSION: str = "0.1.0"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Storage & Workspace Sandboxing ---
    DATA_DIR: Path = Field(default=Path("./data"))
    WORKSPACE_ROOT: Path = Field(default=Path("./data/workspace"))
    VECTOR_DB_PATH: Path = Field(default=Path("./data/chroma"))
    SCRATCH_DIR: Path = Field(default=Path("./data/scratch"))

    # --- Local RAG & Graph Pipeline ---
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"
    OFFLINE_MODE: bool = False
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    TOP_K_RETRIEVAL: int = 5
    KNOWLEDGE_GRAPH_PATH: Path = Field(default=Path("./data/chroma/knowledge_graph.db"))

    # Configurable Retrieval Sufficiency Signals
    RETRIEVAL_SUFFICIENCY_MIN_SCORE: float = 0.40
    RETRIEVAL_SUFFICIENCY_MIN_RESULTS: int = 2
    RETRIEVAL_SUFFICIENCY_MIN_MARGIN: float = 0.05
    GRAPH_MAX_HOPS_DEFAULT: int = 2

    # --- PDF & Page-Aware Extraction Settings ---
    MAX_PDF_SIZE_MB: int = 20
    MAX_PDF_PAGES: int = 100
    PDF_PAGE_TEXT_MIN_CHARS: int = 50
    PDF_SCANNED_MAX_CHARS: int = 40
    PDF_VISUAL_MIN_IMAGES: int = 1
    PDF_VISUAL_AREA_RATIO_MIN: float = 0.20
    CANONICAL_PAGES_DB_PATH: Path = Field(default=Path("./data/chroma/canonical_pages.db"))

    # --- Lazy OCR Fallback Settings ---
    ENABLE_OCR: bool = True
    MAX_OCR_PAGES_PER_REQUEST: int = 3
    OCR_TIMEOUT_SEC: int = 10
    OCR_CACHE_DIR: Path = Field(default=Path("./data/scratch/ocr_cache"))

    # --- Lazy Visual RAG Settings (Render-Friendly) ---
    ENABLE_VISUAL_RAG: bool = False
    ENABLE_LAZY_VISUAL_PROCESSING: bool = True
    VISUAL_PROCESSING_MODE: Literal["on_demand", "precompute", "disabled"] = "on_demand"
    MAX_VISUAL_PAGES_PER_REQUEST: int = 2
    MAX_RENDER_IMAGE_RES: int = 150
    MAX_VISUAL_REGIONS_PER_PAGE: int = 5
    VISUAL_TIMEOUT_SEC: int = 10
    VISUAL_MODEL_NAME: str = "deterministic-visual-feature-v1"
    VISUAL_CACHE_DIR: Path = Field(default=Path("./data/scratch/visual_cache"))
    DOCUMENT_STORE_DIR: Path = Field(default=Path("./data/scratch/documents"))
    CACHE_MAX_SIZE_MB: int = 100

    # --- LLM Inference Providers ---
    LLM_PROVIDER: Literal[
        "ollama", "groq_free", "hf_free", "openai_compatible", "synthetic_mock"
    ] = "synthetic_mock"
    LLM_MODEL: str = "llama3.2:1b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_API_KEY: str | None = None
    HF_TOKEN: str | None = None
    GROQ_API_KEY: str | None = None
    OPENAI_API_BASE: str = "https://api.openai.com/v1"

    # --- System Sandbox Resource Limits ---
    SANDBOX_TIMEOUT_SEC: int = 5
    SANDBOX_MAX_TIMEOUT_SEC: int = 300
    SANDBOX_MEMORY_LIMIT_MB: int = 200
    SANDBOX_MAX_MEMORY_MB: int = 200
    SANDBOX_MAX_NPROC: int = 10
    SANDBOX_MAX_OUTPUT_BYTES: int = 1024 * 1024
    SANDBOX_CPU_LIMIT_PERCENT: int = 50
    ALLOW_OUTBOUND_NETWORK: bool = False
    ALLOW_NETWORK_DEFAULT: bool = False

    # --- Security & Human-in-the-loop Invariants ---
    AUTO_APPLY_PATCHES: bool = False
    REQUIRE_APPROVAL_GATE: bool = True
    REQUIRE_HUMAN_APPROVAL_FOR_PATCH: bool = True
    AUDIT_LOG_PATH: Path = Field(default=Path("./data/audit.log"))

    # --- API Security & Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60
    MAX_UPLOAD_SIZE_MB: int = 10
    CORS_ORIGINS: list[str] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                return ["*"]
            if v_clean.startswith("[") and v_clean.endswith("]"):
                import json

                try:
                    return json.loads(v_clean)
                except Exception:
                    pass
            else:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v if isinstance(v, list) else ["*"]

    def ensure_directories_exist(self) -> None:
        """Create necessary runtime data directories on startup."""
        for path in [
            self.DATA_DIR,
            self.WORKSPACE_ROOT,
            self.VECTOR_DB_PATH,
            self.SCRATCH_DIR,
            self.OCR_CACHE_DIR,
            self.VISUAL_CACHE_DIR,
            self.DOCUMENT_STORE_DIR,
        ]:
            path.resolve().mkdir(parents=True, exist_ok=True)

    def is_path_in_workspace(self, target_path: Path | str) -> bool:
        """
        Security verification invariant: checks that a path strictly resolves
        within WORKSPACE_ROOT, preventing path traversal and symlink escapes.
        """
        try:
            workspace_real = Path(self.WORKSPACE_ROOT).resolve()
            target_real = Path(target_path).resolve()
            return target_real == workspace_real or workspace_real in target_real.parents
        except Exception:
            return False

    def validate_provider_keys(self) -> tuple[bool, str | None]:
        """
        Validates whether required keys are present for cloud inference.
        Returns (is_valid, error_message).
        """
        if self.LLM_PROVIDER in ("groq_free", "hf_free") and not self.LLM_API_KEY:
            return (
                False,
                f"LLM_PROVIDER is set to '{self.LLM_PROVIDER}', but LLM_API_KEY is not configured.",
            )
        return True, None


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor for application settings."""
    settings = Settings()
    settings.ensure_directories_exist()
    return settings
