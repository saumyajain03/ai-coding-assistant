# SentinelForge: Autonomous, Privacy-First Agentic Defense Platform

[![CI/CD Pipeline](https://github.com/saumyajain03/ai-coding-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/saumyajain03/ai-coding-assistant/actions/workflows/ci.yml)
[![Tests Passing](https://img.shields.io/badge/pytest-178%20passed-brightgreen)](tests/)
[![Retrieval MRR](https://img.shields.io/badge/RAG%20MRR-0.9375-blue)](scripts/evaluate_retrieval.py)
[![Docker Ready](https://img.shields.io/badge/docker-ready-blue?logo=docker)](Dockerfile)
[![Zero Cost Cloud](https://img.shields.io/badge/Render-Free%20Tier%20(512MB)-emerald)](render.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**SentinelForge** is a production-grade, zero-cost autonomous AI engineering platform and software defense co-worker. It implements the official **Model Context Protocol (FastMCP)**, a privacy-first **Local Tri-Store RAG Pipeline** with lazy multimodal routing, a deterministic **7-Stage Verifiable Agent Loop**, and an unbypassable **Human-in-the-Loop Approval Gate** backed by OS-level sandbox isolation.

> **Core Engineering Invariant**: SentinelForge never mutates code on disk or executes shell commands without deterministic AST diff inspection, cryptographic action hashing, POSIX `setrlimit` isolation, and explicit operator authorization.

---

## 🏗️ Architectural Subsystems

```
                                    +-----------------------------------------+
                                    |     React 19 Dark Engineering Console   |
                                    |        (Vite SPA, Native File Picker)   |
                                    +--------------------+--------------------+
                                                         | HTTP / WebSockets
                                                         v
                                    +--------------------+--------------------+
                                    |      FastAPI Security Gateway (3.1)     |
                                    |      (Rate Limits, Audit Middleware)    |
                                    +---------+---------------------+---------+
                                              |                     |
                   +--------------------------+                     +--------------------------+
                   |                                                                           |
                   v                                                                           v
+------------------+------------------+                                     +------------------+------------------+
|   7-Stage Autonomous Agent Loop     |                                     |    Local Tri-Store RAG Engine    |
|                                     |                                     |                                     |
| 1. Task Analysis & Requirements     |                                     | - ChromaDB (all-MiniLM-L6-v2)       |
| 2. Plan Generation & Test Commands  |                                     | - Persistent BM25 Lexical Store     |
| 3. Context Retrieval (via MCP)      | <---------------------------------> | - SQLite AST Knowledge Graph        |
| 4. Patch Synthesis (AST Diff)       |                                     | - Deterministic PDF Canonical Pages |
| 5. Isolated Sandbox Execution       |                                     | - Lazy OCR & Visual Smart Router    |
| 6. Self-Critique & Risk Scoring     |                                     | - SHA-256 Incremental Deduplication |
| 7. Human Approval Gate & Report     |                                     +-------------------------------------+
+------------------+------------------+
                   |
                   v
+------------------+-----------------------------------------------------------------------------------------------+
| Hardened Process Sandbox & MCP Layer (Official FastMCP JSON-RPC)                                                 |
| - Tools: `read_code`, `propose_patch`, `apply_patch`, `execute_sandboxed_command`, `get_system_telemetry`        |
| - Boundary Enforcement: Symlink-resolving realpath jail (`./data/workspace`), Command allowlists                |
| - Resource Limits: POSIX `setrlimit` (200MB memory ceiling, 10 process fork cap, 15s hard timeout)              |
| - Immutable Audit: SHA-256 action hashes, token redacting sanitizers (`ghp_`, `sk-`, `gsk_`), JSONL timeline    |
+------------------------------------------------------------------------------------------------------------------+
```

---

## ⚡ Key Technical Features

### 1. Model Context Protocol (FastMCP)
- Standardized, decoupled tool calling using the official Python FastMCP specification.
- Exposes typed tools (`read_code`, `propose_patch`, `apply_patch`, `execute_sandboxed_command`, `get_system_telemetry`), resources (`sentinelforge://system/status`), and defensive prompt templates (`code_review_and_test`).
- Cryptographically binds patch proposals to SHA-256 action hashes. The agent cannot apply modifications directly; it can only stage proposals in memory until authorized.

### 2. Privacy-First Local Tri-Store RAG
- **Dense Vector Search**: Powered by `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions) stored in a local ChromaDB instance on CPU.
- **BM25 Lexical Search**: Custom inverted index with camelCase and snake_case tokenization to capture exact code identifiers, error codes, and regex patterns.
- **Reciprocal Rank Fusion (RRF)**: Merges dense and sparse ranks with a constant $k=60$.
- **Page-Aware PDF Store**: Deterministic 1-indexed SQLite canonical page registry with structural heuristics classifying pages (`TEXT_PAGE`, `SCANNED_PAGE`, `MIXED_PAGE`, `VISUAL_HEAVY_PAGE`).
- **Lazy OCR & Multimodal Fallback**: Computes expensive representations only on demand for target pages, maintaining zero extra memory overhead for standard text.
- **SHA-256 Deduplication**: Files with matching hashes skip parsing and indexing for sub-millisecond incremental updates.

### 3. Verifiable 7-Stage Agent Orchestrator
- **State Machine**: Sequentially transitions through **Analysis** $\rightarrow$ **Plan** $\rightarrow$ **Retrieval** $\rightarrow$ **Patch Proposal** $\rightarrow$ **Sandbox Execution** $\rightarrow$ **Self-Critique** $\rightarrow$ **Final Report**.
- **Human-in-the-Loop Gate**: If an action mutates workspace files, changes git branches, or executes external commands, execution halts at `WAITING_FOR_HUMAN_APPROVAL`.
- **AST Diff Generation**: Validates syntax before proposing patches. Automatically calculates lines added/removed and computes risk scores (1–10).
- **Self-Critique & Truthful Reporting**: Failed tests trigger a critique step with actionable regression analysis rather than fabricated success reports.

### 4. Defense-in-Depth Process Sandbox
- **Path Jail**: Every target path is canonicalized with `os.path.realpath`. Path traversals (`../`) and symlink breakout attacks are intercepted before process invocation.
- **Strict Command Allowlist**: Only vetted binaries (`python`, `pytest`, `node`, `npm`, `git`) are permitted. Shell interpreters (`bash`, `sh`, `sudo`) are classified as `ALWAYS_BLOCKED`.
- **OS Resource Limits (`setrlimit`)**: Hard virtual memory ceiling (`RLIMIT_AS`), maximum process fork cap (`RLIMIT_NPROC` set to 10 to eliminate fork bombs), and execution timeouts.
- **Stream Sanitization**: Scans child process stdout/stderr with regex heuristics to redact API keys and secrets, truncating buffers to 64 KB.

### 5. Zero-Cost Cloud Deployment (Render Free Ready)
- **Engineered for 512 MB RAM**: Baseline memory footprint is **213.7 MiB**. Under active RAG vector queries and ChromaDB indexing, memory peaks at **374.1 MiB**, leaving **>135 MiB of headroom** below the Render Free OOM ceiling.
- **Pre-Baked Weights**: Bundles pre-downloaded ONNX embedding weights into `/app/models` for zero-network cold boots.
- **Ephemeral Storage Resilience**: Workspaces and vector stores auto-initialize on boot without crashing on instance restarts.

---

## 📊 Empirical Benchmarks & Verification

SentinelForge maintains a verified quality bar enforced across automated test suites, retrieval benchmarks, and container runtimes:

| Metric / Benchmark | Standard / Target | Verified Result | Status |
| :--- | :--- | :--- | :--- |
| **Automated Test Suite** | Full codebase verification | **178 passed**, 1 warning in 11.67s | **PASS** |
| **Security Test Harness** | Path jail, fork bombs, injection, memory | **49 security tests passed** | **PASS** |
| **Retrieval Benchmark (MRR)** | $\ge 0.75$ | **0.9375** | **PASS** |
| **Retrieval Benchmark (Recall@3)** | $\ge 0.80$ | **1.0000 (100%)** | **PASS** |
| **Retrieval Query Latency ($p_{50}$)** | $\le 100\text{ ms}$ on local CPU | **44.90 ms** | **PASS** |
| **Ruff Code Linter** | PEP 8, zero warnings | `All checks passed!` | **PASS** |
| **React Production Build** | Vite client bundle | Compiled in **237 ms** | **PASS** |
| **Sandbox Execution Latency** | Isolated child process | **18.56 ms** | **PASS** |
| **Dangerous Command Blocked** | `rm -rf /` attempt | Intercepted, Exit `126` in 2ms | **PASS** |
| **Container Memory Footprint** | Render Free $\le 512\text{ MB}$ limit | **374.1 MiB** peak under full load | **PASS** |

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+
- Node.js 20+ (for local frontend development)
- Docker (optional, for containerized execution)

### Option 1: Docker (Single-Command Run)

Build and run the unified production container locally:

```bash
# Clone the repository
git clone https://github.com/saumyajain03/ai-coding-assistant.git
cd ai-coding-assistant

# Build the container image
docker build -t sentinelforge:latest .

# Run the container (maps host port 8000)
docker run -d --name sentinelforge -p 8000:8000 \
  -e PORT=8000 \
  -e LLM_PROVIDER=groq_free \
  -e GROQ_API_KEY="your-groq-api-key" \
  -e LLM_MODEL="openai/gpt-oss-20b" \
  sentinelforge:latest

# Access the platform
# Web Interface: http://localhost:8000/
# Swagger UI Docs: http://localhost:8000/docs
# Healthcheck: http://localhost:8000/api/v1/health
```

### Option 2: Docker Compose

For persistent storage mounting `./data` on the host:

```bash
# Copy and configure environment variables
cp .env.example .env

# Launch with docker compose
docker compose up -d

# Check live service status
docker compose ps
docker compose logs -f
```

### Option 3: Local Development (Without Docker)

```bash
# 1. Set up Python virtual environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Configure environment
cp .env.example .env

# 3. Launch FastAPI backend
uvicorn src.api.app:app --host 0.0.0.0 --port 8001 --reload

# 4. In a separate terminal, launch React frontend
cd src/web
npm install
npm run dev
# Frontend is live at http://localhost:5173
```

---

## 🧪 Running Quality Gates & Benchmarks

Run the complete suite of automated checks locally:

```bash
# Run full pytest suite (all 178 tests)
pytest tests/

# Run Ruff linter and style check
ruff check src/ tests/ scripts/

# Run the local RAG retrieval benchmark
python scripts/evaluate_retrieval.py

# Build the React frontend production bundle
cd src/web && npm run build
```

---

## ☁️ Zero-Cost Deployment to Render Free

SentinelForge is pre-configured for one-click deployment on the **Render Free tier** using [`render.yaml`](render.yaml):

1. Fork or push this repository to GitHub.
2. Log in to [Render](https://render.com) and navigate to **Blueprints** $\rightarrow$ **New Blueprint Instance**.
3. Select your repository. Render automatically reads `render.yaml`.
4. Add your `GROQ_API_KEY` (free tier from [console.groq.com](https://console.groq.com)) in the Render dashboard.
5. Click **Apply**. SentinelForge builds via Docker and deploys with liveness monitoring at `/api/v1/health`.

### Render Free Tier Notes & Ephemeral Lifecycle
- **512 MB RAM Ceiling**: Pre-baked ONNX embeddings and lazy OCR keep total memory usage under 380 MB.
- **15-Minute Inactivity Spin-Down**: Free instances spin down when idle. Pre-baked weights in `/app/models` ensure fast cold boots (<60s) without downloading Hugging Face models over the network.
- **Ephemeral Storage**: Workspaces, vector stores, and SQLite databases recreate cleanly on fresh boot. Custom documents can be instantly re-indexed via `POST /api/v1/upload`.

---

## 🔒 Security Architecture & Guardrails

```
                    UNTRUSTED INPUT (User Prompt / Uploaded File)
                                        │
                                        ▼
                      [Document Ingestion Sanitizer]
                      - Scans for injection tokens & hostile overrides
                      - Encloses text in <untrusted_document_context>
                                        │
                                        ▼
                         [FastMCP Tool Validation]
                      - Rejects unauthorized tool calls
                      - Validates schema against strict Pydantic models
                                        │
                                        ▼
                      [Approval Gate & Action Hashing]
                      - Generates SHA-256 hash of proposed changes
                      - Prohibits disk mutation without cryptographic token
                                        │
                                        ▼
                        [Hardened Process Sandbox]
                      - `os.path.realpath` symlink & path jail
                      - `resource.setrlimit` (RLIMIT_AS, RLIMIT_NPROC)
                      - Secret regex redactor (`ghp_`, `sk-`, `gsk_`)
                                        │
                                        ▼
                            VERIFIED OUTPUT / PATCH
```

---

## 📁 Repository Structure

```
.
├── .github/workflows/ci.yml       # GitHub Actions CI/CD Pipeline
├── Dockerfile                     # Multi-stage production container build
├── docker-compose.yml             # Local orchestration with resource limits
├── render.yaml                    # Infrastructure-as-code for Render Free
├── requirements.txt               # Locked production dependencies
├── requirements-dev.txt           # Test, lint, and evaluation dependencies
├── scripts/
│   ├── evaluate_retrieval.py      # Automated RAG retrieval benchmark (MRR, Recall@k)
│   └── run_all_checks.sh          # Single-command verification gate
├── src/
│   ├── agent/                     # 7-Stage Agent Loop & Prompt Engineering
│   │   ├── diff_generator.py      # AST-validated diff generator
│   │   ├── llm_client.py          # Unified zero-cost LLM connector (Groq, HF, Mock)
│   │   ├── loop.py                # 7-Stage sequential state machine
│   │   └── prompts.py             # Defensive prompts & system invariants
│   ├── api/                       # FastAPI application & endpoints
│   │   ├── app.py                 # App factory & SPA static file serving
│   │   ├── middleware.py          # Security, rate limiting & audit middleware
│   │   └── routes/platform.py     # Chat, upload, patch, sandbox & task routes
│   ├── mcp_server/                # Official FastMCP JSON-RPC Server
│   │   ├── server.py              # Server bootstrap & tool registration
│   │   └── tools/                 # Ingestion, retrieval, patch, sandbox tools
│   ├── rag/                       # Local Hybrid Tri-Store RAG Pipeline
│   │   ├── canonical_page_store.py# SQLite 1-indexed page store
│   │   ├── hybrid_retriever.py    # Dense + BM25 + Reciprocal Rank Fusion
│   │   ├── indexer.py             # Multi-format parsers & SHA-256 deduplication
│   │   └── visual_engine.py       # Smart router & lazy multimodal fallback
│   ├── sandbox/                   # Defensive Process Sandbox
│   │   ├── audit.py               # Structured audit logging & action hashes
│   │   ├── policy.py              # Approval manager & single-use tokens
│   │   ├── runner.py              # Subprocess execution with setrlimit
│   │   └── security.py            # Path jail, command allowlist & redactor
│   └── web/                       # React 19 + Vite Dark Engineering Console
│       ├── src/components/        # Stepper, DiffViewer, Modal, Terminal, Audit
│       └── src/services/api.ts    # Unified API service layer
└── tests/                         # Comprehensive 178-test automated suite
    ├── evaluation/                # Ground-truth queries & benchmark definitions
    ├── test_agent_loop.py         # 7-stage state machine tests
    ├── test_api_endpoints.py      # FastAPI route & rate limiting tests
    ├── test_mcp_server.py         # FastMCP tools & resource tests
    ├── test_rag_pipeline.py       # Hybrid RAG & deduplication tests
    └── test_sandbox_security.py   # Adversarial injection, jail & fork bomb tests
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
