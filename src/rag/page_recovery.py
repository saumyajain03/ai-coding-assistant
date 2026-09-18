"""
PDF Page Image Recovery Module
Locates canonical PDF files on disk or in the document cache,
and safely extracts page images for Lazy OCR and Visual RAG pipelines.
Strictly bounded in memory with zero cloud leakage.
"""

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from src.config import get_settings

logger = logging.getLogger(__name__)


def locate_pdf_file(doc_id: str, filename: str, source_path: str | None = None) -> Path | None:
    """
    Locates the PDF document on disk using canonical precedence:
    1. Explicit source_path from CanonicalPageRecord
    2. Persistent local document store (./data/scratch/documents/{doc_id}.pdf)
    3. Direct filename resolution if exists
    4. Known test directories (./data/manual_test/pdf/{filename})
    5. Workspace directory (./data/workspace/{filename})
    """
    settings = get_settings()

    # 1. Source path if valid
    if source_path:
        p = Path(source_path)
        if p.exists() and p.is_file():
            return p.resolve()

    # 2. Document store cache
    doc_store_path = settings.DOCUMENT_STORE_DIR / f"{doc_id}.pdf"
    if doc_store_path.exists() and doc_store_path.is_file():
        return doc_store_path.resolve()

    # 3. Direct filename
    direct_p = Path(filename)
    if direct_p.exists() and direct_p.is_file():
        return direct_p.resolve()

    # 4. Standard local directories
    candidate_dirs = [
        Path("data/manual_test/pdf"),
        Path("data/workspace"),
        Path(settings.WORKSPACE_ROOT),
        settings.SCRATCH_DIR,
    ]
    for d in candidate_dirs:
        candidate = d / filename
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
        # Also check just the basename if filename was a path
        candidate_base = d / direct_p.name
        if candidate_base.exists() and candidate_base.is_file():
            return candidate_base.resolve()

    return None


def recover_page_images(
    doc_id: str,
    filename: str,
    page_number: int,
    source_path: str | None = None,
) -> list[Any]:
    """
    Recovers page images for a specific 1-indexed page number from the canonical PDF.
    Returns a list of image objects (each having .name and .data bytes).
    """
    pdf_path = locate_pdf_file(doc_id, filename, source_path)
    if not pdf_path:
        logger.warning(
            "Could not locate PDF file on disk for doc_id=%s, filename=%s",
            doc_id,
            filename,
        )
        return []

    try:
        reader = PdfReader(pdf_path)
        if page_number < 1 or page_number > len(reader.pages):
            logger.warning(
                "Requested page_number %d out of bounds (1..%d) in %s",
                page_number,
                len(reader.pages),
                pdf_path,
            )
            return []

        page = reader.pages[page_number - 1]
        images = list(getattr(page, "images", []))
        return images
    except Exception as e:
        logger.error("Failed to recover page images from %s: %s", pdf_path, e)
        return []
