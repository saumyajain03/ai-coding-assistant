"""
MCP Tool: Sandbox Execution
Executes test workflows, unit tests, and validation commands in an isolated sandbox.
Integrated with Phase 4 Permission Model (Approval tokens & ephemeral secrets).
"""

from typing import Any

from pydantic import BaseModel

from src.sandbox.runner import execute_sandboxed_command


class SandboxExecutionResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    timed_out: bool
    passed: bool
    status: str


def run_sandbox_command_tool(
    command: str,
    timeout_sec: int = 15,
    subpath: str = "",
    approval_token: dict[str, Any] | None = None,
    secrets: dict[str, str] | None = None,
    allow_network: bool | None = None,
) -> dict[str, Any]:
    """
    Executes a command inside the isolated workspace sandbox.
    Enforces time, memory, output, command allowlists, and Phase 4 human approval policies.

    Args:
        command: Command to execute (e.g. 'pytest -v', 'python main.py').
        timeout_sec: Execution timeout limit in seconds (default 15s).
        subpath: Optional subdirectory within the workspace to run in.
        approval_token: Single-use cryptographic approval token for risky operations.
        secrets: Ephemeral key-value credentials injected only during execution.
        allow_network: Explicit override for network access if approved.

    Returns:
        Structured execution result including exit code, stdout, stderr, and status.
    """
    res = execute_sandboxed_command(
        command=command,
        timeout_sec=timeout_sec,
        cwd_subpath=subpath,
        allow_network=allow_network,
        approval_token=approval_token,
        secrets=secrets,
    )

    if res.get("status") == "WAITING_FOR_HUMAN_APPROVAL":
        return res

    status = "success" if res.get("passed") else ("timeout" if res.get("timed_out") else "failed")
    res["status"] = status
    return res
