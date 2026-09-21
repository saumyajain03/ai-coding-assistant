#!/usr/bin/env python3
"""
CLI Evaluation Script: SentinelForge Local RAG Retrieval Benchmark
Runs evaluation queries against the local RAG engine and computes:
- Precision@k
- Recall@k
- Mean Reciprocal Rank (MRR)
- Latency (p50, p95)
"""

import sys
from pathlib import Path

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from tests.evaluation.eval_benchmark import run_retrieval_benchmark  # noqa: E402


def main() -> int:
    print("=" * 80)
    print("      SentinelForge Local RAG In-Repository Evaluation Benchmark      ")
    print("=" * 80)

    print("\n[1/3] Loading evaluation corpus and running queries...")
    benchmark_data = run_retrieval_benchmark(top_k=5)

    print("\n[2/3] Per-Query Retrieval Breakdown:")
    print("-" * 80)
    print(f"{'Query ID':<10} {'Rank':<6} {'MRR':<8} {'Recall@3':<10} {'Latency':<10} {'Ground Truth'}")
    print("-" * 80)

    for r in benchmark_data["results"]:
        rank_str = str(r["rank"]) if r["rank"] > 0 else "N/A"
        print(
            f"{r['query_id']:<10} {rank_str:<6} {r['mrr']:<8.2f} "
            f"{r['recall_at_3']:<10.2f} {r['latency_ms']:<8.1f}ms {r['ground_truth']}"
        )
        print(f"   Query: {r['query']}")
        print(f"   Top-3: {r['retrieved_files'][:3]}")
        print()

    print("=" * 80)
    print("                      Summary Evaluation Metrics                       ")
    print("=" * 80)
    mrr = benchmark_data["mean_mrr"]
    rec3 = benchmark_data["mean_recall_at_3"]
    prec3 = benchmark_data["mean_precision_at_3"]
    p50 = benchmark_data["latency_p50_ms"]
    p95 = benchmark_data["latency_p95_ms"]

    mrr_pass = mrr >= 0.75
    rec_pass = rec3 >= 0.80

    print(f"Queries Evaluated: {benchmark_data['queries_evaluated']}")
    print(f"Mean Reciprocal Rank (MRR): {mrr:.4f}  [{'PASS' if mrr_pass else 'FAIL'}] (Target: >= 0.75)")
    print(f"Recall@3:                   {rec3:.4f}  [{'PASS' if rec_pass else 'FAIL'}] (Target: >= 0.80)")
    print(f"Precision@3:                {prec3:.4f}")
    print(f"Latency p50:                {p50:.2f} ms")
    print(f"Latency p95:                {p95:.2f} ms")
    print("=" * 80)

    if mrr_pass and rec_pass:
        print("\nSUCCESS: All retrieval benchmark quality gates passed!\n")
        return 0
    else:
        print("\nFAILURE: One or more retrieval benchmark targets were not met.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
