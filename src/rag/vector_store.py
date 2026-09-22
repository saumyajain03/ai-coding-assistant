"""
Local Privacy-First Vector Store
Integrates ChromaDB in-process vector store with metadata preservation,
content deduplication, incremental re-indexing, and clean deletion.
"""

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import get_settings


class LocalVectorStore:
    def __init__(self, persist_dir: Path | None = None):
        settings = get_settings()
        db_path = persist_dir or settings.VECTOR_DB_PATH
        db_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(db_path.resolve()),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="sentinelforge_knowledge",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """
        Adds a list of document chunks into ChromaDB.
        Each chunk dict must have: id, text, metadata.
        """
        if not chunks:
            return 0

        ids = [c["id"] for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        return len(chunks)

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Queries the vector store and returns sorted citations with scores.
        """
        if self.count() == 0 or not query_text.strip():
            return []

        results = self.collection.query(
            query_texts=[query_text],
            n_results=min(top_k, self.count()),
            where=filter_metadata,
        )

        output: list[dict[str, Any]] = []
        if results and results["documents"] and results["documents"][0]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
            distances = results["distances"][0] if results["distances"] else [0.0] * len(docs)

            for doc, meta, dist in zip(docs, metas, distances, strict=False):
                # Cosine distance to similarity score
                similarity = round(1.0 - float(dist), 4)
                output.append(
                    {
                        "content": doc,
                        "metadata": meta,
                        "score": similarity,
                        "citation": f"{meta.get('filename', 'unknown')}:{meta.get('start_line', '?')}-{meta.get('end_line', '?')}",
                    }
                )

        return output

    def delete_by_filename(self, filename: str) -> int:
        """
        Deletes all chunks belonging to the specified filename.
        """
        existing = self.collection.get(where={"filename": filename})
        if existing and existing["ids"]:
            count = len(existing["ids"])
            self.collection.delete(ids=existing["ids"])
            return count
        return 0

    def reset(self) -> None:
        """
        Purges all chunks by deleting and recreating the collection.
        """
        try:
            self.client.delete_collection("sentinelforge_knowledge")
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name="sentinelforge_knowledge",
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self.collection.count()

    def get_indexed_files(self) -> list[dict[str, Any]]:
        """
        Returns summary of all uniquely indexed files and their chunk counts.
        """
        all_data = self.collection.get(include=["metadatas"])
        file_map: dict[str, dict[str, Any]] = {}

        if all_data and all_data["metadatas"]:
            for meta in all_data["metadatas"]:
                fname = meta.get("filename", "unknown")
                if fname not in file_map:
                    file_map[fname] = {
                        "filename": fname,
                        "file_type": meta.get("file_type", ""),
                        "sha256": meta.get("sha256", ""),
                        "chunk_count": 0,
                    }
                file_map[fname]["chunk_count"] += 1

        return list(file_map.values())


# Global singleton instance
_vector_store_instance: LocalVectorStore | None = None


def get_vector_store() -> LocalVectorStore:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = LocalVectorStore()
    return _vector_store_instance
