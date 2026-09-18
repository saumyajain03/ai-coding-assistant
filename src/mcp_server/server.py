"""
SentinelForge Official Model Context Protocol (MCP) Server
Integrates 6 meaningful tools, 1 resource, and 1 prompt using official MCP SDK (mcp 2.x).
Provides typed schemas, strict validation, actionable errors, and health checking.
"""

from typing import Any

from mcp.server.mcpserver import MCPServer

from src.mcp_server.prompts.code_review import (
    PROMPT_DESCRIPTION,
    PROMPT_NAME,
    render_code_review_prompt,
)
from src.mcp_server.resources.workspace_status import (
    RESOURCE_MIME_TYPE,
    RESOURCE_NAME,
    RESOURCE_URI,
    get_workspace_status_resource,
)
from src.mcp_server.tools.ingestion import ingest_content_tool
from src.mcp_server.tools.inspection import inspect_repository_tool
from src.mcp_server.tools.patch import propose_patch_tool
from src.mcp_server.tools.retrieval import retrieve_context_tool
from src.mcp_server.tools.sandbox import run_sandbox_command_tool
from src.mcp_server.tools.system import get_system_telemetry_tool


def create_mcp_server() -> MCPServer:
    """
    Creates and initializes the official SentinelForge MCP server
    with all 6 tools, 1 resource, and 1 reusable prompt.
    """
    server = MCPServer(
        name="sentinelforge-mcp",
        version="1.0.0",
        instructions="SentinelForge Privacy-First AI Developer Platform Core MCP Server",
    )

    # --------------------------------------------------------------------------
    # 1. Register Tools (All 6 tools with typed parameters and docstrings)
    # --------------------------------------------------------------------------

    @server.tool(
        name="ingest_content",
        description="Ingests, parses, chunks, and indexes documents and code files into the local RAG engine with deduplication.",
    )
    def tool_ingest_content(
        filename: str,
        content: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        return ingest_content_tool(filename=filename, content=content, file_path=file_path)

    @server.tool(
        name="retrieve_context",
        description="Retrieves semantic context and code snippets from the local vector database with citations and untrusted-data wrapping.",
    )
    def tool_retrieve_context(
        query: str,
        top_k: int = 5,
        filter_filename: str | None = None,
    ) -> dict[str, Any]:
        return retrieve_context_tool(query=query, top_k=top_k, filter_filename=filter_filename)

    @server.tool(
        name="inspect_repository",
        description="Safely inspects the workspace repository directory tree, file metadata, and workspace files with path jail protection.",
    )
    def tool_inspect_repository(
        subpath: str = "",
        depth: int = 2,
        file_pattern: str | None = None,
    ) -> dict[str, Any]:
        return inspect_repository_tool(subpath=subpath, depth=depth, file_pattern=file_pattern)

    @server.tool(
        name="propose_patch",
        description="Proposes a code patch as a reviewable unified diff with AST syntax validation and risk assessment without writing to disk.",
    )
    def tool_propose_patch(
        target_file: str,
        proposed_content: str,
        rationale: str,
    ) -> dict[str, Any]:
        return propose_patch_tool(
            target_file=target_file,
            proposed_content=proposed_content,
            rationale=rationale,
        )

    @server.tool(
        name="run_sandbox_command",
        description="Executes a command inside the isolated workspace sandbox with time, memory, output, and command allowlist restrictions.",
    )
    def tool_run_sandbox_command(
        command: str,
        timeout_sec: int = 15,
        subpath: str = "",
    ) -> dict[str, Any]:
        return run_sandbox_command_tool(
            command=command,
            timeout_sec=timeout_sec,
            subpath=subpath,
        )

    @server.tool(
        name="get_system_telemetry",
        description="Returns platform telemetry, active model mode, sandbox limits, vector index status, and security audit trail.",
    )
    def tool_get_system_telemetry(include_audit_trail: bool = True) -> dict[str, Any]:
        return get_system_telemetry_tool(include_audit_trail=include_audit_trail)

    # --------------------------------------------------------------------------
    # 2. Register MCP Resource (sentinelforge://system/status)
    # --------------------------------------------------------------------------

    @server.resource(
        uri=RESOURCE_URI,
        name=RESOURCE_NAME,
        mime_type=RESOURCE_MIME_TYPE,
        description="Real-time system health, vector index status, and active provider configuration.",
    )
    def resource_workspace_status() -> str:
        return get_workspace_status_resource()

    # --------------------------------------------------------------------------
    # 3. Register MCP Reusable Prompt (code_review_and_test)
    # --------------------------------------------------------------------------

    @server.prompt(
        name=PROMPT_NAME,
        description=PROMPT_DESCRIPTION,
    )
    def prompt_code_review(
        task_description: str,
        target_file: str = "",
        context: str = "",
    ) -> str:
        return render_code_review_prompt(
            task_description=task_description,
            target_file=target_file,
            context=context,
        )

    return server


# Global default server instance
mcp_server_instance = create_mcp_server()


async def invoke_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Standard programmatic client invocation interface for MCP tools.
    Used by the agent and web API to guarantee all core tool operations pass through MCP.
    """
    call_result = await mcp_server_instance.call_tool(tool_name, arguments)

    # Extract structured content or text
    if call_result.structured_content:
        # If wrapped in a single result key or dictionary
        res = call_result.structured_content
        if isinstance(res, dict) and "result" in res and isinstance(res["result"], dict):
            return res["result"]
        return res

    if call_result.content:
        for item in call_result.content:
            if hasattr(item, "text") and item.text:
                return {"result": item.text}

    return {"status": "success", "raw": str(call_result)}
