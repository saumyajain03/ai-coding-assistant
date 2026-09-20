"""
Sandbox Process Runner
Executes commands within an isolated workspace directory, enforcing hard timeouts,
memory and process limits via setrlimit, environment sanitization, and output buffer truncation.
Fully integrated with the Phase 4 Permission Model (Propose -> Human Approval -> Execute).
Supports Dual Runtime (Python & Node.js).
"""

import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import (
    ApprovalToken,
    PolicyVerdict,
    classify_action,
    get_approval_manager,
)
from src.sandbox.security import (
    sanitize_sandbox_output,
    validate_sandbox_command,
    validate_sandbox_path,
)

# Hostile environment variables to strip
HOSTILE_ENV_VARS = {
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "NODE_OPTIONS",
    "BASH_ENV",
    "ENV",
    "IFS",
}

PROXY_ENV_VARS = {
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "all_proxy",
}


def _set_resource_limits(
    max_memory_mb: int,
    max_nproc: int,
    max_cpu_sec: int | None = None,
) -> None:
    """
    Subprocess preexec hook to apply OS-level resource limits via setrlimit.
    """
    # 1. Virtual memory ceiling (RLIMIT_AS)
    if hasattr(resource, "RLIMIT_AS"):
        try:
            max_bytes = max_memory_mb * 1024 * 1024
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            limit_val = min(max_bytes, hard) if hard > 0 else max_bytes
            resource.setrlimit(resource.RLIMIT_AS, (limit_val, limit_val))
        except Exception:
            pass

    # 2. Process count ceiling to prevent fork bombs (RLIMIT_NPROC)
    if hasattr(resource, "RLIMIT_NPROC"):
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
            limit_val = min(max_nproc, hard) if hard > 0 else max_nproc
            resource.setrlimit(resource.RLIMIT_NPROC, (limit_val, limit_val))
        except Exception:
            pass

    # 3. CPU time limit (RLIMIT_CPU)
    if max_cpu_sec and hasattr(resource, "RLIMIT_CPU"):
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_sec, max_cpu_sec + 2))
        except Exception:
            pass


def _prepare_sanitized_env(allow_network: bool = False) -> dict[str, str]:
    """
    Prepares a clean environment by stripping hostile variables and proxy bypasses.
    """
    env = os.environ.copy()

    # Strip hostile variables that could hijack execution
    for hostile in HOSTILE_ENV_VARS:
        env.pop(hostile, None)

    # Strip network proxies when network is disabled
    if not allow_network:
        for proxy in PROXY_ENV_VARS:
            env.pop(proxy, None)
        env["NO_PROXY"] = "*"

    # Prioritize active virtualenv binaries for python/pytest
    workspace_root = Path(os.getcwd()).resolve()
    venv_bin = workspace_root / ".venv" / "bin"
    if venv_bin.exists():
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"

    return env


def execute_sandboxed_command(
    command: str,
    timeout_sec: int | None = None,
    cwd_subpath: str = "",
    allow_network: bool | None = None,
    approval_token: ApprovalToken | dict | None = None,
    secrets: dict[str, str] | None = None,
    rationale: str = "",
    files_affected: list[str] | None = None,
) -> dict[str, Any]:
    """
    Executes a sandboxed command inside the workspace with Phase 4 Permission Verification:
    - ALWAYS_BLOCKED: denied immediately regardless of approval.
    - APPROVAL_REQUIRED: pauses and yields structured ActionProposal if not approved;
      verifies exact action hash and executes if valid token provided.
    - AUTO_ALLOWED: executes automatically within sandbox limits.
    """
    settings = get_settings()
    audit = get_audit_logger()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    exec_cwd = (workspace / cwd_subpath).resolve()

    # 1. Enforce path jail & symlink inspection on execution working directory
    valid_cwd, cwd_reason, real_cwd = validate_sandbox_path(exec_cwd)
    if not valid_cwd:
        audit.record(
            event_type="SECURITY_BLOCKED",
            caller="sandbox_runner",
            details={"command": command, "reason": cwd_reason, "cwd": str(exec_cwd)},
            risk_level="CRITICAL",
        )
        return {
            "status": "blocked",
            "error": cwd_reason,
            "exit_code": 126,
            "stdout": "",
            "stderr": f"Directory access denied: {cwd_reason}",
            "execution_time_ms": 0,
            "timed_out": False,
            "passed": False,
        }

    real_cwd.mkdir(parents=True, exist_ok=True)

    # 2. Phase 4 Policy Classification
    proposal = classify_action(
        command=command,
        cwd_subpath=cwd_subpath,
        files=files_affected,
        network_requested=bool(allow_network),
        secrets_requested=list(secrets.keys()) if secrets else None,
        custom_reason=rationale,
        timeout_sec=timeout_sec,
    )

    # 2A. ALWAYS_BLOCKED: Non-negotiable rejection (Human approval is NOT a bypass)
    if proposal.verdict == PolicyVerdict.ALWAYS_BLOCKED:
        audit.record(
            event_type="SECURITY_BLOCKED",
            caller="sandbox_runner",
            details={"command": command, "reason": proposal.reason},
            risk_level="CRITICAL",
        )
        return {
            "status": "blocked",
            "error": proposal.reason,
            "exit_code": 126,
            "stdout": "",
            "stderr": f"Command rejected: {proposal.reason}",
            "execution_time_ms": 0,
            "timed_out": False,
            "passed": False,
        }

    # 2B. APPROVAL_REQUIRED
    net_allowed = False
    approved_timeout = None
    if proposal.verdict == PolicyVerdict.APPROVAL_REQUIRED:
        if approval_token is None:
            # Need human operator authorization -> return approval gate response
            approval_mgr = get_approval_manager()
            approval_mgr._proposals[proposal.request_id] = proposal

            audit.record(
                event_type="APPROVAL_REQUESTED",
                caller="sandbox_runner",
                details={
                    "request_id": proposal.request_id,
                    "action": proposal.action,
                    "action_hash": proposal.action_hash,
                    "command": proposal.command,
                    "category": proposal.category.value,
                    "risk_level": proposal.risk_level.value,
                    "timeout_sec": proposal.timeout_sec,
                },
                risk_level=proposal.risk_level.value,
                request_id=proposal.request_id,
                action_hash=proposal.action_hash,
            )

            return {
                "status": "WAITING_FOR_HUMAN_APPROVAL",
                "passed": False,
                "exit_code": 126,
                "requires_approval": True,
                "request_id": proposal.request_id,
                "action_hash": proposal.action_hash,
                "proposal": proposal.model_dump(),
                "ui": proposal.ui_representation,
                "error": f"APPROVAL_REQUIRED: {proposal.reason}",
                "stdout": "",
                "stderr": proposal.ui_representation,
                "timed_out": False,
                "execution_time_ms": 0,
            }

        # Approval token provided -> verify and consume single-use token
        approval_mgr = get_approval_manager()
        req_id = (
            approval_token.request_id
            if hasattr(approval_token, "request_id")
            else approval_token.get("request_id", "")
        )
        valid_appr, appr_err = approval_mgr.verify_and_consume_approval(
            request_id=req_id,
            command=command,
            category=proposal.category.value,
            network=proposal.network_required,
            files=proposal.files_affected,
            secrets=proposal.secrets_required,
            timeout_sec=timeout_sec,
        )
        if not valid_appr:
            audit.record(
                event_type="SECURITY_BLOCKED",
                caller="sandbox_runner",
                details={"command": command, "reason": appr_err, "request_id": req_id},
                risk_level="HIGH",
            )
            return {
                "status": "APPROVAL_INVALID",
                "passed": False,
                "exit_code": 126,
                "error": appr_err,
                "stdout": "",
                "stderr": f"Approval verification failed: {appr_err}",
                "timed_out": False,
                "execution_time_ms": 0,
            }

        audit.record(
            event_type="ACTION_APPROVED",
            caller="sandbox_runner",
            details={
                "request_id": req_id,
                "action": proposal.action,
                "action_hash": proposal.action_hash,
                "command": proposal.command,
                "timeout_sec": proposal.timeout_sec,
            },
            risk_level="LOW",
            request_id=req_id,
            action_hash=proposal.action_hash,
        )
        net_allowed = proposal.network_required
        approved_timeout = proposal.timeout_sec
    else:
        # AUTO_ALLOWED
        net_allowed = False if allow_network is None else allow_network

    # 3. Validate command syntax and arguments
    effective_timeout = approved_timeout if approved_timeout is not None else timeout_sec
    is_allowed, denial_reason, args = validate_sandbox_command(
        command,
        approval_token=approval_token,
        timeout_sec=effective_timeout,
    )
    if not is_allowed:
        audit.record(
            event_type="SECURITY_BLOCKED",
            caller="sandbox_runner",
            details={"command": command, "reason": denial_reason},
            risk_level="HIGH",
        )
        return {
            "status": "blocked",
            "error": denial_reason,
            "exit_code": 126,
            "stdout": "",
            "stderr": f"Command rejected: {denial_reason}",
            "execution_time_ms": 0,
            "timed_out": False,
            "passed": False,
        }

    # 4. Resolve executable path cleanly (Dual runtime: Python / Node.js)
    binary_name = args[0].lower()
    if binary_name in {"python", "python3"}:
        venv_python = workspace / ".venv" / "bin" / "python"
        if venv_python.exists():
            args[0] = str(venv_python)
        else:
            args[0] = sys.executable
    elif binary_name == "pytest":
        venv_pytest = workspace / ".venv" / "bin" / "pytest"
        if venv_pytest.exists():
            args[0] = str(venv_pytest)
    elif binary_name in {"node", "npm", "npx"}:
        node_path = shutil.which(binary_name)
        if node_path:
            args[0] = node_path

    # For approved actions, execute using the exact approved timeout.
    # Otherwise, fallback to specified timeout_sec or settings default.
    timeout = (
        approved_timeout
        if approved_timeout and approved_timeout > 0
        else (timeout_sec if timeout_sec and timeout_sec > 0 else settings.SANDBOX_TIMEOUT_SEC)
    )
    env = _prepare_sanitized_env(allow_network=net_allowed)

    # Ephemeral secret injection into child process environment
    if secrets:
        for k, v in secrets.items():
            env[k] = v

    start_time = time.perf_counter()
    timed_out = False
    stdout = ""
    stderr = ""
    exit_code = 1

    try:
        process = subprocess.Popen(
            args,
            cwd=real_cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: _set_resource_limits(
                max_memory_mb=settings.SANDBOX_MAX_MEMORY_MB,
                max_nproc=settings.SANDBOX_MAX_NPROC,
                max_cpu_sec=timeout + 2,
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
            audit.record(
                event_type="TIMEOUT_TERMINATED",
                caller="sandbox_runner",
                details={"command": command, "timeout_sec": timeout},
                risk_level="MEDIUM",
            )
    except Exception as e:
        stderr = f"Subprocess launch failed: {str(e)}"
        exit_code = 1
    finally:
        # Scrub secret values immediately from parent process memory
        if secrets:
            for k in secrets:
                env.pop(k, None)

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # 5. Sanitize and redact output (strip tokens, API keys, and custom secrets)
    clean_stdout = sanitize_sandbox_output(stdout)
    clean_stderr = sanitize_sandbox_output(stderr)
    if secrets:
        for secret_val in secrets.values():
            if secret_val:
                clean_stdout = clean_stdout.replace(secret_val, "[REDACTED_SECRET]")
                clean_stderr = clean_stderr.replace(secret_val, "[REDACTED_SECRET]")

    # 6. Truncate output buffers to prevent memory exhaustion
    max_output = settings.SANDBOX_MAX_OUTPUT_BYTES
    if len(clean_stdout) > max_output:
        trunc_msg = f"\n... [TRUNCATED: Output exceeded {max_output} bytes] ..."
        clean_stdout = clean_stdout[:max_output] + trunc_msg

    if len(clean_stderr) > max_output:
        trunc_msg = f"\n... [TRUNCATED: Error output exceeded {max_output} bytes] ..."
        clean_stderr = clean_stderr[:max_output] + trunc_msg

    passed = exit_code == 0 and not timed_out
    result_status = "success" if passed else ("timeout" if timed_out else "failed")

    # 7. Record structured audit event
    audit.record(
        event_type="COMMAND_EXEC" if passed else "COMMAND_EXEC_FAILED",
        caller="sandbox_runner",
        details={
            "command": command,
            "exit_code": exit_code,
            "duration_ms": elapsed_ms,
            "timed_out": timed_out,
            "passed": passed,
            "network_enabled": net_allowed,
        },
        risk_level=proposal.risk_level.value if proposal else "LOW",
        request_id=proposal.request_id if proposal else None,
        action_hash=proposal.action_hash if proposal else None,
        network_capability=net_allowed,
        affected_files=proposal.files_affected if proposal else [],
    )

    return {
        "status": result_status,
        "command": command,
        "exit_code": exit_code,
        "stdout": clean_stdout,
        "stderr": clean_stderr,
        "execution_time_ms": elapsed_ms,
        "timed_out": timed_out,
        "passed": passed,
    }


def run_python_code(code: str, timeout_sec: int | None = None) -> dict[str, Any]:
    """
    Executes an ephemeral Python script inside the workspace sandbox cache.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    ephemeral_dir = workspace / ".sandbox_cache"
    ephemeral_dir.mkdir(parents=True, exist_ok=True)

    ephemeral_script = ephemeral_dir / f"ephemeral_{time.time_ns()}.py"
    try:
        ephemeral_script.write_text(code, encoding="utf-8")
        rel_script = str(ephemeral_script.relative_to(workspace))
        return execute_sandboxed_command(
            command=f"python {rel_script}",
            timeout_sec=timeout_sec,
        )
    finally:
        if ephemeral_script.exists():
            ephemeral_script.unlink()


def run_node_code(code: str, timeout_sec: int | None = None) -> dict[str, Any]:
    """
    Executes an ephemeral Node.js script inside the workspace sandbox cache.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    ephemeral_dir = workspace / ".sandbox_cache"
    ephemeral_dir.mkdir(parents=True, exist_ok=True)

    ephemeral_script = ephemeral_dir / f"ephemeral_{time.time_ns()}.js"
    try:
        ephemeral_script.write_text(code, encoding="utf-8")
        rel_script = str(ephemeral_script.relative_to(workspace))
        return execute_sandboxed_command(
            command=f"node {rel_script}",
            timeout_sec=timeout_sec,
        )
    finally:
        if ephemeral_script.exists():
            ephemeral_script.unlink()


def run_test_suite(
    framework: str = "pytest",
    target_path: str = "",
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    """
    Executes an automated test suite (pytest) inside the sandbox workspace.
    """
    target = f" {target_path}" if target_path else ""
    return execute_sandboxed_command(
        command=f"{framework}{target}",
        timeout_sec=timeout_sec,
    )
