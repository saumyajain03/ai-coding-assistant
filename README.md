# SentinelForge: Autonomous, Privacy-First Agentic Defense Platform

SentinelForge is a production-grade, zero-cost autonomous AI engineering platform implementing the official **Model Context Protocol (MCP)** SDK, a privacy-first **Local Tri-Store RAG Pipeline** (ChromaDB Vector Store, In-Memory/Disk BM25 Lexical Store, and SQLite Knowledge Graph), a **Deterministic Canonical PDF Page Store**, and **Lazy Multimodal Processing** (Local OCR Fallback and Visual RAG).

> **Core Operating Principle**: SentinelForge uses the least expensive retrieval modality capable of answering the query and escalates to OCR, Visual RAG, or GraphRAG only when additional evidence is required.

---

## 1. Architectural Highlights

* **Official MCP 2.x Server**: Registered tools (`ingest_content`, `retrieve_context`, `inspect_repository`, `propose_patch`, `run_sandbox_command`, `get_system_telemetry`), resources (`sentinelforge://system/status`), and prompts (`code_review_and_test`).
* **Canonical Page Records**: Every PDF page receives a persistent, 1-indexed canonical record in SQLite (`./data/chroma/canonical_pages.db`) tracking exact line offsets, text metrics, image counts, image area ratio, and extraction warnings.
* **Lightweight Page Classifier**: Categorizes PDF pages deterministically into `TEXT_PAGE`, `SCANNED_PAGE`, `MIXED_PAGE`, `VISUAL_HEAVY_PAGE`, or `EMPTY_OR_UNREADABLE_PAGE` using cheap structural heuristics (character count, word count, embedded image count, and image area ratio) without expensive ML inference.
* **Lazy Multimodal Processing vs. Adaptive Retrieval**:
  * **Lazy Processing (WHEN)**: Expensive representations (OCR text, visual regions) are *only generated on demand* when a scanned or visual page is queried.
  * **Adaptive Retrieval (WHICH)**: The router selects the *minimum sufficient modality* (vector, BM25, graph, OCR, visual) required to answer the query.
* **Zero-Cost & Offline by Default**: SentenceTransformers `all-MiniLM-L6-v2` running locally on CPU, local SQLite knowledge graph and canonical page registry, zero paid API dependencies.
* **Constrained Deployment Ready**: Engineered specifically for resource-constrained environments like Render Free (512MB RAM ceiling).

---

## 2. Lazy Processing vs. Adaptive Retrieval

| Stage | Trigger Condition | Execution Model | Resource Footprint |
|---|---|---|---|
| **Ingestion** | Document upload / `ingest_content` | Fast text extraction, page classification, canonical page SQLite indexing, vector embedding, BM25 indexing. | < 50MB RAM, CPU only. |
| **Normal Text Query** | "Explain authentication rules" | **Vector-only retrieval**. Bypasses OCR, Visual RAG, and GraphRAG completely. | Fast (< 20ms), 0 extra memory. |
| **Exact Symbol Query** | "Where is OrderProcessor defined" | **Lexical BM25 + Vector**. Tokenizes camelCase and snake_case symbols. | In-memory / disk inverted index. |
| **Dependency / Caller** | "What does checkout call" | **Knowledge Graph traversal** (1-hop BFS). Traverses verified AST syntax edges (`CALLS`, `IMPORTS`, `DEFINES`). | SQLite query, 0 embedding overhead. |
| **Scanned Document Query** | "What is the total on invoice.pdf" (Page is `SCANNED_PAGE`) | **Lazy On-Demand OCR**. Checks disk cache; if missing, runs local OCR on target page with concurrency locking; sanitizes output. | Triggered only for target pages (max 3). |
| **Diagram / Architecture** | "What does the architecture diagram show" | **Lazy Visual RAG**. Checks disk cache; inspects visual regions and bounding boxes. Disabled by default on Render Free to prevent OOM. | Configurable via `ENABLE_VISUAL_RAG=true`. |

---

## 3. Deployment & Render Resource Controls

SentinelForge enforces hard configuration bounds in `src/config.py` to operate safely within Render Free's 512MB RAM limit:

* `MAX_PDF_SIZE_MB=20`: Safely rejects oversized PDFs.
* `MAX_PDF_PAGES=100`: Prevents memory exhaustion from giant documents.
* `MAX_OCR_PAGES_PER_REQUEST=3`: Prevents runaway CPU time during on-demand OCR.
* `MAX_VISUAL_PAGES_PER_REQUEST=2`: Bounds visual region rendering.
* `MAX_RENDER_IMAGE_RES=150`: Caps DPI rendering resolution.
* `ENABLE_VISUAL_RAG=false`: Kept disabled by default on Render Free; visual queries cleanly fall back to text + BM25 without fake embeddings.
* `ENABLE_OCR=true`: Active with local Tesseract if installed, or safe graceful degradation if the system binary is missing.

### Ephemeral Storage Behavior on Render
1. All SQLite databases (`canonical_pages.db`, `knowledge_graph.db`) and ChromaDB directories recreate cleanly on fresh boot.
2. In-memory and disk caches (`./data/scratch/ocr_cache/`, `./data/scratch/visual_cache/`) gracefully rebuild on demand without data loss.
3. System telemetry (`get_system_telemetry`) exposes active capabilities, memory limits, and component health.

---

## 4. Verification & Testing

SentinelForge maintains a **100% passing automated test suite** with **52 tests passing in under 2 seconds**:

```bash
# Run the single-command verification gate (linter + full test suite)
./scripts/run_all_checks.sh

# Or run pytest directly
./.venv/bin/pytest -v tests/

# Run specific multimodal tests
./.venv/bin/pytest -v tests/test_pdf_multimodal.py
```

### Test Suite Breakdown (52 Tests Total)
* `tests/test_config.py` (5 tests): Settings defaults, directory auto-creation, path jail, CORS, provider validation.
* `tests/test_mcp_server.py` (8 tests): MCP tool discovery, resource reading, prompt rendering, ingestion, retrieval, sandbox execution, telemetry.
* `tests/test_rag_pipeline.py` (9 tests): Multi-format parsing (PDF, MD, AST, JS/TS, JSON), deduplication, deletion, anti-injection sanitization.
* `tests/test_adaptive_rag.py` (10 tests): AST graph extraction, multi-hop BFS, intent routing, result fusion (RRF), comparative evaluation.
* `tests/test_pdf_multimodal.py` (20 tests): Page classification (`TEXT_PAGE`, `SCANNED_PAGE`, `MIXED_PAGE`, `VISUAL_HEAVY_PAGE`), canonical persistence, lazy OCR execution and disk caching, graceful fallbacks, visual region inspection, multi-signal routing, prompt-injection sanitization, oversized file rejections, and comparative multimodal evaluation.

---

## 5. Configuration Reference (`.env`)

```ini
# Core Configuration
DATA_DIR=./data
WORKSPACE_ROOT=./data/workspace
VECTOR_DB_PATH=./data/chroma
SCRATCH_DIR=./data/scratch

# Local Embeddings
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDING_DEVICE=cpu
OFFLINE_MODE=false

# PDF & Multimodal Controls
MAX_PDF_SIZE_MB=20
MAX_PDF_PAGES=100
PDF_PAGE_TEXT_MIN_CHARS=50
PDF_SCANNED_MAX_CHARS=40
PDF_VISUAL_MIN_IMAGES=1

# Lazy OCR Controls
ENABLE_OCR=true
MAX_OCR_PAGES_PER_REQUEST=3
OCR_TIMEOUT_SEC=10

# Lazy Visual RAG Controls (Render-Friendly)
ENABLE_VISUAL_RAG=false
ENABLE_LAZY_VISUAL_PROCESSING=true
VISUAL_PROCESSING_MODE=on_demand
MAX_VISUAL_PAGES_PER_REQUEST=2
MAX_RENDER_IMAGE_RES=150
VISUAL_TIMEOUT_SEC=10
```

---

## 6. Known Limitations & Trade-Offs

1. **System Tesseract Binary**: Live local OCR requires `tesseract` installed on the host OS. If unavailable, SentinelForge automatically enters graceful fallback mode, logs an actionable warning in telemetry, and avoids crashing the ingestion pipeline.
2. **Visual Model Memory Footprint**: Genuine local Vision-Language Models (e.g. CLIP or ViT) typically require 350MB+ RAM. To guarantee stability within Render Free's 512MB RAM ceiling, `ENABLE_VISUAL_RAG` defaults to `false`. When disabled, the system never fabricates fake embeddings and transparently routes visual queries to text + BM25.
