"""
Canonical PDF Page Record & Persistent Store
Maintains a first-class, immutable canonical record for every PDF page,
preserving exact 1-indexed page identity, layout metrics, extraction warnings,
and available retrieval modalities.
"""

import json
import sqlite3
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings


class PageType(StrEnum):
    TEXT_PAGE = "TEXT_PAGE"
    SCANNED_PAGE = "SCANNED_PAGE"
    MIXED_PAGE = "MIXED_PAGE"
    VISUAL_HEAVY_PAGE = "VISUAL_HEAVY_PAGE"
    EMPTY_OR_UNREADABLE_PAGE = "EMPTY_OR_UNREADABLE_PAGE"


class OCRStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class VisualStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class CanonicalPageRecord(BaseModel):
    doc_id: str
    filename: str
    sha256_hash: str
    page_number: int  # 1-indexed for user citations
    page_index: int  # 0-indexed for internal PDF operations
    text: str = ""
    start_line: int = 1
    end_line: int = 1
    section: str | None = None
    page_type: PageType = PageType.TEXT_PAGE
    available_modalities: list[str] = Field(default_factory=lambda: ["text"])
    ocr_status: OCRStatus = OCRStatus.NOT_REQUIRED
    visual_status: VisualStatus = VisualStatus.NOT_REQUIRED
    source_path: str = ""
    extraction_warnings: list[str] = Field(default_factory=list)
    image_count: int = 0
    image_area_ratio: float = 0.0
    char_count: int = 0
    word_count: int = 0

    @property
    def canonical_id(self) -> str:
        return f"{self.filename}:p{self.page_number}"

    @property
    def citation(self) -> str:
        return f"{self.filename}:Page {self.page_number} (L{self.start_line}-L{self.end_line})"


class CanonicalPageStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_settings().CANONICAL_PAGES_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_pages (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    page_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    section TEXT,
                    page_type TEXT NOT NULL,
                    available_modalities TEXT NOT NULL,
                    ocr_status TEXT NOT NULL,
                    visual_status TEXT NOT NULL,
                    source_path TEXT,
                    extraction_warnings TEXT,
                    image_count INTEGER NOT NULL,
                    image_area_ratio REAL NOT NULL,
                    char_count INTEGER NOT NULL,
                    word_count INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_canonical_filename ON canonical_pages(filename);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_canonical_page ON canonical_pages(filename, page_number);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_canonical_page_type ON canonical_pages(page_type);"
            )
            conn.commit()

    def save_pages(self, pages: list[CanonicalPageRecord]) -> int:
        if not pages:
            return 0
        with self._get_connection() as conn:
            for p in pages:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO canonical_pages (
                        id, doc_id, filename, sha256_hash, page_number, page_index,
                        text, start_line, end_line, section, page_type,
                        available_modalities, ocr_status, visual_status, source_path,
                        extraction_warnings, image_count, image_area_ratio, char_count, word_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        p.canonical_id,
                        p.doc_id,
                        p.filename,
                        p.sha256_hash,
                        p.page_number,
                        p.page_index,
                        p.text,
                        p.start_line,
                        p.end_line,
                        p.section,
                        p.page_type.value,
                        json.dumps(p.available_modalities),
                        p.ocr_status.value,
                        p.visual_status.value,
                        p.source_path,
                        json.dumps(p.extraction_warnings),
                        p.image_count,
                        p.image_area_ratio,
                        p.char_count,
                        p.word_count,
                    ),
                )
            conn.commit()
        return len(pages)

    def get_page(self, filename: str, page_number: int) -> CanonicalPageRecord | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM canonical_pages WHERE (filename = ? OR filename LIKE ?) AND page_number = ? LIMIT 1;",
                (filename, f"%{filename}", page_number),
            ).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_doc_pages(self, filename: str) -> list[CanonicalPageRecord]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM canonical_pages WHERE (filename = ? OR filename LIKE ?) ORDER BY page_number ASC;",
                (filename, f"%{filename}"),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def find_pages_by_type(
        self,
        page_type: PageType,
        filename: str | None = None,
    ) -> list[CanonicalPageRecord]:
        with self._get_connection() as conn:
            if filename:
                rows = conn.execute(
                    "SELECT * FROM canonical_pages WHERE (filename = ? OR filename LIKE ?) AND page_type = ? ORDER BY page_number ASC;",
                    (filename, f"%{filename}", page_type.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM canonical_pages WHERE page_type = ? ORDER BY filename, page_number ASC;",
                    (page_type.value,),
                ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def find_pages_by_modality(
        self,
        modality: str,
        filename: str | None = None,
    ) -> list[CanonicalPageRecord]:
        with self._get_connection() as conn:
            if filename:
                rows = conn.execute(
                    "SELECT * FROM canonical_pages WHERE (filename = ? OR filename LIKE ?) AND available_modalities LIKE ? ORDER BY page_number ASC;",
                    (filename, f"%{filename}", f"%{modality}%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM canonical_pages WHERE available_modalities LIKE ? ORDER BY filename, page_number ASC;",
                    (f"%{modality}%",),
                ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def update_page_ocr(
        self,
        filename: str,
        page_number: int,
        status: OCRStatus,
        ocr_text: str = "",
        warnings: list[str] | None = None,
    ) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT text, available_modalities, extraction_warnings FROM canonical_pages WHERE (filename = ? OR filename LIKE ?) AND page_number = ?;",
                (filename, f"%{filename}", page_number),
            ).fetchone()
            if not row:
                return False

            modalities: list[str] = json.loads(row["available_modalities"])
            if status == OCRStatus.COMPLETED and "ocr" not in modalities:
                modalities.append("ocr")

            existing_warnings: list[str] = json.loads(row["extraction_warnings"])
            if warnings:
                existing_warnings.extend(warnings)

            # If OCR text provided, append to text or update
            updated_text = row["text"]
            if ocr_text:
                updated_text = (
                    f"{row['text']}\n\n[OCR Text]:\n{ocr_text}".strip()
                    if row["text"]
                    else ocr_text
                )

            conn.execute(
                """
                UPDATE canonical_pages
                SET ocr_status = ?, text = ?, available_modalities = ?, extraction_warnings = ?
                WHERE (filename = ? OR filename LIKE ?) AND page_number = ?;
                """,
                (
                    status.value,
                    updated_text,
                    json.dumps(modalities),
                    json.dumps(existing_warnings),
                    filename,
                    f"%{filename}",
                    page_number,
                ),
            )
            conn.commit()
            return True

    def update_page_visual(
        self,
        filename: str,
        page_number: int,
        status: VisualStatus,
        warnings: list[str] | None = None,
    ) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT available_modalities, extraction_warnings FROM canonical_pages WHERE (filename = ? OR filename LIKE ?) AND page_number = ?;",
                (filename, f"%{filename}", page_number),
            ).fetchone()
            if not row:
                return False

            modalities: list[str] = json.loads(row["available_modalities"])
            if status == VisualStatus.COMPLETED and "visual" not in modalities:
                modalities.append("visual")

            existing_warnings: list[str] = json.loads(row["extraction_warnings"])
            if warnings:
                existing_warnings.extend(warnings)

            conn.execute(
                """
                UPDATE canonical_pages
                SET visual_status = ?, available_modalities = ?, extraction_warnings = ?
                WHERE (filename = ? OR filename LIKE ?) AND page_number = ?;
                """,
                (
                    status.value,
                    json.dumps(modalities),
                    json.dumps(existing_warnings),
                    filename,
                    f"%{filename}",
                    page_number,
                ),
            )
            conn.commit()
            return True

    def delete_by_filename(self, filename: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM canonical_pages WHERE filename = ?;",
                (filename,),
            )
            conn.commit()
            return cursor.rowcount

    def reset(self) -> None:
        """
        Clears all canonical page records from the SQLite database.
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM canonical_pages;")
            conn.commit()

    def get_stats(self) -> dict[str, Any]:
        with self._get_connection() as conn:
            total_pages = conn.execute("SELECT COUNT(*) FROM canonical_pages;").fetchone()[0]
            type_counts = dict(
                conn.execute(
                    "SELECT page_type, COUNT(*) FROM canonical_pages GROUP BY page_type;"
                ).fetchall()
            )
            ocr_counts = dict(
                conn.execute(
                    "SELECT ocr_status, COUNT(*) FROM canonical_pages GROUP BY ocr_status;"
                ).fetchall()
            )
            visual_counts = dict(
                conn.execute(
                    "SELECT visual_status, COUNT(*) FROM canonical_pages GROUP BY visual_status;"
                ).fetchall()
            )
            return {
                "total_canonical_pages": total_pages,
                "page_types": type_counts,
                "ocr_statuses": ocr_counts,
                "visual_statuses": visual_counts,
            }

    def _row_to_record(self, row: sqlite3.Row) -> CanonicalPageRecord:
        return CanonicalPageRecord(
            doc_id=row["doc_id"],
            filename=row["filename"],
            sha256_hash=row["sha256_hash"],
            page_number=row["page_number"],
            page_index=row["page_index"],
            text=row["text"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            section=row["section"],
            page_type=PageType(row["page_type"]),
            available_modalities=json.loads(row["available_modalities"]),
            ocr_status=OCRStatus(row["ocr_status"]),
            visual_status=VisualStatus(row["visual_status"]),
            source_path=row["source_path"] or "",
            extraction_warnings=json.loads(row["extraction_warnings"] or "[]"),
            image_count=row["image_count"],
            image_area_ratio=row["image_area_ratio"],
            char_count=row["char_count"],
            word_count=row["word_count"],
        )


_store_instance: CanonicalPageStore | None = None


def get_canonical_page_store() -> CanonicalPageStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = CanonicalPageStore()
    return _store_instance
