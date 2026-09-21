"""
Sandbox Security Engine
Enforces command allowlists, file extension restrictions, path traversal jails,
symlink escape mitigation, and scans outputs for secret exfiltration.
Integrates with the Phase 4 Permission Model (AUTO_ALLOWED, APPROVAL_REQUIRED, ALWAYS_BLOCKED).
"""

import os
import re
import shlex
import urllib.parse
from pathlib import Path
from typing import Any

from src.config import get_settings

# Allowed binaries in sandbox (Dual Runtime: Python & Node.js + git & package managers)
ALLOWED_COMMANDS = {
    "python",
    "python3",
    "pytest",
    "node",
    "npm",
    "npx",
    "git",
    "pip",
}

# Strictly forbidden command tokens, shells, network utilities, and escalations (ALWAYS_BLOCKED)
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

# Dangerous shell metacharacters when not properly tokenized
SHELL_METACHECK = re.compile(r"[;&|`$><]")

# Patterns for secret detection and redaction
KV_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|password|bearer|auth[_-]?token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?"
)
TOKEN_PATTERNS = [
    re.compile(r"ghp_[a-zA-Z0-9_]{20,}"),
    re.compile(r"sk-[a-zA-Z0-9_\-\.]{16,}"),
    re.compile(r"gsk_[a-zA-Z0-9_\-\.]{16,}"),
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{16,}", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(?:[A-Z\s]+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:[A-Z\s]+)?PRIVATE\s+KEY-----"),
    re.compile(r"ssh-rsa\s+AAAA[0-9A-Za-z+/]+={0,2}(?:\s+\S+)?"),
]


def validate_sandbox_path(target_path: Path | str) -> tuple[bool, str | None, Path]:
    """
    Validates that a path is strictly inside the workspace jail,
    resolving any symlinks to verify real filesystem location.
    Non-negotiable invariant: cannot be bypassed by human approval.

    Returns:
        (is_valid, denial_reason, resolved_path)
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    try:
        raw_str = urllib.parse.unquote(str(target_path))
        p = Path(raw_str)
        if not p.is_absolute():
            p = (workspace / p)
        # Resolve all symlinks to canonical real path
        real_path = Path(os.path.realpath(str(p)))

        if not settings.is_path_in_workspace(real_path):
            return (
                False,
                f"SECURITY_VIOLATION: Target path '{target_path}' resolves outside workspace jail ({real_path}).",
                real_path,
            )
        return True, None, real_path
    except Exception as e:
        return False, f"SECURITY_VIOLATION: Path resolution failed: {e}", workspace


def validate_sandbox_command(
    command: str,
    approval_token: Any | None = None,
    timeout_sec: int | None = None,
) -> tuple[bool, str | None, list[str]]:
    """
    Validates a command against the security allowlist, forbidden tokens,
    anti-traversal rules, and Phase 4 human approval policies.

    Returns:
        (is_allowed, denial_reason, parsed_args)
    """
    command_clean = command.strip()
    if not command_clean:
        return False, "Command is empty.", []

    # 1. Non-negotiable ALWAYS_BLOCKED check: forbidden tokens
    for token in FORBIDDEN_TOKENS:
        if re.search(rf"(?:^|\s|/){re.escape(token)}(?:$|\s|/)", command_clean):
            return (
                False,
                f"SECURITY_VIOLATION: Command contains forbidden token '{token}'.",
                [],
            )

    # 2. Tokenize command safely without invoking a shell
    try:
        args = shlex.split(command_clean)
    except Exception as e:
        return False, f"SECURITY_VIOLATION: Malformed command string: {e}", []

    if not args:
        return False, "No executable specified.", []

    # 3. Binary allowlist check
    binary = Path(args[0]).name.lower()
    if binary not in ALLOWED_COMMANDS:
        return (
            False,
            f"SECURITY_VIOLATION: Binary '{binary}' is not on the sandbox allowlist. Allowed: {sorted(ALLOWED_COMMANDS)}",
            [],
        )

    # 4. Path traversal & symlink jail validation on arguments
    skip_next = False
    for arg in args[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-c", "-e", "-m"}:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue

        arg_unquoted = urllib.parse.unquote(arg)
        valid, reason, _ = validate_sandbox_path(arg_unquoted)
        if not valid:
            return False, reason, []

    # 5. Git command policy (Read-only vs Mutating/Network)
    if binary == "git":
        allowed_git_subs = {"diff", "status", "log", "branch", "show"}
        sub = args[1].lower() if len(args) > 1 else ""

        if sub not in allowed_git_subs:
            # If an approval token is provided, verify it
            if approval_token is not None:
                from src.sandbox.policy import get_approval_manager

                req_id = (
                    approval_token.request_id
                    if hasattr(approval_token, "request_id")
                    else approval_token.get("request_id", "")
                )
                valid, err = get_approval_manager().verify_and_consume_approval(
                    request_id=req_id,
                    command=command_clean,
                    category="GIT_NETWORK" if sub in {"push", "pull", "fetch", "clone"} else "GIT_MUTATING",
                    network=sub in {"push", "pull", "fetch", "clone"},
                    timeout_sec=timeout_sec,
                )
                if not valid:
                    return False, f"SECURITY_VIOLATION: Approval verification failed: {err}", []
                return True, None, args

            return (
                False,
                f"SECURITY_VIOLATION: Mutating or network git command '{sub}' requires explicit human approval.",
                [],
            )

    # 6. Package Managers (npm, pip)
    if binary in {"npm", "pip"}:
        sub = args[1].lower() if len(args) > 1 else ""
        if sub in {"install", "i", "add", "uninstall", "remove"}:
            if approval_token is not None:
                from src.sandbox.policy import get_approval_manager

                req_id = (
                    approval_token.request_id
                    if hasattr(approval_token, "request_id")
                    else approval_token.get("request_id", "")
                )
                valid, err = get_approval_manager().verify_and_consume_approval(
                    request_id=req_id,
                    command=command_clean,
                    category="PACKAGE_INSTALL",
                    network=True,
                    timeout_sec=timeout_sec,
                )
                if not valid:
                    return False, f"SECURITY_VIOLATION: Approval verification failed: {err}", []
                return True, None, args

            return (
                False,
                f"SECURITY_VIOLATION: Package modification command '{command_clean}' requires explicit human approval.",
                [],
            )

    return True, None, args


def sanitize_sandbox_output(output: str, secrets_to_redact: list[str] | None = None) -> str:
    """
    Redacts detected secrets, credentials, or sensitive tokens from stdout/stderr.
    """
    if not output:
        return ""

    sanitized = output
    if secrets_to_redact:
        for s in secrets_to_redact:
            if s and len(s) >= 4:
                sanitized = sanitized.replace(s, "[REDACTED_SECRET]")

    sanitized = KV_SECRET_PATTERN.sub(r"\1: [REDACTED_SECRET]", sanitized)
    for pattern in TOKEN_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized
