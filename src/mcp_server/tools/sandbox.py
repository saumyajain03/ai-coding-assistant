"""
MCP Tool: Sandbox Execution
Executes test workflows, unit tests, and validation commands in an isolated sandbox.
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
) -> dict[str, Any]:
    """
    Executes a command inside the isolated workspace sandbox.
    Enforces time, memory, output, and command allowlist restrictions.

    Args:
        command: Command to execute (e.g. 'pytest -v', 'python main.py').
        timeout_sec: Execution timeout limit in seconds (default 15s).
        subpath: Optional subdirectory within the workspace to run in.

    Returns:
        Structured execution result including exit code, stdout, stderr, and timings.
    """
    res = execute_sandboxed_command(
        command=command,
        timeout_sec=timeout_sec,
        cwd_subpath=subpath,
    )

    status = "success" if res.get("passed") else ("timeout" if res.get("timed_out") else "failed")
    res["status"] = status
    return res
