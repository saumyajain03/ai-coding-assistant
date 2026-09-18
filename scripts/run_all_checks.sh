#!/usr/bin/env bash
set -eo pipefail

echo "================================================================="
echo "  PROJECT SENTINELFORGE: RUNNING AUTOMATED VERIFICATION CHECKS   "
echo "================================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# 1. Environment verification
if [ ! -f ".env" ]; then
    echo ">> [1/4] Generating default .env from .env.example..."
    cp .env.example .env
else
    echo ">> [1/4] .env configuration file detected."
fi

# Detect Python interpreter
if [ -d ".venv" ]; then
    PYTHON_EXEC="./.venv/bin/python"
    PYTEST_EXEC="./.venv/bin/pytest"
    RUFF_EXEC="./.venv/bin/ruff"
else
    PYTHON_EXEC="python3"
    PYTEST_EXEC="pytest"
    RUFF_EXEC="ruff"
fi

echo ">> Using Python executable: $($PYTHON_EXEC --version)"

# 2. Linting & Static Code Quality
echo ">> [2/4] Running linter and style checks..."
if command -v "$RUFF_EXEC" >/dev/null 2>&1; then
    $RUFF_EXEC check .
    echo "   [✓] Linting passed clean."
else
    echo "   [!] ruff not found, checking with python -m compileall..."
    $PYTHON_EXEC -m compileall -q src tests
    echo "   [✓] Syntax compilation passed."
fi

# 3. Automated Test Suite
echo ">> [3/4] Running automated test suite..."
if [ -d "tests" ]; then
    $PYTEST_EXEC -v tests/
    echo "   [✓] Test suite passed successfully."
else
    echo "   [!] tests/ directory not populated yet."
fi

# 4. In-Repo Retrieval Evaluation (if benchmark exists)
if [ -f "scripts/evaluate_retrieval.py" ]; then
    echo ">> [4/4] Executing RAG retrieval benchmark suite..."
    $PYTHON_EXEC scripts/evaluate_retrieval.py
    echo "   [✓] Benchmark evaluation completed."
else
    echo ">> [4/4] Skipping retrieval benchmark (will be run when Phase 7 is built)."
fi

echo "================================================================="
echo "  [SUCCESS] All SentinelForge automated checks passed cleanly!   "
echo "================================================================="
