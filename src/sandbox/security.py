"""
Sandbox Security Engine
Enforces command allowlists, file extension restrictions, path traversal jails,
and scans outputs for potential secret exfiltration.
"""

import re
import shlex
from pathlib import Path

from src.config import get_settings

# Allowed binaries in sandbox
ALLOWED_COMMANDS = {
    "python",
    "python3",
    "pytest",
    "node",
    "npm",
    "git",
}

# Strictly forbidden command tokens
FORBIDDEN_TOKENS = {
    "curl",
    "wget",
    "nc",
    "netcat",
    "bash",
    "sh",
    "zsh",
    "sudo",
    "su",
    "eval",
    "chmod",
    "chown",
    "mkfifo",
    "rm -rf /",
    "/etc/passwd",
    "/etc/shadow",
    ".ssh",
    ".env",
}

# Regex for common secret formats (tokens, API keys, credentials)
KV_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|password|bearer|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?"
)
TOKEN_PATTERNS = [
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),
    re.compile(r"gsk_[a-zA-Z0-9]{32,}"),
]


def validate_sandbox_command(command: str) -> tuple[bool, str | None, list[str]]:
    """
    Validates a command against the security allowlist and anti-traversal rules.

    Returns:
        (is_allowed, denial_reason, parsed_args)
    """
    command_clean = command.strip()
    if not command_clean:
        return False, "Command is empty.", []

    # Check for raw forbidden tokens
    for token in FORBIDDEN_TOKENS:
        if token in command_clean:
            return (
                False,
                f"SECURITY_VIOLATION: Command contains forbidden token '{token}'.",
                [],
            )

    try:
        args = shlex.split(command_clean)
    except Exception as e:
        return False, f"Malformed command string: {e}", []

    if not args:
        return False, "No executable specified.", []

    binary = Path(args[0]).name.lower()
    if binary not in ALLOWED_COMMANDS:
        return (
            False,
            f"SECURITY_VIOLATION: Binary '{binary}' is not on the sandbox allowlist. Allowed: {sorted(ALLOWED_COMMANDS)}",
            [],
        )

    # Git subcommand check
    if binary == "git":
        if len(args) < 2 or args[1] not in {"diff", "status", "log", "branch"}:
            return (
                False,
                f"SECURITY_VIOLATION: Only safe git read commands (diff, status, log, branch) are allowed. Got '{args[1] if len(args) > 1 else ''}'.",
                [],
            )

    # Check for path traversal in command arguments
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    for arg in args[1:]:
        if ".." in arg:
            potential_path = (workspace / arg).resolve()
            if not settings.is_path_in_workspace(potential_path):
                return (
                    False,
                    f"SECURITY_VIOLATION: Argument '{arg}' attempts path traversal outside workspace.",
                    [],
                )

    return True, None, args


def sanitize_sandbox_output(output: str) -> str:
    """
    Redacts detected secrets or sensitive tokens from sandbox stdout/stderr.
    """
    sanitized = KV_SECRET_PATTERN.sub(r"\1: [REDACTED_SECRET]", output)
    for pattern in TOKEN_PATTERNS:
        sanitized = pattern.sub("[REDACTED_TOKEN]", sanitized)
    return sanitized
