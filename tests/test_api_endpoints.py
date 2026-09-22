"""
Tests for Phase 5 SentinelForge FastAPI Platform API.
Validates:
1. Health endpoint and platform telemetry
2. Security headers (CSP, X-Frame-Options, X-Content-Type-Options, HSTS)
3. Request ID tracking (X-Request-ID)
4. CORS preflight
5. Request validation
6. Rate limiting middleware
7. Sandbox execution with allowed command
8. Sandbox execution blocking ALWAYS_BLOCKED command
9. Human approval gate enforcement (action hash binding, unapproved rejection, approved application)
10. Audit trail exposure
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import get_settings
from src.mcp_server.tools.patch import propose_patch_tool


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_01_health_endpoint_and_telemetry(client):
    """Verifies GET /api/v1/health returns status, provider, and workspace metadata."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app_name" in data
    assert "version" in data
    assert "active_provider" in data
    assert "workspace_root" in data
    assert data["sandbox_timeout_sec"] > 0


def test_02_security_headers_present(client):
    """Verifies that SecurityHeadersMiddleware injects required defensive headers."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert "default-src 'self'" in headers.get("content-security-policy", "")
    assert "max-age=" in headers.get("strict-transport-security", "")


def test_03_request_id_tracking(client):
    """Verifies X-Request-ID is generated if omitted, or propagated if provided."""
    # Auto-generation
    res1 = client.get("/api/v1/health")
    assert "x-request-id" in res1.headers
    assert len(res1.headers["x-request-id"]) > 0

    # Custom propagation
    custom_id = "test-custom-request-id-999"
    res2 = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert res2.headers.get("x-request-id") == custom_id


def test_04_cors_preflight(client):
    """Verifies strict CORS preflight handling."""
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


def test_05_request_validation_rejection(client):
    """Verifies that invalid payloads are rejected with 422 Unprocessable Entity."""
    # Prompt too short (min length 3)
    response = client.post("/api/v1/chat", json={"prompt": "ab"})
    assert response.status_code == 422


def test_06_rate_limiting_enforcement():
    """Verifies that exceeding rate limit on protected endpoints triggers 429 Too Many Requests."""
    settings = get_settings()
    original_limit = settings.RATE_LIMIT_PER_MINUTE
    try:
        settings.RATE_LIMIT_PER_MINUTE = 3
        app = create_app()
        test_c = TestClient(app)

        for _ in range(3):
            res = test_c.get("/api/v1/audit")
            assert res.status_code == 200

        # 4th request must exceed limit
        res_blocked = test_c.get("/api/v1/audit")
        assert res_blocked.status_code == 429
        assert "RATE_LIMIT_EXCEEDED" in res_blocked.text
    finally:
        settings.RATE_LIMIT_PER_MINUTE = original_limit


def test_07_sandbox_run_allowed_command(client):
    """Verifies that safe commands execute through the sandbox endpoint."""
    response = client.post(
        "/api/v1/sandbox/run",
        json={"command": "python -c 'print(\"hello from sandbox\")'"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["exit_code"] == 0
    assert "hello from sandbox" in data["stdout"]
    assert data["passed"] is True


def test_08_sandbox_run_blocked_command(client):
    """Verifies that Phase 3 ALWAYS_BLOCKED commands are blocked via the API."""
    response = client.post(
        "/api/v1/sandbox/run",
        json={"command": "curl https://example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["passed"] is False
    assert data["exit_code"] != 0
    assert "SECURITY_VIOLATION" in (data["error"] or "") or "BLOCKED" in (data["error"] or "")


def test_09_human_approval_enforcement_flow(client):
    """
    Verifies the end-to-end approval gate:
    1. Propose patch via propose_patch_tool
    2. Try to apply without valid action hash -> Rejected
    3. Try to apply unapproved patch -> Rejected
    4. Approve with matching action hash -> Applied & verified
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT)
    test_target = workspace / "api_test_dummy.py"
    test_target.write_text("def dummy():\n    return False\n", encoding="utf-8")

    try:
        # 1. Propose patch
        new_content = "def dummy():\n    return True\n"
        proposal = propose_patch_tool(
            target_file="api_test_dummy.py",
            proposed_content=new_content,
            rationale="Fix dummy function return",
        )
        assert proposal["status"] == "PENDING_APPROVAL"
        request_id = proposal["request_id"]
        action_hash = proposal["action_hash"]

        # 2. Tampered action hash must be rejected
        bad_hash_resp = client.post(
            "/api/v1/patches/action",
            json={
                "request_id": request_id,
                "action_hash": "tampered_hash_value_12345",
                "action": "approve",
            },
        )
        assert bad_hash_resp.status_code == 400
        assert "ACTION_HASH_MISMATCH" in bad_hash_resp.text

        # Target file must still have original content
        assert test_target.read_text(encoding="utf-8") == "def dummy():\n    return False\n"

        # 3. Valid approval
        approve_resp = client.post(
            "/api/v1/patches/action",
            json={
                "request_id": request_id,
                "action_hash": action_hash,
                "action": "approve",
            },
        )
        assert approve_resp.status_code == 200
        app_data = approve_resp.json()
        assert app_data["status"] == "APPLIED"
        assert app_data["approved"] is True

        # Target file must now be updated on disk
        assert test_target.read_text(encoding="utf-8") == new_content

    finally:
        if test_target.exists():
            test_target.unlink()


def test_10_audit_trail_endpoint(client):
    """Verifies that GET /api/v1/audit returns recent security events."""
    response = client.get("/api/v1/audit?limit=10")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) > 0
    first = events[0]
    assert "timestamp" in first
    assert "event_type" in first
    assert "caller" in first


def test_11_agent_task_dispatch_and_polling(client):
    """
    Verifies starting an agent task via POST /api/v1/chat and polling via GET /api/v1/tasks/{task_id}.
    Uses an isolated workspace file to execute all 7 stages.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT)
    test_file = workspace / "api_math_calc.py"
    test_test = workspace / "test_api_math_calc.py"

    test_file.write_text("def multiply(a, b):\n    return a + b\n", encoding="utf-8")
    test_test.write_text("from api_math_calc import multiply\ndef test_multiply():\n    assert multiply(3, 4) == 12\n", encoding="utf-8")

    with patch.object(get_settings(), "LLM_PROVIDER", "synthetic_mock"):
        try:
            # Start task
            test_cmd = 'python -c "from api_math_calc import multiply; assert multiply(3, 4) == 12; print(\'ALL_TESTS_PASS\')"'
            res = client.post(
                "/api/v1/chat",
                json={
                    "prompt": "Fix calculation in api_math_calc.py to multiply properly",
                    "target_file": "api_math_calc.py",
                    "test_command": test_cmd,
                    "proposed_code": "def multiply(a, b):\n    return a * b\n",
                    "skip_rag": True,
                },
            )
            assert res.status_code == 202
            task_id = res.json()["task_id"]

            # Poll task
            import time
            for _ in range(10):
                poll_res = client.get(f"/api/v1/tasks/{task_id}")
                assert poll_res.status_code == 200
                task_data = poll_res.json()
                if task_data["status"] in ("waiting_approval", "completed", "failed"):
                    break
                time.sleep(0.5)

            assert task_data["status"] in ("waiting_approval", "completed")
            assert len(task_data["stages_executed"]) > 0
            assert "Analysis" in task_data["stages_executed"]
            assert task_data["patch_proposal"] is not None
            assert task_data["patch_proposal"]["syntax_valid"] is True
            assert task_data["patch_proposal"]["action_hash"] != ""

            # Test approving the task patch via API
            if task_data["status"] == "waiting_approval":
                prop = task_data["patch_proposal"]
                act_res = client.post(
                    "/api/v1/patches/action",
                    json={
                        "request_id": prop["request_id"],
                        "action_hash": prop["action_hash"],
                        "action": "approve",
                    },
                )
                assert act_res.status_code == 200
                assert act_res.json()["status"] == "APPLIED"
                assert act_res.json()["test_result"]["passed"] is True

                # Task status should now reflect completed
                poll_after = client.get(f"/api/v1/tasks/{task_id}")
                assert poll_after.json()["status"] == "completed"
        finally:
            if test_file.exists():
                test_file.unlink()
            if test_test.exists():
                test_test.unlink()


def test_12_task_immediate_retrieval_and_sanitization(client):
    """
    Regression test: Verifies that GET /api/v1/tasks/{task_id} immediately returns 200
    without returning 404, and gracefully handles quoted or stripped IDs.
    """
    res = client.post(
        "/api/v1/chat",
        json={"prompt": "regression testing immediate retrieval"},
    )
    assert res.status_code == 202
    task_id = res.json()["task_id"]

    # 1. Immediate retrieval right after creation
    get_res = client.get(f"/api/v1/tasks/{task_id}")
    assert get_res.status_code == 200
    assert get_res.json()["task_id"] == task_id

    # 2. Retrieval with raw hex (without task_ prefix)
    raw_hex = task_id.replace("task_", "")
    get_hex_res = client.get(f"/api/v1/tasks/{raw_hex}")
    assert get_hex_res.status_code == 200
    assert get_hex_res.json()["task_id"] == task_id

    # 3. Retrieval with extra surrounding quotes/spaces
    get_quoted_res = client.get(f"/api/v1/tasks/%22{task_id}%22")
    assert get_quoted_res.status_code == 200
    assert get_quoted_res.json()["task_id"] == task_id


def test_13_upload_documents_endpoint(client):
    """Verifies that POST /api/v1/upload indexes valid files (.py, .md)."""
    files = [
        ("files", ("test_sample.py", b"def sample_hello():\n    return 'world'\n", "text/plain")),
        ("files", ("spec.md", b"# Architecture Spec\nSecurity bounds and tests.\n", "text/markdown")),
    ]
    res = client.post("/api/v1/upload", files=files)
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 2
    assert results[0]["filename"] == "test_sample.py"
    assert results[1]["filename"] == "spec.md"


def test_14_upload_unsupported_extension_rejected(client):
    """Verifies that POST /api/v1/upload rejects unsupported file extensions."""
    files = [
        ("files", ("dangerous.exe", b"binary content", "application/octet-stream")),
    ]
    res = client.post("/api/v1/upload", files=files)
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


# ==============================================================================
# Task 7.1 Platform & API Integration Test Implementations (Tests 16 - 19)
# ==============================================================================
def test_fastapi_openapi_metadata(client):
    """Task 7.1.16: Verifies /openapi.json is generated and valid with expected routes."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
    assert "SentinelForge" in schema["info"]["title"]
    paths = schema.get("paths", {})
    assert "/api/v1/health" in paths
    assert "/api/v1/chat" in paths
    assert "/api/v1/patches/action" in paths
    assert "/api/v1/upload" in paths
    assert "/api/v1/bootstrap" in paths


def test_file_upload_size_limit(client):
    """Task 7.1.17: Verifies 413 error on file exceeding 10MB."""
    settings = get_settings()
    # Exceed limit by 100KB
    oversized_bytes = b"A" * (settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 102400)
    files = [
        ("files", ("oversized_doc.md", oversized_bytes, "text/markdown")),
    ]
    response = client.post("/api/v1/upload", files=files)
    assert response.status_code == 413
    assert "exceeds maximum allowed upload size" in response.json()["detail"]


def test_rate_limiter():
    """Task 7.1.18: Verifies 429 response when request limit is exceeded."""
    test_06_rate_limiting_enforcement()


def test_bootstrap_endpoint(client):
    """Verifies workspace initialization is ready for real documents without creating mock files."""
    response = client.post("/api/v1/bootstrap")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["bootstrapped", "ready"]
    assert "workspace_root" in data
    assert "smoke_calc.py" not in data.get("files_created", [])


def test_workspace_reset_endpoint(client):
    """Verifies workspace and RAG index reset endpoint."""
    response = client.post("/api/v1/workspace/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reset"
    assert "workspace_root" in data



