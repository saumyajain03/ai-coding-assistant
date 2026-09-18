"""
Phase 1 Verification: Model Context Protocol (MCP) Server Tests
Proves MCP client discovery and invocation of all 6 tools, 1 resource, and 1 prompt.
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


@pytest.mark.asyncio
async def test_mcp_tool_discovery(mcp_server):
    """Verify that all 6 required tools are discovered via the official MCP SDK."""
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


@pytest.mark.asyncio
async def test_mcp_resource_discovery_and_read(mcp_server):
    """Verify discovery and reading of sentinelforge://system/status resource."""
    resources = await mcp_server.list_resources()
    resource_uris = [str(r.uri) for r in resources]
    assert "sentinelforge://system/status" in resource_uris

    contents = await mcp_server.read_resource("sentinelforge://system/status")
    assert len(contents) > 0
    data = json.loads(contents[0].content)
    assert data["app_name"] == "SentinelForge"
    assert data["status"] == "operational"
    assert "sandbox_limits" in data


@pytest.mark.asyncio
async def test_mcp_prompt_discovery_and_render(mcp_server):
    """Verify discovery and rendering of code_review_and_test prompt."""
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
async def test_mcp_ingest_and_retrieve_flow():
    """Verify content ingestion and context retrieval through MCP client invocation."""
    sample_doc = (
        "# Authentication Service\n"
        "The authentication module uses JWT tokens with RS256 signing.\n"
        "Tokens expire after 3600 seconds.\n"
    )

    # Ingest content via MCP
    ingest_res = await invoke_mcp_tool(
        "ingest_content",
        {"filename": "auth_docs.md", "content": sample_doc},
    )
    assert ingest_res["status"] in ("indexed_successfully", "already_indexed")
    assert ingest_res["chunk_count"] > 0
    assert "sha256_hash" in ingest_res

    # Retrieve context via MCP
    retrieve_res = await invoke_mcp_tool(
        "retrieve_context",
        {"query": "How long before JWT tokens expire?", "top_k": 2},
    )
    assert retrieve_res["total_retrieved"] > 0
    first_hit = retrieve_res["results"][0]
    assert first_hit["filename"] == "auth_docs.md"
    assert "3600" in first_hit["content"]
    assert "<untrusted_document_context" in first_hit["safe_wrapped_content"]


@pytest.mark.asyncio
async def test_mcp_inspect_repository_jail(tmp_path):
    """Verify repository inspection within workspace and blocking of path traversal."""
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    # Create a safe file in workspace
    test_file = workspace / "sample.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    # Inspect valid workspace
    res = await invoke_mcp_tool("inspect_repository", {"subpath": ""})
    assert "total_files" in res
    assert res["total_files"] >= 1

    # Attempt path traversal
    traversal_res = await invoke_mcp_tool(
        "inspect_repository",
        {"subpath": "../../"},
    )
    assert "SECURITY_VIOLATION" in traversal_res.get("error", "")


@pytest.mark.asyncio
async def test_mcp_propose_patch_tool():
    """Verify propose_patch computes unified diff and checks AST syntax."""
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    # Create an initial file in workspace
    calc_file = workspace / "calculator.py"
    calc_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    # Propose fix
    proposed = "def add(a, b):\n    return a + b\n"
    res = await invoke_mcp_tool(
        "propose_patch",
        {
            "target_file": "calculator.py",
            "proposed_content": proposed,
            "rationale": "Fix subtraction bug in add function",
        },
    )
    assert res["syntax_valid"] is True
    assert "-    return a - b" in res["unified_diff"]
    assert "+    return a + b" in res["unified_diff"]
    assert res["status"] == "PENDING_APPROVAL"

    # Disk file must remain UNCHANGED (HITL safety invariant)
    assert calc_file.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"


@pytest.mark.asyncio
async def test_mcp_sandbox_command_execution():
    """Verify sandboxed command execution and allowlist enforcement."""
    # Allowed command
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
