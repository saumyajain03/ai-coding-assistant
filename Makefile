.PHONY: install lint format test check eval dev clean

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
RUFF = $(VENV)/bin/ruff
UVICORN = $(VENV)/bin/uvicorn

install:
	@echo ">> Installing dependencies into $(VENV)..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

lint:
	@echo ">> Running ruff linting..."
	$(RUFF) check .

format:
	@echo ">> Formatting source code..."
	$(RUFF) format .

test:
	@echo ">> Running automated tests..."
	$(PYTEST) -v tests/

check:
	@echo ">> Running all automated checks..."
	./scripts/run_all_checks.sh

eval:
	@echo ">> Running retrieval benchmark suite..."
	$(PYTHON) scripts/evaluate_retrieval.py

dev:
	@echo ">> Starting SentinelForge API & UI on http://localhost:8000..."
	$(UVICORN) src.api.app:app --host 0.0.0.0 --port 8000 --reload

clean:
	@echo ">> Cleaning cache and ephemeral data..."
	rm -rf __pycache__ .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
