"""
Phase 1 & Phase 7 Verification: Model Context Protocol (MCP) Server Tests
Covers Task 7.1 (Tests 1-6):
1. test_mcp_tool_discovery: Verifies all 6 tools are registered with valid schemas.
2. test_mcp_resource_read: Verifies reading sentinelforge://system/status.
3. test_mcp_prompt_get: Verifies rendering code_review_and_test prompt.
4. test_mcp_ingest_tool_invocation: Tests ingest_content with valid and invalid inputs.
5. test_mcp_retrieve_tool_invocation: Tests context retrieval schema and output structure.
6. test_mcp_sandbox_tool_timeout: Tests timeout triggering actionable error response.
Additional tests:
- test_mcp_inspect_repository_jail
- test_mcp_propose_patch_tool
- test_mcp_sandbox_command_execution
- test_mcp_system_telemetry
"""

import json
from pathlib import Path

import pytest

from src.config import get_settings
from src.mcp_server.server import create_mcp_server, invoke_mcp_tool


@pytest.fixture
def mcp_server():
    """Provides a fresh MCPServer instance for testing."""
    return create_mcp_server()


# 1. Tool Discovery & Schemas
@pytest.mark.asyncio
async def test_mcp_tool_discovery(mcp_server):
    """Verify that all 6 required tools are discovered with valid schemas."""
    tools = await mcp_server.list_tools()
    tool_names = {t.name for t in tools}

    expected_tools = {
        "ingest_content",
        "retrieve_context",
        "inspect_repository",
        "propose_patch",
        "run_sandbox_command",
        "get_system_telemetry",
    }
    assert expected_tools.issubset(tool_names)
    assert len(tools) >= 6

    # Verify each tool has non-empty description and parameters schema
    for t in tools:
        assert t.description != ""
        assert t.input_schema is not None
        assert t.input_schema.get("type") == "object"


# 2. Resource Read
@pytest.mark.asyncio
async def test_mcp_resource_read(mcp_server):
    """Verify reading sentinelforge://system/status resource."""
    resources = await mcp_server.list_resources()
    resource_uris = [str(r.uri) for r in resources]
    assert "sentinelforge://system/status" in resource_uris

    contents = await mcp_server.read_resource("sentinelforge://system/status")
    assert len(contents) > 0
    data = json.loads(contents[0].content)
    assert data["app_name"] == "SentinelForge"
    assert data["status"] == "operational"
    assert "sandbox_limits" in data
    assert data["sandbox_limits"]["human_approval_required"] is True


@pytest.mark.asyncio
async def test_mcp_resource_discovery_and_read(mcp_server):
    """Alias verifying resource discovery and read compatibility."""
    await test_mcp_resource_read(mcp_server)


# 3. Prompt Get
@pytest.mark.asyncio
async def test_mcp_prompt_get(mcp_server):
    """Verify rendering code_review_and_test prompt with arguments."""
    prompts = await mcp_server.list_prompts()
    prompt_names = [p.name for p in prompts]
    assert "code_review_and_test" in prompt_names

    rendered = await mcp_server.get_prompt(
        "code_review_and_test",
        {"task_description": "Fix zero division error", "target_file": "math_utils.py"},
    )
    msg_text = rendered.messages[0].content.text
    assert "Fix zero division error" in msg_text
    assert "math_utils.py" in msg_text
    assert "EXECUTION PROTOCOL" in msg_text


@pytest.mark.asyncio
async def test_mcp_prompt_discovery_and_render(mcp_server):
    """Alias verifying prompt discovery and render compatibility."""
    await test_mcp_prompt_get(mcp_server)


# 4. Ingest Tool Invocation (Valid & Invalid Inputs)
@pytest.mark.asyncio
async def test_mcp_ingest_tool_invocation():
    """Verify ingest_content tool with valid and invalid inputs."""
    # Valid markdown ingestion
    sample_doc = "# Testing Service\nProvides automated regression test execution.\n"
    res_valid = await invoke_mcp_tool(
        "ingest_content",
        {"filename": "test_service.md", "content": sample_doc},
    )
    assert res_valid["status"] in ("indexed_successfully", "already_indexed")
    assert res_valid["chunk_count"] > 0
    assert "sha256_hash" in res_valid

    # Invalid input 1: Unsupported file extension
    res_unsupported = await invoke_mcp_tool(
        "ingest_content",
        {"filename": "payload.exe", "content": "binary"},
    )
    assert res_unsupported["status"] == "failed"
    assert "UNSUPPORTED_FILE_TYPE" in res_unsupported["error"]

    # Invalid input 2: Non-existent file path
    res_notfound = await invoke_mcp_tool(
        "ingest_content",
        {"filename": "missing.py", "file_path": "/path/does/not/exist/missing.py"},
    )
    assert res_notfound["status"] == "failed"
    assert "FILE_NOT_FOUND" in res_notfound["error"]

    # Invalid input 3: Missing both content and file_path
    res_missing_args = await invoke_mcp_tool(
        "ingest_content",
        {"filename": "empty.py"},
    )
    assert res_missing_args["status"] == "failed"
    assert "INVALID_ARGUMENTS" in res_missing_args["error"]


# 5. Retrieve Tool Invocation
@pytest.mark.asyncio
async def test_mcp_retrieve_tool_invocation():
    """Verify retrieve_context tool output schema, citations, and defensive prompt."""
    doc = (
        "# Security Architecture\n"
        "All commands are executed inside an isolated sandbox with a 15-second timeout.\n"
        "Human approval is required for mutating Git commands.\n"
    )
    await invoke_mcp_tool("ingest_content", {"filename": "sec_arch.md", "content": doc})

    res = await invoke_mcp_tool(
        "retrieve_context",
        {"query": "What is the sandbox timeout and Git approval requirement?", "top_k": 3},
    )
    assert "total_retrieved" in res
    assert res["total_retrieved"] > 0
    assert "results" in res
    assert "defensive_context_prompt" in res

    first_hit = res["results"][0]
    assert "filename" in first_hit
    assert "start_line" in first_hit
    assert "end_line" in first_hit
    assert "citation" in first_hit
    assert "safe_wrapped_content" in first_hit
    assert "<untrusted_document_context" in first_hit["safe_wrapped_content"]


@pytest.mark.asyncio
async def test_mcp_ingest_and_retrieve_flow():
    """Verify combined ingestion and retrieval flow through MCP client."""
    await test_mcp_retrieve_tool_invocation()


# 6. Sandbox Tool Timeout
@pytest.mark.asyncio
async def test_mcp_sandbox_tool_timeout():
    """Verify that timeout triggers an actionable error response with exit code 124."""
    res = await invoke_mcp_tool(
        "run_sandbox_command",
        {"command": 'python -c "import time; time.sleep(5)"', "timeout_sec": 1},
    )
    assert res["passed"] is False
    assert res["timed_out"] is True
    assert res["exit_code"] == 124
    assert res["status"] == "timeout"
    assert "TIMEOUT" in res["stderr"]


# Additional MCP Tool Verifications
@pytest.mark.asyncio
async def test_mcp_inspect_repository_jail(tmp_path):
    """Verify repository inspection within workspace and blocking of path traversal."""
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    test_file = workspace / "sample_mcp.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    try:
        res = await invoke_mcp_tool("inspect_repository", {"subpath": ""})
        assert "total_files" in res
        assert res["total_files"] >= 1

        # Attempt path traversal
        traversal_res = await invoke_mcp_tool(
            "inspect_repository",
            {"subpath": "../../"},
        )
        assert "SECURITY_VIOLATION" in traversal_res.get("error", "")
    finally:
        if test_file.exists():
            test_file.unlink()


@pytest.mark.asyncio
async def test_mcp_propose_patch_tool():
    """Verify propose_patch computes unified diff and checks AST syntax."""
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    calc_file = workspace / "calc_mcp.py"
    calc_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    try:
        proposed = "def add(a, b):\n    return a + b\n"
        res = await invoke_mcp_tool(
            "propose_patch",
            {
                "target_file": "calc_mcp.py",
                "proposed_content": proposed,
                "rationale": "Fix subtraction bug in add function",
            },
        )
        assert res["syntax_valid"] is True
        assert "-    return a - b" in res["unified_diff"]
        assert "+    return a + b" in res["unified_diff"]
        assert res["status"] == "PENDING_APPROVAL"

        # Disk file must remain UNCHANGED
        assert calc_file.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"
    finally:
        if calc_file.exists():
            calc_file.unlink()


@pytest.mark.asyncio
async def test_mcp_sandbox_command_execution():
    """Verify sandboxed command execution and allowlist enforcement."""
    res = await invoke_mcp_tool(
        "run_sandbox_command",
        {"command": 'python -c "print(40 + 2)"'},
    )
    assert res["passed"] is True
    assert res["exit_code"] == 0
    assert "42" in res["stdout"].strip()

    # Disallowed command (e.g. curl)
    bad_res = await invoke_mcp_tool(
        "run_sandbox_command",
        {"command": "curl http://example.com"},
    )
    assert bad_res["passed"] is False
    assert "SECURITY_VIOLATION" in bad_res.get("error", "")


@pytest.mark.asyncio
async def test_mcp_system_telemetry():
    """Verify system telemetry tool reports valid status and resource limits."""
    res = await invoke_mcp_tool("get_system_telemetry", {"include_audit_trail": True})
    assert res["app_name"] == "SentinelForge"
    assert res["status"] == "operational"
    assert "sandbox_limits" in res
    assert res["sandbox_limits"]["human_approval_required"] is True
