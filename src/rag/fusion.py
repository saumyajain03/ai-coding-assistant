"""
Result Fusion and Deduplication Engine
Implements Reciprocal Rank Fusion (RRF) to blend Vector, Lexical (BM25),
and Graph retrieval results while removing duplicate content and preserving citations.
"""

from hashlib import sha256
from typing import Any


def fuse_and_deduplicate(
    ranked_lists: list[list[dict[str, Any]]],
    top_k: int = 5,
    rrf_k: int = 60,
) -> list[dict[str, Any]]:
    """
    Blends multiple ranked retrieval lists using Reciprocal Rank Fusion (RRF).
    Deduplicates identical chunks using content hashing.

    Args:
        ranked_lists: List of ranked result lists (e.g. [vector_results, bm25_results, graph_results]).
        top_k: Number of final fused results to return.
        rrf_k: Smoothing constant for RRF (default 60).

    Returns:
        Deduplicated, re-ranked list of cited evidence items.
    """
    # Key: content_hash -> {item_dict, rrf_score, source_types}
    fused_map: dict[str, dict[str, Any]] = {}

    for r_list in ranked_lists:
        for rank, item in enumerate(r_list, start=1):
            content = item.get("content", "").strip()
            if not content:
                continue

            content_hash = sha256(content.encode("utf-8")).hexdigest()
            rrf_score = 1.0 / (rrf_k + rank)
            source_type = item.get("source_type", "vector")

            if content_hash not in fused_map:
                fused_map[content_hash] = {
                    "item": item,
                    "rrf_score": rrf_score,
                    "sources": {source_type},
                    "best_score": item.get("score", 0.0),
                }
            else:
                entry = fused_map[content_hash]
                entry["rrf_score"] += rrf_score
                entry["sources"].add(source_type)
                if item.get("score", 0.0) > entry["best_score"]:
                    entry["best_score"] = item.get("score", 0.0)
                    entry["item"] = item  # Use item with best metadata

    if not fused_map:
        return []

    # Sort descending by fused RRF score
    sorted_entries = sorted(fused_map.values(), key=lambda e: e["rrf_score"], reverse=True)[:top_k]

    max_rrf = max(e["rrf_score"] for e in sorted_entries) if sorted_entries else 1.0

    final_results: list[dict[str, Any]] = []
    for entry in sorted_entries:
        item = entry["item"]
        normalized_fusion_score = round(min(1.0, entry["rrf_score"] / (max_rrf + 1e-5)), 4)
        item["score"] = normalized_fusion_score
        item["raw_score"] = round(entry["best_score"], 4)
        item["fusion_sources"] = sorted(entry["sources"])
        final_results.append(item)

    return final_results
