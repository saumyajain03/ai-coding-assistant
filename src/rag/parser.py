"""
RAG Multi-Format Document Parsers
Extracts content with precise line ranges, section headings, and page numbers from:
- PDF (page-aware PDF parser)
- Markdown (section-aware Markdown parser)
- Python (Python AST parser)
- JavaScript (JS structural parser)
- TypeScript (TS structural parser)
- JSON (JSON structural parser)
- Text (Text parser)

All parsers normalize into the standard ParsedSection schema with exact provenance.
"""

import ast
import json
import re
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pypdf import PdfReader

from src.config import get_settings
from src.rag.canonical_page import (
    CanonicalPageRecord,
    OCRStatus,
    PageType,
    VisualStatus,
    get_canonical_page_store,
)
from src.rag.pdf_classifier import classify_pdf_page


class ParsedSection(BaseModel):
    content: str
    page: int | None = None
    start_line: int
    end_line: int
    section_name: str | None = None
    chunk_type: str = "text"  # text, code_function, code_class, code_interface, markdown_section, json_object, pdf_page
    metadata: dict[str, Any] = Field(default_factory=dict)


def parse_document(
    filename: str,
    content_bytes: bytes | None = None,
    file_path: Path | None = None,
) -> list[ParsedSection]:
    """
    Routes files to format-specific parsers, normalizing into standard ParsedSection objects.
    """
    ext = Path(filename).suffix.lower()

    if file_path and file_path.exists():
        raw_bytes = file_path.read_bytes()
    elif content_bytes is not None:
        raw_bytes = content_bytes
    else:
        raise ValueError("Either content_bytes or existing file_path must be provided.")

    if ext == ".pdf":
        return _parse_pdf(raw_bytes, filename=filename)

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1", errors="replace")

    if ext == ".py":
        return _parse_python_ast(text)
    elif ext == ".js":
        return _parse_javascript(text)
    elif ext == ".ts":
        return _parse_typescript(text)
    elif ext == ".md":
        return _parse_markdown(text)
    elif ext == ".json":
        return _parse_json(text)
    else:
        return _parse_text(text)


def _parse_pdf(raw_bytes: bytes, filename: str = "document.pdf") -> list[ParsedSection]:
    """
    Dedicated page-aware PDF parser with Render-friendly bounds, deterministic
    page classification, and canonical page record persistence.
    """
    settings = get_settings()

    # 1. Enforce file size limit
    max_bytes = settings.MAX_PDF_SIZE_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise ValueError(
            f"PDF file size ({len(raw_bytes) / 1024 / 1024:.2f}MB) exceeds configured maximum limit of {settings.MAX_PDF_SIZE_MB}MB."
        )

    sections: list[ParsedSection] = []
    reader = PdfReader(BytesIO(raw_bytes))

    # 2. Enforce page count limit
    page_count = len(reader.pages)
    if page_count > settings.MAX_PDF_PAGES:
        raise ValueError(
            f"PDF page count ({page_count}) exceeds configured maximum limit of {settings.MAX_PDF_PAGES} pages."
        )

    file_hash = sha256(raw_bytes).hexdigest()
    doc_id = f"doc_{file_hash[:12]}"

    # Save raw bytes to document store for lazy on-demand OCR / Visual processing
    doc_store_path = settings.DOCUMENT_STORE_DIR / f"{doc_id}.pdf"
    try:
        doc_store_path.parent.mkdir(parents=True, exist_ok=True)
        doc_store_path.write_bytes(raw_bytes)
    except Exception:
        pass

    canonical_pages: list[CanonicalPageRecord] = []
    current_line = 1

    for page_idx, page in enumerate(reader.pages):
        page_number = page_idx + 1  # 1-indexed for citations
        text = page.extract_text() or ""
        clean_text = text.strip()
        lines = text.splitlines()
        line_count = max(1, len(lines))

        # Safely extract embedded images if present
        page_images = list(getattr(page, "images", []))

        # Page dimensions
        width = 612.0
        height = 792.0
        if getattr(page, "mediabox", None):
            try:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
            except Exception:
                pass

        # 3. Classify Page
        page_type, metrics = classify_pdf_page(
            page_text=clean_text,
            page_images=page_images,
            page_width=width,
            page_height=height,
        )

        modalities = ["text"]
        ocr_status = OCRStatus.NOT_REQUIRED
        visual_status = VisualStatus.NOT_REQUIRED

        if page_type == PageType.SCANNED_PAGE:
            ocr_status = OCRStatus.PENDING
            modalities.append("ocr")
        elif page_type == PageType.VISUAL_HEAVY_PAGE:
            visual_status = VisualStatus.PENDING
            modalities.append("visual")
        elif page_type == PageType.MIXED_PAGE:
            modalities.extend(["ocr", "visual"])

        # 4. Construct Canonical Page Record
        canonical_rec = CanonicalPageRecord(
            doc_id=doc_id,
            filename=filename,
            sha256_hash=file_hash,
            page_number=page_number,
            page_index=page_idx,
            text=clean_text,
            start_line=current_line,
            end_line=current_line + line_count - 1,
            section=f"Page {page_number}",
            page_type=page_type,
            available_modalities=modalities,
            ocr_status=ocr_status,
            visual_status=visual_status,
            source_path=str(doc_store_path),
            extraction_warnings=[],
            image_count=metrics["image_count"],
            image_area_ratio=metrics["image_area_ratio"],
            char_count=metrics["char_count"],
            word_count=metrics["word_count"],
        )
        canonical_pages.append(canonical_rec)

        # 5. Emit normalized ParsedSection for downstream chunking
        section_content = clean_text
        is_placeholder = False
        if not section_content and page_type == PageType.SCANNED_PAGE:
            section_content = f"[Scanned Page {page_number} - Text not selectable. OCR fallback available]"
            is_placeholder = True

        sections.append(
            ParsedSection(
                content=section_content,
                page=page_number,
                start_line=current_line,
                end_line=current_line + line_count - 1,
                section_name=f"Page {page_number}",
                chunk_type="pdf_page",
                metadata={
                    "page_number": page_number,
                    "line_count": line_count,
                    "page_type": page_type.value,
                    "available_modalities": modalities,
                    "ocr_status": ocr_status.value,
                    "visual_status": visual_status.value,
                    "filename": filename,
                    "is_placeholder": is_placeholder,
                    "doc_id": doc_id,
                },
            )
        )
        current_line += line_count

    # Persist canonical records to SQLite store
    get_canonical_page_store().save_pages(canonical_pages)

    return sections


def _parse_python_ast(code: str) -> list[ParsedSection]:
    """
    Dedicated Python AST parser.
    Extracts classes, methods, functions, docstrings, imports, and calls with exact line numbers.
    """
    lines = code.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return []

    sections: list[ParsedSection] = []

    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", start + 10)
                chunk_lines = lines[start - 1 : end]
                calls = [
                    n.func.id
                    for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                ]
                sections.append(
                    ParsedSection(
                        content="\n".join(chunk_lines),
                        start_line=start,
                        end_line=end,
                        section_name=f"def {node.name}()",
                        chunk_type="code_function",
                        metadata={
                            "symbol_name": node.name,
                            "symbol_type": "function",
                            "calls": calls[:15],
                            "is_async": isinstance(node, ast.AsyncFunctionDef),
                        },
                    )
                )

            elif isinstance(node, ast.ClassDef):
                start = node.lineno
                end = getattr(node, "end_lineno", start + 20)
                chunk_lines = lines[start - 1 : end]
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                methods = [
                    m.name
                    for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                sections.append(
                    ParsedSection(
                        content="\n".join(chunk_lines),
                        start_line=start,
                        end_line=end,
                        section_name=f"class {node.name}",
                        chunk_type="code_class",
                        metadata={
                            "symbol_name": node.name,
                            "symbol_type": "class",
                            "bases": bases,
                            "methods": methods,
                        },
                    )
                )

    except SyntaxError:
        # Fallback to structural lines if code has syntax errors
        pass

    if not sections:
        return _parse_text(code, chunk_type="code_snippet")

    return sections


def _parse_javascript(code: str) -> list[ParsedSection]:
    """
    Dedicated JavaScript structural parser.
    Detects function declarations, arrow functions, ES6 classes, and CommonJS exports.
    """
    lines = code.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return []

    sections: list[ParsedSection] = []
    js_pattern = re.compile(
        r"^(?:export\s+)?(?:async\s+)?(?:function\s+([a-zA-Z0-9_$]+)|class\s+([a-zA-Z0-9_$]+)|(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\()"
    )

    current_start = 1
    current_name = "Header"
    symbol_name = None
    symbol_type = "module"

    for idx, line in enumerate(lines, start=1):
        match = js_pattern.match(line.strip())
        if match and idx > current_start:
            content = "\n".join(lines[current_start - 1 : idx - 1])
            if content.strip():
                sections.append(
                    ParsedSection(
                        content=content,
                        start_line=current_start,
                        end_line=idx - 1,
                        section_name=current_name,
                        chunk_type="code_function" if "function" in current_name else "code_block",
                        metadata={"symbol_name": symbol_name, "symbol_type": symbol_type},
                    )
                )
            current_start = idx
            symbol_name = match.group(1) or match.group(2) or match.group(3) or "Block"
            symbol_type = "class" if match.group(2) else "function"
            current_name = f"js:{symbol_name}"

    # Final section
    content = "\n".join(lines[current_start - 1 : total_lines])
    if content.strip():
        sections.append(
            ParsedSection(
                content=content,
                start_line=current_start,
                end_line=total_lines,
                section_name=current_name,
                chunk_type="code_function" if "function" in current_name else "code_block",
                metadata={"symbol_name": symbol_name, "symbol_type": symbol_type},
            )
        )

    return sections if sections else _parse_text(code, chunk_type="code_snippet")


def _parse_typescript(code: str) -> list[ParsedSection]:
    """
    Dedicated TypeScript structural parser.
    Detects interfaces, type aliases, enums, typed classes, and functions with generics.
    """
    lines = code.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return []

    sections: list[ParsedSection] = []
    ts_pattern = re.compile(
        r"^(?:export\s+)?(?:declare\s+)?(?:async\s+)?(?:interface\s+([a-zA-Z0-9_$]+)|type\s+([a-zA-Z0-9_$]+)|enum\s+([a-zA-Z0-9_$]+)|class\s+([a-zA-Z0-9_$]+)|function\s+([a-zA-Z0-9_$]+)|(?:const|let)\s+([a-zA-Z0-9_$]+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s*)?\()"
    )

    current_start = 1
    current_name = "Header"
    symbol_name = None
    symbol_type = "module"

    for idx, line in enumerate(lines, start=1):
        match = ts_pattern.match(line.strip())
        if match and idx > current_start:
            content = "\n".join(lines[current_start - 1 : idx - 1])
            if content.strip():
                sections.append(
                    ParsedSection(
                        content=content,
                        start_line=current_start,
                        end_line=idx - 1,
                        section_name=current_name,
                        chunk_type="code_interface" if "interface" in current_name else "code_block",
                        metadata={"symbol_name": symbol_name, "symbol_type": symbol_type},
                    )
                )
            current_start = idx
            # Extract matched group
            if match.group(1):
                symbol_name, symbol_type = match.group(1), "interface"
            elif match.group(2):
                symbol_name, symbol_type = match.group(2), "type"
            elif match.group(3):
                symbol_name, symbol_type = match.group(3), "enum"
            elif match.group(4):
                symbol_name, symbol_type = match.group(4), "class"
            elif match.group(5):
                symbol_name, symbol_type = match.group(5), "function"
            else:
                symbol_name, symbol_type = match.group(6) or "block", "variable"
            current_name = f"ts:{symbol_type}:{symbol_name}"

    # Final section
    content = "\n".join(lines[current_start - 1 : total_lines])
    if content.strip():
        sections.append(
            ParsedSection(
                content=content,
                start_line=current_start,
                end_line=total_lines,
                section_name=current_name,
                chunk_type="code_interface" if "interface" in current_name else "code_block",
                metadata={"symbol_name": symbol_name, "symbol_type": symbol_type},
            )
        )

    return sections if sections else _parse_text(code, chunk_type="code_snippet")


def _parse_markdown(text: str) -> list[ParsedSection]:
    """
    Dedicated section-aware Markdown parser.
    Splits along #, ##, and ### headers, preserving exact line numbers and heading titles.
    """
    lines = text.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return []

    sections: list[ParsedSection] = []
    header_pattern = re.compile(r"^(#{1,3})\s+(.+)$")

    current_start = 1
    current_title = "Overview"

    for idx, line in enumerate(lines, start=1):
        match = header_pattern.match(line)
        if match and idx > current_start:
            chunk = "\n".join(lines[current_start - 1 : idx - 1])
            if chunk.strip():
                sections.append(
                    ParsedSection(
                        content=chunk,
                        start_line=current_start,
                        end_line=idx - 1,
                        section_name=current_title,
                        chunk_type="markdown_section",
                        metadata={"heading": current_title},
                    )
                )
            current_start = idx
            current_title = match.group(2).strip()

    # Final section
    final_chunk = "\n".join(lines[current_start - 1 : total_lines])
    if final_chunk.strip():
        sections.append(
            ParsedSection(
                content=final_chunk,
                start_line=current_start,
                end_line=total_lines,
                section_name=current_title,
                chunk_type="markdown_section",
                metadata={"heading": current_title},
            )
        )

    return sections if sections else _parse_text(text)


def _parse_json(text: str) -> list[ParsedSection]:
    """
    Dedicated JSON structural parser.
    Segments top-level keys while preserving line structure.
    """
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            sections: list[ParsedSection] = []
            for key, val in data.items():
                snippet = f'"{key}": {json.dumps(val, indent=2)}'
                sections.append(
                    ParsedSection(
                        content=snippet,
                        start_line=1,
                        end_line=len(snippet.splitlines()),
                        section_name=f"Key: {key}",
                        chunk_type="json_object",
                        metadata={"key": key},
                    )
                )
            if sections:
                return sections
    except Exception:
        pass

    return _parse_text(text, chunk_type="json_snippet")


def _parse_text(text: str, chunk_type: str = "text") -> list[ParsedSection]:
    """
    Dedicated Plain Text parser.
    Chunks into 40-line blocks with 5-line overlap while preserving 1-indexed lines.
    """
    lines = text.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return []

    sections: list[ParsedSection] = []
    block_size = 40
    step = 35

    for i in range(0, total_lines, step):
        start_line = i + 1
        end_line = min(i + block_size, total_lines)
        chunk_lines = lines[start_line - 1 : end_line]
        chunk_content = "\n".join(chunk_lines)

        sections.append(
            ParsedSection(
                content=chunk_content,
                start_line=start_line,
                end_line=end_line,
                section_name=f"Lines {start_line}-{end_line}",
                chunk_type=chunk_type,
            )
        )
        if end_line >= total_lines:
            break

    return sections
