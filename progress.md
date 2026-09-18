# SentinelForge Development Progress & Decision Log (`progress.md`)

This log tracks every phase of Project SentinelForge: files created, architectural rationale, modifications made, and verified status.

---

## Phase Summary Table

| Phase | Title | Status | Automated Tests | Notes / Highlights |
|---|---|---|---|---|
| **Phase 0** | Foundation, Config & Single-Command Gate | **COMPLETED** [x] | 5 Tests Passed | Pydantic Settings, path jail, Makefile, deterministic deps |
| **Phase 1** | Model Context Protocol (MCP) Server | **COMPLETED** [x] | 8 Tests Passed (13 Total) | Official MCP SDK 2.x, 6 tools (+2 bonus), resource, prompt |
| **Phase 2** | Privacy-First Local RAG, GraphRAG & Lazy Multimodal PDF | **COMPLETED** [x] | 39 Tests Passed (52 Total) | Canonical pages, lazy OCR, Visual RAG, tri-store, multi-signal router |
| **Phase 3** | Defensive Sandbox Engine | Pending [ ] | Targeted: 6+ Tests | Process isolation, setrlimit, dual runtime (Py+Node) |
| **Phase 4** | 7-Stage Autonomous Agent Core | Pending [ ] | Targeted: 4+ Tests | 7-stage orchestrator, AST diffs, zero-cost LLM connector |
| **Phase 5** | Web App & FastAPI Gateway | Pending [ ] | Targeted: 4+ Tests | OpenAPI docs, diff viewer UI, ephemeral bootstrap |
| **Phase 6** | Adversarial Hardening & Auditing | Pending [ ] | Targeted: 6+ Tests | 15+ injection attack suite, traversal jail tests |
| **Phase 7** | Evaluation & Benchmark Suite | Pending [ ] | Targeted: 8+ Qs Eval | Precision@k, Recall@k, MRR retrieval metrics |
| **Phase 8** | Zero-Cost Deployment & CI/CD | Pending [ ] | Full Pipeline | Docker, render.yaml, GitHub Actions CI/CD |
| **Phase 9** | Documentation & Video Script | Pending [ ] | Ready | AI_USAGE.md, README.md, 8-12 min video script |

---

## Phase 0 Log: Foundation & Configuration
- **Files Created**:
  - `pyproject.toml` & `requirements.txt`: Locked dependencies (`mcp`, `fastapi`, `chromadb`, `sentence-transformers`, `pytest`, `ruff`).
  - `.env.example` & `.env`: Dynamic configuration template ensuring zero hardcoded secrets.
  - `src/config.py`: Pydantic Settings implementation. Auto-creates runtime directories and enforces the `is_path_in_workspace()` path jail validator.
  - `scripts/run_all_checks.sh`: Single executable script fulfilling Core Gate 5 (runs linter and tests).
  - `Makefile`: Ergonomic targets (`make test`, `make lint`, `make dev`, `make check`).
  - `tests/test_config.py` & `tests/conftest.py`: Verified environment parsing and path traversal prevention (`../../etc/passwd` rejection).
- **Design Decisions**:
  - Selected Python 3.11 virtual environment for maximum compatibility with official `mcp 2.x`, PyTorch CPU, and ChromaDB.
  - Used `pydantic-settings` to guarantee environment variable type safety with fallback defaults.

---

## Phase 1 Log: Model Context Protocol (MCP) Server
- **Files Created**:
  - `src/mcp_server/server.py`: Official MCP SDK 2.x server initialization with typed tool registrations and client invocation helper `invoke_mcp_tool()`.
  - `src/mcp_server/tools/ingestion.py`: `ingest_content` tool with file extension validation, SHA-256 duplicate checking, and chunk indexing.
  - `src/mcp_server/tools/retrieval.py`: `retrieve_context` tool with semantic scoring, line citations, and `<untrusted_document_context>` defensive wrapping.
  - `src/mcp_server/tools/inspection.py`: `inspect_repository` tool with realpath boundary check to block directory traversal and dangerous symlinks.
  - `src/mcp_server/tools/patch.py`: `propose_patch` tool generating unified diffs and AST syntax validation without writing to disk.
  - `src/mcp_server/tools/sandbox.py`: `run_sandbox_command` tool invoking the sandbox runner with timeouts and limits.
  - `src/mcp_server/tools/system.py`: `get_system_telemetry` tool exposing platform status, vector count, and audit log (*Bonus 1: 6th Tool*).
  - `src/mcp_server/resources/workspace_status.py`: Exposes `sentinelforge://system/status` MCP resource.
  - `src/mcp_server/prompts/code_review.py`: Exposes `code_review_and_test` MCP prompt for the 7-stage loop.
  - `src/sandbox/security.py`: Command allowlist, path traversal checker, and regex secret redactor.
  - `src/sandbox/runner.py`: Subprocess isolation with `resource.setrlimit` (time, memory, nproc, output limit).
  - `src/sandbox/audit.py`: Structured in-memory and on-disk audit logger.
  - `tests/test_mcp_server.py`: 8 automated unit/integration tests verifying all 6 tools, resource, prompt, and sandbox execution.
- **Design Decisions & Changes Made**:
  - Discovered that `mcp 2.2.0` deprecated `FastMCP` in favor of `from mcp.server.mcpserver import MCPServer`. Adapted codebase immediately to the modern 2.x architecture.
  - Fixed regex substitution in `sanitize_sandbox_output` to handle token formats (ghp, sk, gsk) without triggering invalid group reference errors.
  - Kept disk files untouched on patch proposal to strictly adhere to the Human-In-The-Loop (HITL) requirement.

---

## Phase 2 Log: Privacy-First Local RAG Pipeline
- **Status**: **COMPLETED** [x] (9 tests in `test_rag_pipeline.py`, 22 tests total passing)
- **Files Created / Enhanced**:
  - `src/rag/parser.py`: Enhanced with AST-aware Python parsing (`ast.FunctionDef`, `ast.ClassDef`), JS/TS regex boundary parser, Markdown header parser (`#`, `##`, `###`), JSON structural parser, and PDF page-by-page extraction (`pypdf`).
  - `src/rag/chunker.py`: Structure-aware chunking engine that partitions parsed sections while preserving exact start/end line numbers, page numbers, and SHA-256 hashes.
  - `src/rag/guardrails.py`: Comprehensive anti-injection engine. Scans for 8+ threat patterns (`DIRECT_INSTRUCTION_OVERRIDE`, `DELIMITER_BREAKOUT_ATTEMPT`, `SYSTEM_PROMPT_EMULATION`, `PRIVILEGE_ESCALATION`), defuses malicious commands, escapes delimiter tags, and records security audit events.
  - `src/rag/embeddings.py`: Local `SentenceTransformers` CPU wrapper with `OFFLINE_MODE` enforcement to ensure air-gapped zero-network execution.
  - `src/rag/indexer.py`: Centralized `RAGIndexer` orchestrating file ingestion, SHA-256 deduplication, incremental replacement, and deletion.
  - `src/mcp_server/tools/ingestion.py`: Refactored to delegate directly to `RAGIndexer`.
  - `src/mcp_server/tools/retrieval.py`: Refactored to wrap all citations inside `sanitize_content_for_context()`.
  - `tests/test_rag_pipeline.py`: 9 new automated tests covering PDF, Python AST, JS/TS, Markdown, JSON, deduplication, incremental update, deletion, anti-injection, and invalid file rejection.
- **Design Decisions**:
  - Used Python's standard `ast` module for Python parsing so function and class boundaries are mathematically exact down to line numbers.
  - Implemented proactive defensive sanitization in `guardrails.py`: instead of just flagging an injection, it neutralizes closing delimiter tags (`&lt;/untrusted_document_context&gt;`) so attackers cannot break out into the LLM's system prompt context.
  - Achieved **22 total automated tests** passing in 1.4 seconds, satisfying Core Gate 5 ($\ge 12$ tests) and capturing the **Bonus Objective (+2 pts)** for $> 20$ automated tests.

---

## Phase 2 Extension Log: Adaptive Local RAG with GraphRAG & Lexical BM25
- **Status**: **COMPLETED** [x] (10 additional tests in `test_adaptive_rag.py`, **32 total tests passing**)
- **Files Created / Enhanced**:
  - `src/rag/knowledge_graph.py`: SQLite-backed persistent graph database (`./data/chroma/knowledge_graph.db`). Defines `GraphNode` and `GraphEdge` schemas, atomic edge insertions, BFS multi-hop traversal with max-depth pruning, and line-level provenance tracking.
  - `src/rag/graph_builder.py`: Deterministic entity and structural relationship extractor:
    - **Python AST**: `ast.ClassDef`, `ast.FunctionDef`, `ast.Call`, `ast.Import`, `ast.ImportFrom` -> `DEFINES`, `CALLS`, `INHERITS`, `IMPORTS`.
    - **JavaScript / TypeScript**: Classes, interfaces, type aliases, function declarations, imports -> `DEFINES`, `INHERITS`, `IMPORTS`.
    - **Markdown**: Heading hierarchies, relative file/code links -> `DEFINES`, `REFERENCES`.
    - **JSON**: Configuration keys, object structures -> `CONFIGURES`.
    - **PDF**: Page nodes with text excerpts and bounding line numbers.
    - Strictly avoids hallucinating relations from text similarity; only verified AST/syntax structures create edges.
  - `src/rag/lexical_store.py`: In-memory and disk-persisted (`./data/chroma/bm25_index.json`) BM25 search engine with camelCase and snake_case decomposing tokenizer.
  - `src/rag/fusion.py`: Reciprocal Rank Fusion (RRF with $k=60$) blending vector similarity, BM25 scores, and graph traversal hops, with SHA-256 chunk deduplication.
  - `src/rag/router.py`:
    - Intent Classifier (`classify_query_intent`): Categorizes queries into `SEMANTIC_LOOKUP`, `EXACT_SYMBOL`, `RELATIONSHIP_DEPENDENCY`, `IMPACT_ANALYSIS`, `MULTI_HOP_ARCHITECTURE`, and `COMPLEX_DEBUGGING`.
    - Inspectable `RetrievalPlan`: Explicitly declares selected strategies, hop depth, and target entities.
    - Configurable Multi-Signal Sufficiency Evaluator (`evaluate_evidence_sufficiency`): Evaluates result count, similarity baseline, score margin between rank-1 and rank-2, exact symbol presence, and query intent rather than relying on a hard-coded vector confidence threshold.
    - Conditional Escalation: Escalates to Lexical BM25 or 1-hop Graph expansion only when initial retrieval evidence is insufficient.
  - `src/rag/indexer.py`: Synchronously indexes documents across all three stores (ChromaDB, BM25, SQLite Knowledge Graph) and deletes atomically across all three.
  - `src/mcp_server/tools/retrieval.py`: Updated to invoke `execute_adaptive_retrieval()`, providing transparent execution traces and retrieval plans.
  - `tests/test_adaptive_rag.py`: 10 comprehensive tests verifying graph extraction, TS interfaces, multi-hop BFS, vector-only bypass of GraphRAG, lexical exact-symbol routing, dependency graph queries, impact analysis, RRF fusion, and multi-category comparative evaluation.
- **Design Decisions**:
  - Maintained complete zero-cost, local-first footprint using SQLite for graph storage and local BM25 without external services.
  - Enforced strict conditionality: GraphRAG is completely bypassed for semantic queries (0 hops), preserving low latency and high precision.
  - All 7 document parsers remain completely separate while normalizing cleanly into `ParsedSection`.
  - **Total automated test count now stands at 32 tests passing** in under 1.7 seconds!

---

## Phase 2 Extension Log (Part 2): Resource-Efficient Lazy PDF Processing & Multimodal Adaptive RAG
- **Status**: **COMPLETED** [x] (20 additional tests in `test_pdf_multimodal.py`, **52 total tests passing in 1.94s**)
- **Core Operating Principle**:
  > SentinelForge uses the least expensive retrieval modality capable of answering the query and escalates to OCR, Visual RAG, or GraphRAG only when additional evidence is required.
- **Files Created / Enhanced**:
  - `src/rag/canonical_page.py`: First-class `CanonicalPageRecord` schema and SQLite-backed `CanonicalPageStore` (`./data/chroma/canonical_pages.db`). Preserves 1-indexed `page_number`, 0-indexed `page_index`, `doc_id`, `sha256_hash`, `start_line`, `end_line`, `page_type`, `available_modalities`, `ocr_status`, `visual_status`, `image_count`, `image_area_ratio`, `char_count`, and `word_count`.
  - `src/rag/pdf_classifier.py`: Deterministic, lightweight PDF page classifier using inexpensive heuristics (character count, word count, image count, and image area ratio) to classify pages into `TEXT_PAGE`, `SCANNED_PAGE`, `MIXED_PAGE`, `VISUAL_HEAVY_PAGE`, or `EMPTY_OR_UNREADABLE_PAGE` without expensive ML overhead.
  - `src/rag/ocr_engine.py`: `LazyOCREngine` with per-page concurrency locking (`threading.Lock`), disk caching (`./data/scratch/ocr_cache/`), prompt-injection sanitization, and graceful degradation when the system Tesseract binary is absent.
  - `src/rag/visual_engine.py`: `LazyVisualRAGEngine` with per-page locking, disk caching (`./data/scratch/visual_cache/`), visual region detection (bounding boxes, diagrams, flowcharts, tables), and genuine visual representation interface. Kept disabled by default (`ENABLE_VISUAL_RAG=False`) to respect Render Free 512MB RAM constraints without fabricating fake embeddings.
  - `src/rag/parser.py`: Updated `_parse_pdf()` with Render-friendly bounds (`MAX_PDF_SIZE_MB=20`, `MAX_PDF_PAGES=100`), page classification, canonical record persistence, and normalized `ParsedSection` output.
  - `src/rag/router.py`:
    - Extended `RetrievalPlan` with typed multi-modal attributes: `query_type` (`semantic_text`, `exact_symbol`, `scanned_text`, `visual_question`, `dependency_question`, `impact_analysis`, `complex_debugging`), `modalities`, `use_vector`, `use_bm25`, `use_graph`, `use_ocr`, `use_visual`, `fallback_strategy`, and `confidence`.
    - Multi-signal routing: evaluates query intent + target entities + explicit page citations (e.g. "Page 4") + canonical page metadata in SQLite + repository modality availability + evidence sufficiency.
    - Deterministic fallback: falls back safely to text Vector + BM25 when confidence or modality is insufficient or unavailable.
  - `src/rag/indexer.py`: Integrates `CanonicalPageStore.delete_by_filename()` during incremental re-indexing and deletion.
  - `src/mcp_server/tools/system.py`: Telemetry exposes active multimodal capabilities (`ocr_enabled`, `ocr_available`, `visual_rag_enabled`, `visual_rag_active`, `canonical_pages` stats, and resource bounds).
  - `tests/test_pdf_multimodal.py`: 20 new tests covering classification, canonical persistence, lazy execution, caching, graceful degradation, adaptive routing, prompt injection sanitization, oversized file/page rejections, and comparative multimodal evaluation.
- **Design Decisions**:
  - **Lazy Processing vs. Adaptive Retrieval**:
    - *Lazy Processing*: Controls WHEN expensive representations (OCR text, visual regions) are computed (deferred until a scanned/visual page is queried).
    - *Adaptive Retrieval*: Controls WHICH modality is searched (vector, BM25, graph, OCR, visual) based on query requirements.
  - **Render Deployment Safety**: Enforces strict memory caps and feature flags (`ENABLE_VISUAL_RAG=false` by default) so the entire pipeline runs smoothly within Render Free's 512MB RAM ceiling.
  - **Total automated test count now stands at 52 tests passing** cleanly in under 2 seconds!

---

## Phase 3 Log: Defensive Sandbox Engine (Next)
- **Goal**: Implement isolated execution for Python and Node.js/TypeScript workflows, enforce process limits (`RLIMIT_AS`, `RLIMIT_NPROC`, buffer caps), and test adversarial containment (fork bombs, memory exhaustion, traversal attacks).


