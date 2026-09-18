"""
RAG Structure-Aware Chunker
Partitions parsed document sections into size-bounded chunks while strictly preserving
exact line numbers, section titles, page citations, and SHA-256 hashes.
"""

from typing import Any

from src.rag.parser import ParsedSection


def chunk_sections(
    sections: list[ParsedSection],
    filename: str,
    file_hash: str,
    file_type: str,
    max_chunk_chars: int = 1500,
    overlap_chars: int = 150,
) -> list[dict[str, Any]]:
    """
    Transforms structured parsed sections into indexed vector chunks with complete metadata.
    """
    chunks: list[dict[str, Any]] = []

    for sec_idx, sec in enumerate(sections):
        content = sec.content.strip()
        if not content:
            continue

        # If section is within character bounds, keep it intact
        if len(content) <= max_chunk_chars:
            chunk_id = f"{file_hash[:12]}_{sec_idx}"
            chunks.append(
                {
                    "id": chunk_id,
                    "text": content,
                    "metadata": {
                        "filename": filename,
                        "file_type": file_type,
                        "sha256": file_hash,
                        "page": sec.page if sec.page is not None else -1,
                        "start_line": sec.start_line,
                        "end_line": sec.end_line,
                        "section": sec.section_name or "",
                        "chunk_type": sec.chunk_type,
                    },
                }
            )
        else:
            # Sub-split oversized section while calculating proportional line numbers
            lines = content.splitlines()
            total_lines = len(lines)
            chunk_line_step = max(10, int(total_lines * (max_chunk_chars / len(content))))

            for start_idx in range(0, total_lines, chunk_line_step):
                end_idx = min(start_idx + chunk_line_step, total_lines)
                sub_lines = lines[start_idx:end_idx]
                sub_content = "\n".join(sub_lines)

                rel_start_line = sec.start_line + start_idx
                rel_end_line = min(sec.start_line + end_idx - 1, sec.end_line)
                sub_id = f"{file_hash[:12]}_{sec_idx}_{start_idx}"

                chunks.append(
                    {
                        "id": sub_id,
                        "text": sub_content,
                        "metadata": {
                            "filename": filename,
                            "file_type": file_type,
                            "sha256": file_hash,
                            "page": sec.page if sec.page is not None else -1,
                            "start_line": rel_start_line,
                            "end_line": rel_end_line,
                            "section": f"{sec.section_name or ''} (part)",
                            "chunk_type": sec.chunk_type,
                        },
                    }
                )

    return chunks
