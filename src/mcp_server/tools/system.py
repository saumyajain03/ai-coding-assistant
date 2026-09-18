"""
MCP Tool: System Telemetry and Audit
Returns comprehensive platform health, active LLM provider mode,
sandbox constraints, vector index counts, and recent security audit events.
"""

import time
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings
from src.rag.canonical_page import get_canonical_page_store
from src.rag.ocr_engine import get_ocr_engine
from src.rag.vector_store import get_vector_store
from src.rag.visual_engine import get_visual_engine
from src.sandbox.audit import get_audit_logger

_SERVER_START_TIME = time.time()


class SystemTelemetryResult(BaseModel):
    app_name: str
    version: str
    status: str
    uptime_seconds: float
    active_llm_provider: str
    data_processing_mode: str
    vector_store_doc_count: int
    indexed_files_count: int
    multimodal_capabilities: dict[str, Any] = Field(default_factory=dict)
    sandbox_limits: dict[str, Any]
    audit_events_count: int
    recent_audit_trail: list[dict[str, Any]]


def get_system_telemetry_tool(include_audit_trail: bool = True) -> dict[str, Any]:
    """
    Returns platform telemetry, active model mode, sandbox limits, and security audit log.

    Args:
        include_audit_trail: Whether to include recent audit event entries (default True).

    Returns:
        Structured telemetry dictionary.
    """
    settings = get_settings()
    vector_store = get_vector_store()
    audit_logger = get_audit_logger()

    indexed_files = vector_store.get_indexed_files()
    uptime = round(time.time() - _SERVER_START_TIME, 2)

    processing_mode = (
        "100% Local (Air-Gapped/Private)"
        if settings.LLM_PROVIDER in ("ollama", "synthetic_mock")
        else f"Cloud Zero-Cost ({settings.LLM_PROVIDER})"
    )

    trail = audit_logger.get_recent_events(limit=20) if include_audit_trail else []

    page_store = get_canonical_page_store()
    ocr_engine = get_ocr_engine()
    visual_engine = get_visual_engine()

    return SystemTelemetryResult(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        status="operational",
        uptime_seconds=uptime,
        active_llm_provider=settings.LLM_PROVIDER,
        data_processing_mode=processing_mode,
        vector_store_doc_count=vector_store.count(),
        indexed_files_count=len(indexed_files),
        multimodal_capabilities={
            "ocr_enabled": settings.ENABLE_OCR,
            "ocr_available": ocr_engine.is_ocr_available(),
            "visual_rag_enabled": settings.ENABLE_VISUAL_RAG,
            "visual_rag_active": visual_engine.is_visual_active(),
            "visual_processing_mode": settings.VISUAL_PROCESSING_MODE,
            "canonical_pages": page_store.get_stats(),
            "limits": {
                "max_pdf_size_mb": settings.MAX_PDF_SIZE_MB,
                "max_pdf_pages": settings.MAX_PDF_PAGES,
                "max_ocr_pages_per_request": settings.MAX_OCR_PAGES_PER_REQUEST,
                "max_visual_pages_per_request": settings.MAX_VISUAL_PAGES_PER_REQUEST,
                "max_render_image_res": settings.MAX_RENDER_IMAGE_RES,
                "ocr_timeout_sec": settings.OCR_TIMEOUT_SEC,
                "visual_timeout_sec": settings.VISUAL_TIMEOUT_SEC,
            },
        },
        sandbox_limits={
            "timeout_sec": settings.SANDBOX_TIMEOUT_SEC,
            "max_memory_mb": settings.SANDBOX_MAX_MEMORY_MB,
            "max_nproc": settings.SANDBOX_MAX_NPROC,
            "max_output_bytes": settings.SANDBOX_MAX_OUTPUT_BYTES,
            "network_blocked": not settings.ALLOW_NETWORK_DEFAULT,
            "human_approval_required": settings.REQUIRE_HUMAN_APPROVAL_FOR_PATCH,
        },
        audit_events_count=audit_logger.count(),
        recent_audit_trail=trail,
    ).model_dump()
