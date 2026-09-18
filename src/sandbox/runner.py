"""
Sandbox Process Runner
Executes commands within an isolated workspace directory, enforcing hard timeouts,
memory and process limits via setrlimit, and output buffer truncation.
"""

import os
import resource
import subprocess
import time
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.sandbox.security import sanitize_sandbox_output, validate_sandbox_command


def _set_resource_limits(max_memory_mb: int, max_nproc: int) -> None:
    """
    Subprocess preexec hook to apply OS-level resource limits.
    """
    try:
        # Address space (virtual memory) limit
        max_bytes = max_memory_mb * 1024 * 1024
        if hasattr(resource, "RLIMIT_AS"):
            resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
    except Exception:
        pass

    try:
        # Number of processes limit (fork bomb defense)
        if hasattr(resource, "RLIMIT_NPROC"):
            resource.setrlimit(resource.RLIMIT_NPROC, (max_nproc, max_nproc))
    except Exception:
        pass


def execute_sandboxed_command(
    command: str,
    timeout_sec: int | None = None,
    cwd_subpath: str = "",
) -> dict[str, Any]:
    """
    Executes a sandboxed command inside the workspace with security checks and resource limits.

    Returns:
        Structured dictionary containing execution status, exit code, stdout, stderr, and timings.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    exec_cwd = (workspace / cwd_subpath).resolve()

    # Enforce path jail on cwd
    if not settings.is_path_in_workspace(exec_cwd):
        return {
            "error": "SECURITY_VIOLATION: Execution directory is outside workspace root.",
            "exit_code": 126,
            "stdout": "",
            "stderr": "Directory traversal denied.",
            "execution_time_ms": 0,
            "timed_out": False,
            "passed": False,
        }

    exec_cwd.mkdir(parents=True, exist_ok=True)

    # Validate command against security allowlist
    is_allowed, denial_reason, args = validate_sandbox_command(command)
    if not is_allowed:
        return {
            "error": denial_reason,
            "exit_code": 126,
            "stdout": "",
            "stderr": f"Command rejected: {denial_reason}",
            "execution_time_ms": 0,
            "timed_out": False,
            "passed": False,
        }

    timeout = timeout_sec if timeout_sec and timeout_sec > 0 else settings.SANDBOX_TIMEOUT_SEC

    # Prepare sanitized environment with network proxy variables stripped
    env = os.environ.copy()
    if not settings.ALLOW_NETWORK_DEFAULT:
        env["http_proxy"] = ""
        env["https_proxy"] = ""
        env["HTTP_PROXY"] = ""
        env["HTTPS_PROXY"] = ""
        env["NO_PROXY"] = "*"

    # Use active venv python if 'python' or 'pytest' is invoked
    venv_bin = Path(os.getcwd()) / ".venv" / "bin"
    if venv_bin.exists():
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"

    start_time = time.perf_counter()
    timed_out = False

    try:
        process = subprocess.Popen(
            args,
            cwd=exec_cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: _set_resource_limits(
                settings.SANDBOX_MAX_MEMORY_MB, settings.SANDBOX_MAX_NPROC
            ),
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            exit_code = 124
            timed_out = True
            stderr += f"\n[TIMEOUT] Command exceeded maximum execution limit of {timeout}s and was terminated."

    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "command": command,
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Execution failed: {str(e)}",
            "execution_time_ms": elapsed_ms,
            "timed_out": False,
            "passed": False,
        }

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Enforce output buffer limit (default 64KB)
    max_bytes = settings.SANDBOX_MAX_OUTPUT_BYTES
    if len(stdout) > max_bytes:
        stdout = stdout[:max_bytes] + f"\n... [TRUNCATED: Exceeded {max_bytes} bytes limit]"
    if len(stderr) > max_bytes:
        stderr = stderr[:max_bytes] + f"\n... [TRUNCATED: Exceeded {max_bytes} bytes limit]"

    # Sanitize outputs against secret leakage
    clean_stdout = sanitize_sandbox_output(stdout)
    clean_stderr = sanitize_sandbox_output(stderr)

    return {
        "command": command,
        "exit_code": exit_code,
        "stdout": clean_stdout,
        "stderr": clean_stderr,
        "execution_time_ms": elapsed_ms,
        "timed_out": timed_out,
        "passed": (exit_code == 0),
    }
