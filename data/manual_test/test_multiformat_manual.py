"""
SentinelForge Multi-Format Manual Test Harness
Validates parsing, ingestion, indexing, and adaptive retrieval across:
1. Markdown (.md)
2. Plain Text (.txt)
3. JSON (.json)
4. Python (.py)
5. JavaScript (.js)
6. TypeScript (.ts)

Runs on the UNCHANGED existing pipeline using public MCP tools and RAG APIs.
Outputs true execution results without mocking, hardcoding, or fabricated scores.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.mcp_server.tools.ingestion import ingest_content_tool  # noqa: E402
from src.mcp_server.tools.retrieval import retrieve_context_tool  # noqa: E402
from src.rag.parser import parse_document  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
CASES_FILE = BASE_DIR / "expected" / "multiformat_cases.json"
GENERATED_DIR = BASE_DIR / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = GENERATED_DIR / "multiformat_results.json"


def log_header(title: str):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def log_section(title: str):
    print(f"\n--- {title} ---")


def run_parsing_verification() -> list[dict[str, Any]]:
    """Directly verifies format-specific parser behavior and structural segmentation."""
    log_header("STEP 1: MULTI-FORMAT PARSER STRUCTURAL VALIDATION")

    test_files = [
        ("Markdown (.md)", BASE_DIR / "code_repo" / "docs" / "api_specification.md"),
        ("Plain Text (.txt)", BASE_DIR / "operational_guide.txt"),
        ("JSON (.json)", BASE_DIR / "code_repo" / "config" / "settings.json"),
        ("Python (.py)", BASE_DIR / "code_repo" / "app" / "auth.py"),
        ("JavaScript (.js)", BASE_DIR / "code_repo" / "web" / "auth_client.js"),
        ("TypeScript (.ts)", BASE_DIR / "code_repo" / "app" / "session_types.ts"),
    ]

    parsing_results = []
    for fmt_label, p in test_files:
        if not p.exists():
            print(f"[FAIL] Missing test file for {fmt_label}: {p}")
            parsing_results.append({"format": fmt_label, "status": "FILE_NOT_FOUND", "path": str(p)})
            continue

        raw_bytes = p.read_bytes()
        t0 = time.perf_counter()
        sections = parse_document(p.name, content_bytes=raw_bytes)
        dt_ms = round((time.perf_counter() - t0) * 1000, 3)

        chunk_types = [s.chunk_type for s in sections]
        line_ranges = [(s.start_line, s.end_line) for s in sections]
        section_names = [s.section_name for s in sections if s.section_name]

        print(f"\n[FORMAT: {fmt_label}] -> {p.name} ({len(raw_bytes)} bytes)")
        print(f"  Sections Parsed: {len(sections)} in {dt_ms}ms")
        print(f"  Chunk Types:     {set(chunk_types)}")
        print(f"  Line Ranges:     {line_ranges[:4]}")
        print(f"  Sample Headings: {section_names[:3]}")

        is_ok = len(sections) > 0 and all(s.end_line >= s.start_line for s in sections)
        status = "PASS" if is_ok else "FAIL"
        parsing_results.append({
            "format": fmt_label,
            "filename": p.name,
            "sections_count": len(sections),
            "chunk_types": sorted(set(chunk_types)),
            "duration_ms": dt_ms,
            "status": status,
        })

    return parsing_results


def run_ingestion_phase() -> list[dict[str, Any]]:
    """Ingests multi-format documents into the live tri-store index."""
    log_header("STEP 2: MULTI-FORMAT TRI-STORE INGESTION")

    files_to_ingest = [
        ("docs/api_specification.md", BASE_DIR / "code_repo" / "docs" / "api_specification.md"),
        ("README.md", BASE_DIR / "code_repo" / "README.md"),
        ("operational_guide.txt", BASE_DIR / "operational_guide.txt"),
        ("security_doc.txt", BASE_DIR / "security_doc.txt"),
        ("config/settings.json", BASE_DIR / "code_repo" / "config" / "settings.json"),
        ("app/auth.py", BASE_DIR / "code_repo" / "app" / "auth.py"),
        ("app/database.py", BASE_DIR / "code_repo" / "app" / "database.py"),
        ("app/cache.py", BASE_DIR / "code_repo" / "app" / "cache.py"),
        ("app/main.py", BASE_DIR / "code_repo" / "app" / "main.py"),
        ("web/auth_client.js", BASE_DIR / "code_repo" / "web" / "auth_client.js"),
        ("app/session_types.ts", BASE_DIR / "code_repo" / "app" / "session_types.ts"),
    ]

    ingest_manifest = []
    for rel_name, p in files_to_ingest:
        if not p.exists():
            print(f"  [WARN] Skipping non-existent file: {p}")
            continue

        t0 = time.perf_counter()
        res = ingest_content_tool(filename=rel_name, file_path=str(p))
        dt_ms = round((time.perf_counter() - t0) * 1000, 2)
        res["duration_ms"] = dt_ms
        res["filename"] = rel_name
        ingest_manifest.append(res)

        print(
            f"  -> Ingested: {rel_name:<30} | Chunks: {res.get('chunk_count', 0):<3} | "
            f"Graph Nodes: {res.get('graph_nodes_count', 0):<2} | "
            f"Edges: {res.get('graph_edges_count', 0):<2} | "
            f"Status: {res.get('status')} ({dt_ms}ms)"
        )

    return ingest_manifest


def run_retrieval_cases() -> dict[str, Any]:
    """Executes multi-format retrieval test cases against the live adaptive router."""
    log_header("STEP 3: MULTI-FORMAT ADAPTIVE RETRIEVAL EVALUATION")

    if not CASES_FILE.exists():
        print(f"[ERROR] Cases file not found at {CASES_FILE}")
        sys.exit(1)

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    print(f"Executing {len(cases)} test cases across 6 document formats...\n")

    results_summary = []
    pass_count = 0
    fail_count = 0

    for idx, case in enumerate(cases, start=1):
        cid = case["id"]
        fmt = case.get("format", "Unknown")
        query = case["query"]
        exp_mode = case["expected_retrieval_mode"]
        exp_sources = case["expected_sources"]
        exp_tokens = case.get("expected_content_tokens", [])
        reason = case["reason"]

        log_section(f"Case {idx:02d}/{len(cases)}: [{fmt}] {cid}")
        print(f"Query:           \"{query}\"")
        print(f"Expected Mode:   {exp_mode}")
        print(f"Expected Source: {exp_sources}")
        print(f"Expected Tokens: {exp_tokens}")
        print(f"Rationale:       {reason}")

        t0 = time.perf_counter()
        resp = retrieve_context_tool(query=query, top_k=5)
        dt_ms = round((time.perf_counter() - t0) * 1000, 2)

        plan = resp.get("retrieval_plan", {})
        intent = plan.get("intent", "unknown")
        strategies = plan.get("selected_strategies", [])
        confidence = plan.get("confidence", 0.0)
        retrieved_items = resp.get("results", [])

        print(f"\nRouter Output:   Intent='{intent}' | Strategies={strategies} | Confidence={confidence}")
        print(f"Latency:         {dt_ms}ms | Retrieved Chunks: {len(retrieved_items)}")

        # Collect citations and full content
        retrieved_citations = [item.get("citation", "") for item in retrieved_items]
        combined_content = " ".join(item.get("content", "") for item in retrieved_items)

        # 1. Check source matching
        source_hit = any(
            any(exp in c for exp in exp_sources)
            for c in retrieved_citations
        )

        # 2. Check token/evidence presence
        token_hits = [tok for tok in exp_tokens if tok.lower() in combined_content.lower()]
        token_hit_ratio = len(token_hits) / max(1, len(exp_tokens))
        evidence_hit = token_hit_ratio >= 0.50 if exp_tokens else True

        # Determine overall case result
        case_passed = source_hit and evidence_hit
        status = "PASS" if case_passed else "FAIL"

        if case_passed:
            pass_count += 1
            print(f"Result:          [{status}] Source Matched: True | Token Overlap: {len(token_hits)}/{len(exp_tokens)}")
        else:
            fail_count += 1
            print(f"Result:          [{status}] Source Matched: {source_hit} | Token Overlap: {len(token_hits)}/{len(exp_tokens)}")

        if retrieved_items:
            top_item = retrieved_items[0]
            top_content_snippet = " ".join(top_item.get("content", "").split())[:120]
            print(f"Top Citation:    {top_item.get('citation')}")
            print(f"Top Score:       {top_item.get('score')}")
            print(f"Top Snippet:     \"{top_content_snippet}...\"")

        results_summary.append({
            "id": cid,
            "format": fmt,
            "query": query,
            "expected_mode": exp_mode,
            "router_intent": intent,
            "selected_strategies": strategies,
            "confidence": confidence,
            "source_matched": source_hit,
            "token_matched_count": len(token_hits),
            "expected_tokens_count": len(exp_tokens),
            "evidence_matched": evidence_hit,
            "status": status,
            "latency_ms": dt_ms,
            "top_citation": retrieved_items[0].get("citation") if retrieved_items else None,
            "top_score": retrieved_items[0].get("score") if retrieved_items else 0.0,
        })

    total = len(cases)
    pass_pct = round((pass_count / max(1, total)) * 100, 1)

    log_header("MULTI-FORMAT EVALUATION SUMMARY")
    print(f"Total Cases:  {total}")
    print(f"PASSED:       {pass_count} ({pass_pct}%)")
    print(f"FAILED:       {fail_count}")

    # Format breakdown
    formats = sorted({c["format"] for c in cases})
    print("\nFormat Breakdown:")
    for fmt in formats:
        fmt_cases = [r for r in results_summary if r["format"] == fmt]
        fmt_pass = sum(1 for r in fmt_cases if r["status"] == "PASS")
        print(f"  - {fmt:<20}: {fmt_pass}/{len(fmt_cases)} passed")

    return {
        "total_cases": total,
        "passed": pass_count,
        "failed": fail_count,
        "pass_rate_pct": pass_pct,
        "results": results_summary,
    }


def main():
    start_time = time.time()
    parsing_res = run_parsing_verification()
    ingest_res = run_ingestion_phase()
    retrieval_res = run_retrieval_cases()
    total_time = round(time.time() - start_time, 2)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_duration_sec": total_time,
        "parsing_validation": parsing_res,
        "ingestion_manifest": ingest_res,
        "retrieval_summary": retrieval_res,
    }

    RESULTS_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nFull execution results persisted to: {RESULTS_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
