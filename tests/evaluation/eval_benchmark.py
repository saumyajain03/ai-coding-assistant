"""
In-Repository Retrieval Evaluation Suite (Task 7.3)
Computes Precision@k, Recall@k, Mean Reciprocal Rank (MRR), and Latency
against tests/evaluation/test_queries.json.
Asserts in pytest that:
- MRR >= 0.75
- Recall@3 >= 0.80
- p50 Latency < 1000ms
"""

import json
import time
from pathlib import Path
from typing import Any

from src.mcp_server.tools.retrieval import retrieve_context_tool
from src.rag.indexer import get_rag_indexer

# Benchmark Corpus: Ground-truth files providing canonical reference documentation and code
BENCHMARK_CORPUS = {
    "auth_service.py": (
        '"""Authentication and JWT Token Service."""\n'
        "import time\n"
        "import jwt\n\n"
        'SECRET_KEY = "mock_auth_secret_for_tests"\n'
        'ALGORITHM = "RS256"\n'
        "TOKEN_EXPIRY_SECONDS = 3600\n\n"
        "def verify_jwt_token(token: str) -> dict:\n"
        '    """Verifies RSA256 signature and decodes user payload from JWT token."""\n'
        "    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n"
        '    if decoded.get("exp", 0) < time.time():\n'
        '        raise ValueError("Token expired")\n'
        "    return decoded\n\n"
        "def revoke_token(token_id: str, redis_client) -> bool:\n"
        '    """Adds token to Redis revocation blocklist with remaining TTL."""\n'
        '    redis_client.setex(f"revoked:{token_id}", TOKEN_EXPIRY_SECONDS, "1")\n'
        "    return True\n"
    ),
    "payment_gateway.py": (
        '"""Payment Processing and Transaction Settlement Service."""\n\n'
        "DAILY_SETTLEMENT_LIMIT_INR = 100000.0\n"
        "REFUND_WINDOW_DAYS = 30\n\n"
        "def process_transaction(amount: float, customer_id: str) -> dict:\n"
        '    """Validates daily settlement threshold and processes payment capture."""\n'
        "    if amount > DAILY_SETTLEMENT_LIMIT_INR:\n"
        '        raise ValueError("Exceeds maximum daily settlement limit")\n'
        '    return {"status": "captured", "amount": amount, "customer_id": customer_id}\n\n'
        "def handle_payment_webhook(event_payload: dict, idempotency_key: str) -> bool:\n"
        '    """Handles asynchronous payment webhooks with strict idempotency key deduplication."""\n'
        "    if not idempotency_key:\n"
        "        return False\n"
        "    return True\n"
    ),
    "system_architecture.md": (
        "# SentinelForge Distributed Architecture\n\n"
        "## Microservices Breakdown\n"
        "The backend platform consists of FastAPI Gateway, MCP Server, and Local RAG subsystem.\n\n"
        "## Database Sharding\n"
        "User data is horizontally partitioned by user UUID hash mod 16.\n"
        "Read replicas handle 80% of analytical traffic.\n\n"
        "## Caching Strategy and Invalidation\n"
        "Redis cluster operates with LRU eviction and cache-aside invalidation.\n"
        "Cache invalidation occurs synchronously upon mutating write operations.\n"
    ),
    "security_policy.md": (
        "# SentinelForge Security Policy & Sandboxing Boundaries\n\n"
        "## RBAC and API Key Rotation\n"
        "API credentials must be rotated every 90 days.\n"
        "Access tiers strictly enforce read-only, mutating, and administrative privileges.\n\n"
        "## Network Security & TLS\n"
        "All ingress and egress traffic enforces TLS 1.3 with forward secrecy.\n\n"
        "## Sandbox Isolation Limits\n"
        "Sandbox execution processes are constrained by RLIMIT_AS (200MB memory ceiling),\n"
        "RLIMIT_NPROC (10 process ceiling for fork bomb prevention), and a 15-second hard timeout.\n"
    ),
}


def ensure_benchmark_corpus_indexed() -> None:
    """Seeds the ground-truth benchmark documents into the local RAG index."""
    indexer = get_rag_indexer()
    for filename, content in BENCHMARK_CORPUS.items():
        indexer.index_file(filename=filename, content_bytes=content.encode("utf-8"))


def run_retrieval_benchmark(top_k: int = 5) -> dict[str, Any]:
    """
    Executes all queries from test_queries.json, computing MRR, Recall@3, Precision@3,
    and query latency percentiles.
    """
    ensure_benchmark_corpus_indexed()

    queries_path = Path(__file__).parent / "test_queries.json"
    with open(queries_path, encoding="utf-8") as f:
        queries = json.load(f)

    results_per_query: list[dict[str, Any]] = []
    mrr_values: list[float] = []
    recall3_values: list[float] = []
    precision3_values: list[float] = []
    latencies_ms: list[float] = []

    for q in queries:
        query_text = q["query"]
        ground_truth = q["ground_truth_file"]
        relevant_files = q.get("relevant_files", [ground_truth])

        t0 = time.perf_counter()
        retrieval_res = retrieve_context_tool(query=query_text, top_k=top_k)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        hits = retrieval_res.get("results", [])
        hit_files = [h["filename"] for h in hits]

        # Calculate rank of first relevant hit (1-indexed)
        rank = 0
        for idx, h_file in enumerate(hit_files, start=1):
            if h_file in relevant_files or h_file == ground_truth:
                rank = idx
                break

        mrr = 1.0 / rank if rank > 0 else 0.0
        recall_at_3 = 1.0 if (0 < rank <= 3) else 0.0
        top3_hits = hit_files[:3]
        relevant_in_top3 = sum(1 for f in top3_hits if f in relevant_files or f == ground_truth)
        precision_at_3 = relevant_in_top3 / max(len(top3_hits), 1)

        mrr_values.append(mrr)
        recall3_values.append(recall_at_3)
        precision3_values.append(precision_at_3)

        results_per_query.append({
            "query_id": q["query_id"],
            "query": query_text,
            "ground_truth": ground_truth,
            "retrieved_files": hit_files,
            "rank": rank,
            "mrr": round(mrr, 4),
            "recall_at_3": recall_at_3,
            "precision_at_3": round(precision_at_3, 4),
            "latency_ms": round(elapsed_ms, 2),
        })

    latencies_sorted = sorted(latencies_ms)
    p50_idx = int(len(latencies_sorted) * 0.50)
    p95_idx = min(int(len(latencies_sorted) * 0.95), len(latencies_sorted) - 1)

    mean_mrr = sum(mrr_values) / len(mrr_values) if mrr_values else 0.0
    mean_recall3 = sum(recall3_values) / len(recall3_values) if recall3_values else 0.0
    mean_prec3 = sum(precision3_values) / len(precision3_values) if precision3_values else 0.0

    return {
        "queries_evaluated": len(queries),
        "queries_with_results": sum(1 for r in results_per_query if r["retrieved_files"]),
        "mean_mrr": round(mean_mrr, 4),
        "mean_recall_at_3": round(mean_recall3, 4),
        "mean_precision_at_3": round(mean_prec3, 4),
        "latency_p50_ms": round(latencies_sorted[p50_idx], 2) if latencies_sorted else 0.0,
        "latency_p95_ms": round(latencies_sorted[p95_idx], 2) if latencies_sorted else 0.0,
        "results": results_per_query,
    }


# ==============================================================================
# Pytest Test Assertions for Task 7.3
# ==============================================================================
def test_benchmark_mrr_threshold():
    """Verify that Mean Reciprocal Rank (MRR) meets or exceeds the required 0.75 threshold."""
    metrics = run_retrieval_benchmark(top_k=5)
    assert metrics["mean_mrr"] >= 0.75, f"MRR {metrics['mean_mrr']} failed threshold >= 0.75"


def test_benchmark_recall_threshold():
    """Verify that Recall@3 meets or exceeds the required 0.80 threshold."""
    metrics = run_retrieval_benchmark(top_k=5)
    assert metrics["mean_recall_at_3"] >= 0.80, (
        f"Recall@3 {metrics['mean_recall_at_3']} failed threshold >= 0.80"
    )


def test_benchmark_all_queries_produce_results():
    """Verify all queries retrieve non-empty results."""
    metrics = run_retrieval_benchmark(top_k=5)
    assert metrics["queries_evaluated"] >= 8
    assert metrics["queries_with_results"] == metrics["queries_evaluated"]


def test_benchmark_latency_acceptable():
    """Verify that retrieval median query latency (p50) remains under 1000ms."""
    metrics = run_retrieval_benchmark(top_k=5)
    assert metrics["latency_p50_ms"] < 1000.0, (
        f"Latency p50 {metrics['latency_p50_ms']}ms exceeds 1000ms ceiling"
    )
