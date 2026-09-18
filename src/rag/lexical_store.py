"""
Local Lexical & BM25 Search Engine
Provides zero-cost, in-memory BM25 retrieval for exact identifiers, symbols,
class names, function names, error codes, and configuration keys.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any


def tokenize_code_and_text(text: str) -> list[str]:
    """
    Tokenizes text splitting on whitespace and punctuation,
    while preserving and decomposing camelCase and snake_case code tokens.
    """
    raw_tokens = re.findall(r"[a-zA-Z0-9_\-]+", text)
    tokens: list[str] = []

    for tok in raw_tokens:
        tok_lower = tok.lower()
        tokens.append(tok_lower)
        # Decompose snake_case
        if "_" in tok:
            tokens.extend([part.lower() for part in tok.split("_") if len(part) > 1])
        # Decompose camelCase / PascalCase
        camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", tok)
        if len(camel_parts) > 1:
            tokens.extend([p.lower() for p in camel_parts if len(p) > 1])

    return tokens


class LexicalBM25Store:
    def __init__(self, k1: float = 1.5, b: float = 0.75, persist_path: Path | None = None):
        self.k1 = k1
        self.b = b
        self.persist_path = persist_path
        self.documents: dict[str, dict[str, Any]] = {}  # id -> {id, text, metadata}
        self.doc_tokens: dict[str, list[str]] = {}  # id -> tokens
        self.doc_lens: dict[str, int] = {}
        self.avg_doc_len: float = 0.0
        self.doc_freqs: Counter[str] = Counter()  # term -> doc count
        self.total_docs: int = 0
        if self.persist_path and self.persist_path.exists():
            self._load()

    def _save(self) -> None:
        if not self.persist_path:
            return
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(self.documents, f)
        except Exception:
            pass

    def _load(self) -> None:
        if not self.persist_path or not self.persist_path.exists():
            return
        try:
            with open(self.persist_path, encoding="utf-8") as f:
                docs_dict = json.load(f)
            self.add_documents(list(docs_dict.values()), persist=False)
        except Exception:
            pass

    def add_documents(self, docs: list[dict[str, Any]], persist: bool = True) -> int:
        """
        Indexes chunks for BM25 lexical search.
        """
        for d in docs:
            doc_id = d["id"]
            text = d["text"]
            self.documents[doc_id] = d

            tokens = tokenize_code_and_text(text)
            self.doc_tokens[doc_id] = tokens
            self.doc_lens[doc_id] = len(tokens)

            # Update document frequencies
            unique_terms = set(tokens)
            for term in unique_terms:
                self.doc_freqs[term] += 1

        self.total_docs = len(self.documents)
        total_len = sum(self.doc_lens.values())
        self.avg_doc_len = total_len / self.total_docs if self.total_docs > 0 else 0.0
        if persist:
            self._save()
        return len(docs)

    def delete_by_filename(self, filename: str) -> int:
        """
        Removes all documents originating from the specified filename and recomputes stats.
        """
        to_delete = [
            doc_id
            for doc_id, doc in self.documents.items()
            if doc.get("metadata", {}).get("filename") == filename
        ]
        if not to_delete:
            return 0

        for doc_id in to_delete:
            tokens = self.doc_tokens.pop(doc_id, [])
            self.doc_lens.pop(doc_id, None)
            self.documents.pop(doc_id, None)
            for term in set(tokens):
                self.doc_freqs[term] -= 1
                if self.doc_freqs[term] <= 0:
                    del self.doc_freqs[term]

        self.total_docs = len(self.documents)
        total_len = sum(self.doc_lens.values())
        self.avg_doc_len = total_len / self.total_docs if self.total_docs > 0 else 0.0
        self._save()
        return len(to_delete)

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        filter_filename: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Scores all indexed documents using BM25 against the query tokens.
        """
        query_tokens = tokenize_code_and_text(query_text)
        if not query_tokens or self.total_docs == 0:
            return []

        scores: dict[str, float] = {}

        for doc_id, doc_terms in self.doc_tokens.items():
            doc_meta = self.documents[doc_id].get("metadata", {})
            if filter_filename and doc_meta.get("filename") != filter_filename:
                continue

            doc_len = self.doc_lens.get(doc_id, 1)
            term_counts = Counter(doc_terms)
            score = 0.0

            for q_term in query_tokens:
                if q_term not in term_counts:
                    continue

                tf = term_counts[q_term]
                df = self.doc_freqs.get(q_term, 0)
                # BM25 IDF
                idf = math.log(1.0 + (self.total_docs - df + 0.5) / (df + 0.5))

                # BM25 Term Frequency weighting
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                score += idf * (numerator / denominator)

            if score > 0.0:
                scores[doc_id] = score

        if not scores:
            return []

        # Sort descending by score
        sorted_doc_ids = sorted(scores.keys(), key=lambda d: scores[d], reverse=True)[:top_k]
        max_score = max(scores.values()) if scores else 1.0

        results: list[dict[str, Any]] = []
        for doc_id in sorted_doc_ids:
            doc = self.documents[doc_id]
            meta = doc.get("metadata", {})
            normalized_score = round(min(1.0, scores[doc_id] / (max_score + 1e-5)), 4)

            results.append(
                {
                    "id": doc_id,
                    "content": doc["text"],
                    "metadata": meta,
                    "score": normalized_score,
                    "raw_bm25_score": round(scores[doc_id], 4),
                    "citation": f"{meta.get('filename', 'unknown')}:L{meta.get('start_line', '?')}-{meta.get('end_line', '?')}",
                    "source_type": "lexical_bm25",
                }
            )

        return results

    def count(self) -> int:
        return self.total_docs


_bm25_instance: LexicalBM25Store | None = None


def get_lexical_store() -> LexicalBM25Store:
    global _bm25_instance
    if _bm25_instance is None:
        from src.config import get_settings

        settings = get_settings()
        persist_path = settings.VECTOR_DB_PATH / "bm25_index.json"
        _bm25_instance = LexicalBM25Store(persist_path=persist_path)
    return _bm25_instance

