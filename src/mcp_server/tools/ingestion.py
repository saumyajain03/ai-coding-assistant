"""
MCP Tool: Content Ingestion
Ingests documents, code files, and PDFs into the local vector index with
content hashing, duplicate detection, and source metadata extraction.
"""

from pathlib import Path
from typing import Any

from src.rag.indexer import ALLOWED_EXTENSIONS, get_rag_indexer


def ingest_content_tool(
    filename: str,
    content: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    """
    Ingests, parses, chunks, and indexes documents and code files into the local RAG engine.

    Args:
        filename: Name of the file with extension (.pdf, .md, .txt, .json, .py, .js, .ts).
        content: Raw text content (optional if file_path is provided).
        file_path: Relative or absolute path to the file (optional if content is provided).

    Returns:
        Structured dictionary containing document ID, chunk count, SHA-256 hash, and indexing status.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return {
            "error": f"UNSUPPORTED_FILE_TYPE: Extension '{ext}' is not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
            "filename": filename,
            "status": "failed",
        }

    content_bytes: bytes | None = None
    target_disk_path: Path | None = None

    if content is not None:
        content_bytes = content.encode("utf-8")
    elif file_path:
        target_disk_path = Path(file_path).resolve()
        if not target_disk_path.exists():
            return {
                "error": f"FILE_NOT_FOUND: Path '{file_path}' does not exist on disk.",
                "status": "failed",
            }
        content_bytes = target_disk_path.read_bytes()
    else:
        return {
            "error": "INVALID_ARGUMENTS: Either 'content' or 'file_path' must be provided.",
            "status": "failed",
        }

    indexer = get_rag_indexer()
    try:
        result = indexer.index_file(
            filename=filename,
            content_bytes=content_bytes,
            file_path=target_disk_path,
        )
        return result.model_dump()
    except ValueError as e:
        return {
            "error": str(e),
            "filename": filename,
            "status": "failed",
        }
    except Exception as e:
        return {
            "error": f"INDEXING_ERROR: {str(e)}",
            "filename": filename,
            "status": "failed",
        }
