"""
MCP Resource: System and Workspace Status
URI: sentinelforge://system/status
Provides a real-time JSON snapshot of workspace statistics, vector index counts, and health.
"""

import json

from src.mcp_server.tools.system import get_system_telemetry_tool

RESOURCE_URI = "sentinelforge://system/status"
RESOURCE_NAME = "SentinelForge System & Workspace Status"
RESOURCE_MIME_TYPE = "application/json"


def get_workspace_status_resource() -> str:
    """
    Returns the serialized JSON content for sentinelforge://system/status.
    """
    telemetry = get_system_telemetry_tool(include_audit_trail=True)
    return json.dumps(telemetry, indent=2)
