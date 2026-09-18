"""
RAG Indexer Engine
Handles unified document indexing across:
1. Local Vector Store (ChromaDB)
2. In-Memory Lexical Store (BM25)
3. Local Knowledge Graph (SQLite)
Preserves content hashing, duplicate detection, incremental re-indexing, and clean deletion.
"""

from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import get_settings
from src.rag.canonical_page import get_canonical_page_store
from src.rag.chunker import chunk_sections
from src.rag.graph_builder import build_graph_for_document
from src.rag.knowledge_graph import get_knowledge_graph
from src.rag.lexical_store import get_lexical_store
from src.rag.parser import parse_document
from src.rag.vector_store import get_vector_store

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".json", ".py", ".js", ".ts"}


class IndexResult(BaseModel):
    document_id: str
    filename: str
    file_type: str
    chunk_count: int
    sha256_hash: str
    is_duplicate: bool
    status: str
    graph_nodes_count: int = 0
    graph_edges_count: int = 0


class RAGIndexer:
    def __init__(self):
        self.settings = get_settings()
        self.vector_store = get_vector_store()
        self.lexical_store = get_lexical_store()
        self.knowledge_graph = get_knowledge_graph()

    def index_file(
        self,
        filename: str,
        content_bytes: bytes | None = None,
        file_path: Path | None = None,
    ) -> IndexResult:
        """
        Indexes a file simultaneously into Vector Store, Lexical Index, and Knowledge Graph
        with SHA-256 deduplication and incremental replacement.
        """
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
            )

        if content_bytes is None and file_path:
            content_bytes = file_path.read_bytes()
        elif content_bytes is None:
            raise ValueError("Either content_bytes or file_path must be provided.")

        max_bytes = self.settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content_bytes) > max_bytes:
            raise ValueError(f"File size exceeds maximum limit of {max_bytes} bytes.")

        file_hash = sha256(content_bytes).hexdigest()

        # 1. Deduplication check: if file exists and hash is identical across stores, skip re-indexing
        indexed_files = self.vector_store.get_indexed_files()
        is_in_lexical = any(
            doc.get("metadata", {}).get("filename") == filename
            for doc in self.lexical_store.documents.values()
        )
        for existing in indexed_files:
            if existing["filename"] == filename and existing.get("sha256") == file_hash and is_in_lexical:
                return IndexResult(
                    document_id=f"doc_{file_hash[:12]}",
                    filename=filename,
                    file_type=ext,
                    chunk_count=existing["chunk_count"],
                    sha256_hash=file_hash,
                    is_duplicate=True,
                    status="already_indexed",
                    graph_nodes_count=0,
                    graph_edges_count=0,
                )

        # 2. Incremental re-indexing: remove prior chunks and graph edges for this filename
        self.vector_store.delete_by_filename(filename)
        self.lexical_store.delete_by_filename(filename)
        self.knowledge_graph.delete_by_filename(filename)
        get_canonical_page_store().delete_by_filename(filename)

        # 3. Parse and chunk
        sections = parse_document(
            filename=filename,
            content_bytes=content_bytes,
            file_path=file_path,
        )

        chunks = chunk_sections(
            sections=sections,
            filename=filename,
            file_hash=file_hash,
            file_type=ext,
            max_chunk_chars=self.settings.CHUNK_SIZE * 4,
            overlap_chars=self.settings.CHUNK_OVERLAP * 4,
        )

        # 4. Ingest into Vector Store (ChromaDB)
        added_count = self.vector_store.add_chunks(chunks)

        # 5. Ingest into Lexical Store (BM25)
        self.lexical_store.add_documents(chunks)

        # 6. Ingest into Knowledge Graph
        nodes, edges = build_graph_for_document(
            filename=filename,
            raw_content=content_bytes,
            file_hash=file_hash,
            sections=sections,
        )
        self.knowledge_graph.add_nodes_and_edges(nodes, edges)

        return IndexResult(
            document_id=f"doc_{file_hash[:12]}",
            filename=filename,
            file_type=ext,
            chunk_count=added_count,
            sha256_hash=file_hash,
            is_duplicate=False,
            status="indexed_successfully",
            graph_nodes_count=len(nodes),
            graph_edges_count=len(edges),
        )

    def delete_file(self, filename: str) -> int:
        """
        Deletes all chunks and graph entities associated with the filename across all stores.
        """
        v_count = self.vector_store.delete_by_filename(filename)
        self.lexical_store.delete_by_filename(filename)
        self.knowledge_graph.delete_by_filename(filename)
        get_canonical_page_store().delete_by_filename(filename)
        return v_count

    def get_indexed_summary(self) -> list[dict[str, Any]]:
        """
        Returns list of indexed documents with chunk counts and SHA-256 hashes.
        """
        return self.vector_store.get_indexed_files()


_indexer_instance: RAGIndexer | None = None


def get_rag_indexer() -> RAGIndexer:
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = RAGIndexer()
    return _indexer_instance
