"""
SentinelForge Phase 4 Security Permission & Policy Engine
Implements the Three-Way Action Classification:
1. AUTO_ALLOWED: Safe, read-only inspection, retrieval, and test execution.
2. APPROVAL_REQUIRED: Mutating, network, package-install, patch, and credentialed actions.
3. ALWAYS_BLOCKED: Sandbox escapes, symlink breakout, privilege escalation, policy tampering.

Enforces action-hash-bound single-use human approvals and prevents authorization replay or bundling.
"""

import hashlib
import json
import re
import shlex
import time
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings


class PolicyVerdict(StrEnum):
    AUTO_ALLOWED = "AUTO_ALLOWED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ALWAYS_BLOCKED = "ALWAYS_BLOCKED"


class ActionCategory(StrEnum):
    READ_ONLY = "READ_ONLY"
    WORKSPACE_WRITE = "WORKSPACE_WRITE"
    GIT_READ = "GIT_READ"
    GIT_MUTATING = "GIT_MUTATING"
    GIT_NETWORK = "GIT_NETWORK"
    NETWORK_REQUEST = "NETWORK_REQUEST"
    PACKAGE_INSTALL = "PACKAGE_INSTALL"
    PATCH_APPLICATION = "PATCH_APPLICATION"
    SECRET_ACCESS = "SECRET_ACCESS"
    SECRET_DISCLOSURE = "SECRET_DISCLOSURE"
    SYSTEM_ESCALATION = "SYSTEM_ESCALATION"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionProposal(BaseModel):
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    action: str
    command: str
    category: ActionCategory
    verdict: PolicyVerdict
    risk_level: RiskLevel
    reason: str
    network_required: bool = False
    files_affected: list[str] = Field(default_factory=list)
    secrets_required: list[str] = Field(default_factory=list)
    timeout_sec: int | None = None
    action_hash: str = ""
    requires_human_approval: bool = True
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, APPROVED, REJECTED, EXECUTED, BLOCKED
    ui_representation: str = ""
    created_at: float = Field(default_factory=time.time)

    def model_post_init(self, __context: Any) -> None:
        if not self.action_hash:
            self.action_hash = compute_action_hash(
                command=self.command,
                category=self.category.value,
                network=self.network_required,
                files=self.files_affected,
                secrets=self.secrets_required,
                timeout_sec=self.timeout_sec,
            )
        if not self.ui_representation:
            self.ui_representation = format_approval_ui(self)


class ApprovalToken(BaseModel):
    request_id: str
    action_hash: str
    approved: bool
    granted_at: float = Field(default_factory=time.time)
    nonce: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    consumed: bool = False
    rejection_reason: str | None = None


def compute_action_hash(
    command: str,
    category: str,
    network: bool = False,
    files: list[str] | None = None,
    secrets: list[str] | None = None,
    timeout_sec: int | None = None,
) -> str:
    """
    Computes a deterministic SHA-256 hash over the canonical action tuple.
    Ensures approval for 'git push origin main' cannot authorize 'git push origin production'
    or 'git push --force'.
    Includes the approved timeout to prevent reusing a 60s approval for 600s.
    """
    norm_cmd = " ".join(command.strip().split())
    norm_files = sorted(files or [])
    norm_secrets = sorted(secrets or [])
    settings = get_settings()
    effective_timeout = timeout_sec if timeout_sec and timeout_sec > 0 else settings.SANDBOX_TIMEOUT_SEC
    canonical = json.dumps(
        {
            "command": norm_cmd,
            "category": category,
            "network": bool(network),
            "files": norm_files,
            "secrets": norm_secrets,
            "timeout_sec": int(effective_timeout),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def format_approval_ui(proposal: ActionProposal) -> str:
    """Generates the human-readable approval card required by Section 4."""
    files_str = "\n".join(f"- {f}" for f in proposal.files_affected) if proposal.files_affected else "None"
    settings = get_settings()
    timeout_val = proposal.timeout_sec if proposal.timeout_sec and proposal.timeout_sec > 0 else settings.SANDBOX_TIMEOUT_SEC
    is_default = proposal.timeout_sec is None or proposal.timeout_sec == settings.SANDBOX_TIMEOUT_SEC
    timeout_label = f"{timeout_val}s{' (Default)' if is_default else ''}"

    return (
        "==================================================\n"
        "HUMAN APPROVAL REQUIRED\n"
        "==================================================\n"
        f"ACTION:\n{proposal.action}\n\n"
        f"WHY:\n{proposal.reason}\n\n"
        f"RISK:\n{proposal.risk_level.value} — Category: {proposal.category.value}\n\n"
        f"REQUESTED TIMEOUT:\n{timeout_label}\n\n"
        f"NETWORK:\n{'Required' if proposal.network_required else 'Disabled'}\n\n"
        f"FILES AFFECTED:\n{files_str}\n\n"
        f"PROPOSED COMMAND:\n{proposal.command}\n\n"
        f"REQUEST ID:\n{proposal.request_id}\n\n"
        f"ACTION HASH:\n{proposal.action_hash[:16]}...\n\n"
        "STATUS:\nWaiting for human approval.\n\n"
        "Possible actions:\n"
        "[Approve]  [Reject]\n"
        "=================================================="
    )


# Read-only Git subcommands (Safe without approval)
SAFE_GIT_SUBCOMMANDS = {"status", "diff", "log", "branch", "show"}

# Mutating Git subcommands requiring human approval
MUTATING_GIT_SUBCOMMANDS = {
    "commit": (ActionCategory.GIT_MUTATING, RiskLevel.MEDIUM),
    "checkout": (ActionCategory.GIT_MUTATING, RiskLevel.MEDIUM),
    "merge": (ActionCategory.GIT_MUTATING, RiskLevel.MEDIUM),
    "rebase": (ActionCategory.GIT_MUTATING, RiskLevel.HIGH),
    "reset": (ActionCategory.GIT_MUTATING, RiskLevel.HIGH),
    "tag": (ActionCategory.GIT_MUTATING, RiskLevel.LOW),
    "stash": (ActionCategory.GIT_MUTATING, RiskLevel.LOW),
}

# Network-oriented Git subcommands requiring human approval
NETWORK_GIT_SUBCOMMANDS = {
    "push": (ActionCategory.GIT_NETWORK, RiskLevel.HIGH),
    "pull": (ActionCategory.GIT_NETWORK, RiskLevel.HIGH),
    "fetch": (ActionCategory.GIT_NETWORK, RiskLevel.MEDIUM),
    "clone": (ActionCategory.GIT_NETWORK, RiskLevel.HIGH),
    "remote": (ActionCategory.GIT_NETWORK, RiskLevel.MEDIUM),
}

# Strictly forbidden tokens that violate the sandbox boundary
ALWAYS_BLOCKED_TOKENS = {
    "sudo",
    "su",
    "mkfifo",
    "eval",
    "/etc/passwd",
    "/etc/shadow",
    ".ssh",
    ".env",
    "rm -rf /",
    "chmod",
    "chown",
}


def classify_action(
    command: str,
    cwd_subpath: str = "",
    files: list[str] | None = None,
    network_requested: bool = False,
    secrets_requested: list[str] | None = None,
    custom_reason: str = "",
    category: ActionCategory | None = None,
    timeout_sec: int | None = None,
) -> ActionProposal:
    """
    Evaluates a command against the three-way security permission taxonomy:
    1. ALWAYS_BLOCKED
    2. APPROVAL_REQUIRED
    3. AUTO_ALLOWED
    """
    cmd_clean = command.strip()
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()

    # 0. Timeout validation: Reject proposals exceeding hard system maximum
    if timeout_sec is not None and timeout_sec > settings.SANDBOX_MAX_TIMEOUT_SEC:
        return ActionProposal(
            action=f"Blocked Command with excessive timeout: {timeout_sec}s",
            command=cmd_clean,
            category=ActionCategory.SYSTEM_ESCALATION,
            verdict=PolicyVerdict.ALWAYS_BLOCKED,
            risk_level=RiskLevel.CRITICAL,
            reason=(
                f"SECURITY_VIOLATION: Requested timeout {timeout_sec}s exceeds maximum allowed "
                f"system limit ({settings.SANDBOX_MAX_TIMEOUT_SEC}s)."
            ),
            timeout_sec=timeout_sec,
            requires_human_approval=False,
            status="BLOCKED",
        )

    # 1. Immediate ALWAYS_BLOCKED Checks (Escape & Escalation Primitives)
    for token in ALWAYS_BLOCKED_TOKENS:
        if re.search(rf"(?:^|\s|/){re.escape(token)}(?:$|\s|/)", cmd_clean):
            return ActionProposal(
                action=f"Blocked Command with forbidden token: '{token}'",
                command=cmd_clean,
                category=ActionCategory.SYSTEM_ESCALATION,
                verdict=PolicyVerdict.ALWAYS_BLOCKED,
                risk_level=RiskLevel.CRITICAL,
                reason=f"SECURITY_VIOLATION: Command contains forbidden sandbox-escape or escalation token '{token}'.",
                timeout_sec=timeout_sec,
                requires_human_approval=False,
                status="BLOCKED",
            )

    # Path traversal detection
    if ".." in cmd_clean or "/etc" in cmd_clean or "/var" in cmd_clean:
        # Check if arguments escape workspace
        try:
            tokens = shlex.split(cmd_clean)
            for t in tokens[1:]:
                if not t.startswith("-") and (".." in t or t.startswith("/")):
                    target = (workspace / t).resolve() if not Path(t).is_absolute() else Path(t).resolve()
                    if not settings.is_path_in_workspace(target):
                        return ActionProposal(
                            action=f"Blocked Path Traversal: '{t}'",
                            command=cmd_clean,
                            category=ActionCategory.SYSTEM_ESCALATION,
                            verdict=PolicyVerdict.ALWAYS_BLOCKED,
                            risk_level=RiskLevel.CRITICAL,
                            reason=f"SECURITY_VIOLATION: Target path '{t}' resolves outside workspace root ({target}).",
                            timeout_sec=timeout_sec,
                            requires_human_approval=False,
                            status="BLOCKED",
                        )
        except Exception:
            pass

    # Metacharacter injection detection for raw shells
    if re.search(r"[;`$><]", cmd_clean) and not (cmd_clean.startswith("python") or cmd_clean.startswith("node")):
        return ActionProposal(
            action=f"Blocked Metacharacters in: '{cmd_clean}'",
            command=cmd_clean,
            category=ActionCategory.SYSTEM_ESCALATION,
            verdict=PolicyVerdict.ALWAYS_BLOCKED,
            risk_level=RiskLevel.CRITICAL,
            reason="SECURITY_VIOLATION: Unescaped shell metacharacters detected.",
            requires_human_approval=False,
            status="BLOCKED",
        )

    try:
        args = shlex.split(cmd_clean)
    except Exception as e:
        return ActionProposal(
            action=f"Malformed command: '{cmd_clean}'",
            command=cmd_clean,
            category=ActionCategory.SYSTEM_ESCALATION,
            verdict=PolicyVerdict.ALWAYS_BLOCKED,
            risk_level=RiskLevel.CRITICAL,
            reason=f"SECURITY_VIOLATION: Malformed command string: {e}",
            requires_human_approval=False,
            status="BLOCKED",
        )

    if not args:
        return ActionProposal(
            action="Empty command",
            command="",
            category=ActionCategory.READ_ONLY,
            verdict=PolicyVerdict.ALWAYS_BLOCKED,
            risk_level=RiskLevel.LOW,
            reason="No command specified.",
            requires_human_approval=False,
            status="BLOCKED",
        )

    binary = Path(args[0]).name.lower()

    # Disallowed binary checks (e.g. bash, sh, zsh, curl, wget, nc)
    if binary in {"bash", "sh", "zsh", "curl", "wget", "nc", "netcat"}:
        return ActionProposal(
            action=f"Blocked Shell / Raw Network Binary: '{binary}'",
            command=cmd_clean,
            category=ActionCategory.SYSTEM_ESCALATION,
            verdict=PolicyVerdict.ALWAYS_BLOCKED,
            risk_level=RiskLevel.CRITICAL,
            reason=f"SECURITY_VIOLATION: Direct invocation of '{binary}' violates the sandbox containment boundary.",
            requires_human_approval=False,
            status="BLOCKED",
        )

    # Explicit category override (if caller pre-categorized the action, e.g. PATCH_APPLICATION)
    if category is not None:
        return ActionProposal(
            action=f"Action: '{cmd_clean}'",
            command=cmd_clean,
            category=category,
            verdict=PolicyVerdict.APPROVAL_REQUIRED,
            risk_level=RiskLevel.MEDIUM,
            reason=custom_reason or f"Action categorized as {category.value}.",
            network_required=network_requested,
            files_affected=files or [],
            secrets_required=secrets_requested or [],
            timeout_sec=timeout_sec,
            requires_human_approval=True,
            status="PENDING_APPROVAL",
        )

    # Git Policy Classification (Inspect before generic network so git push is GIT_NETWORK)
    if binary == "git":
        subcmd = args[1].lower() if len(args) > 1 else ""

        # Safe read-only Git
        if subcmd in SAFE_GIT_SUBCOMMANDS:
            return ActionProposal(
                action=f"Safe Git Read: 'git {subcmd}'",
                command=cmd_clean,
                category=ActionCategory.GIT_READ,
                verdict=PolicyVerdict.AUTO_ALLOWED,
                risk_level=RiskLevel.LOW,
                reason="Read-only repository state inspection.",
                timeout_sec=timeout_sec,
                requires_human_approval=False,
                status="APPROVED",
            )

        # Destructive Git Variants (CRITICAL Risk)
        if subcmd == "push" and any(flag in args for flag in ["--force", "-f", "+"]):
            return ActionProposal(
                action="Force Push to Remote Repository",
                command=cmd_clean,
                category=ActionCategory.GIT_NETWORK,
                verdict=PolicyVerdict.APPROVAL_REQUIRED,
                risk_level=RiskLevel.CRITICAL,
                reason=custom_reason or "Force-pushing may overwrite remote git history destructively.",
                network_required=True,
                files_affected=files or [],
                secrets_required=secrets_requested or [],
                timeout_sec=timeout_sec,
                requires_human_approval=True,
                status="PENDING_APPROVAL",
            )
        if subcmd == "reset" and any(flag in args for flag in ["--hard"]):
            return ActionProposal(
                action="Hard Reset Working Tree",
                command=cmd_clean,
                category=ActionCategory.GIT_MUTATING,
                verdict=PolicyVerdict.APPROVAL_REQUIRED,
                risk_level=RiskLevel.CRITICAL,
                reason=custom_reason or "Hard reset discards uncommitted workspace modifications permanently.",
                files_affected=files or [],
                secrets_required=secrets_requested or [],
                timeout_sec=timeout_sec,
                requires_human_approval=True,
                status="PENDING_APPROVAL",
            )

        # Network Git commands
        if subcmd in NETWORK_GIT_SUBCOMMANDS:
            cat, risk = NETWORK_GIT_SUBCOMMANDS[subcmd]
            return ActionProposal(
                action=f"Network Git Operation: 'git {subcmd}'",
                command=cmd_clean,
                category=cat,
                verdict=PolicyVerdict.APPROVAL_REQUIRED,
                risk_level=risk,
                reason=custom_reason or f"Executing 'git {subcmd}' transmits data to/from remote repository.",
                network_required=True,
                files_affected=files or [],
                secrets_required=secrets_requested or [],
                timeout_sec=timeout_sec,
                requires_human_approval=True,
                status="PENDING_APPROVAL",
            )

        # Mutating Git commands
        if subcmd in MUTATING_GIT_SUBCOMMANDS:
            cat, risk = MUTATING_GIT_SUBCOMMANDS[subcmd]
            return ActionProposal(
                action=f"Mutating Git Operation: 'git {subcmd}'",
                command=cmd_clean,
                category=cat,
                verdict=PolicyVerdict.APPROVAL_REQUIRED,
                risk_level=risk,
                reason=custom_reason or f"Executing 'git {subcmd}' mutates local repository tracking state.",
                network_required=network_requested,
                files_affected=files or [],
                secrets_required=secrets_requested or [],
                timeout_sec=timeout_sec,
                requires_human_approval=True,
                status="PENDING_APPROVAL",
            )

        # Unknown Git subcommand -> defaults to approval required
        return ActionProposal(
            action=f"Git Operation: 'git {subcmd}'",
            command=cmd_clean,
            category=ActionCategory.GIT_MUTATING,
            verdict=PolicyVerdict.APPROVAL_REQUIRED,
            risk_level=RiskLevel.HIGH,
            reason=custom_reason or f"Git subcommand '{subcmd}' modifies repository state.",
            network_required=network_requested,
            files_affected=files or [],
            secrets_required=secrets_requested or [],
            timeout_sec=timeout_sec,
            requires_human_approval=True,
            status="PENDING_APPROVAL",
        )

    # Patch Application Detection
    if binary in {"patch", "apply_patch"} or cmd_clean.startswith("apply_patch"):
        return ActionProposal(
            action=f"Apply Code Patch: '{cmd_clean}'",
            command=cmd_clean,
            category=ActionCategory.PATCH_APPLICATION,
            verdict=PolicyVerdict.APPROVAL_REQUIRED,
            risk_level=RiskLevel.MEDIUM,
            reason=custom_reason or "Applying code patch modifies workspace files.",
            network_required=network_requested,
            files_affected=files or [],
            secrets_required=secrets_requested or [],
            timeout_sec=timeout_sec,
            requires_human_approval=True,
            status="PENDING_APPROVAL",
        )

    # Secret Access Requested
    if secrets_requested:
        return ActionProposal(
            action="Execute Command with Injected Secret",
            command=cmd_clean,
            category=ActionCategory.SECRET_ACCESS,
            verdict=PolicyVerdict.APPROVAL_REQUIRED,
            risk_level=RiskLevel.HIGH,
            reason=custom_reason or f"Command requires temporary credential access for: {secrets_requested}",
            network_required=network_requested,
            files_affected=files or [],
            secrets_required=secrets_requested,
            timeout_sec=timeout_sec,
            requires_human_approval=True,
            status="PENDING_APPROVAL",
        )

    # Network Capability Requested
    if network_requested:
        return ActionProposal(
            action="Enable Ephemeral Network Access for Command",
            command=cmd_clean,
            category=ActionCategory.NETWORK_REQUEST,
            verdict=PolicyVerdict.APPROVAL_REQUIRED,
            risk_level=RiskLevel.HIGH,
            reason=custom_reason or "The requested task legitimately requires outbound network connectivity.",
            network_required=True,
            files_affected=files or [],
            secrets_required=secrets_requested or [],
            timeout_sec=timeout_sec,
            requires_human_approval=True,
            status="PENDING_APPROVAL",
        )

    # 5. Package Managers (pip, npm)
    if binary in {"npm", "npx", "pip"} or (binary in {"python", "python3"} and len(args) > 2 and args[1] == "-m" and args[2] == "pip"):
        is_install = any(sub in args for sub in ["install", "i", "add", "uninstall", "remove"])
        if is_install:
            return ActionProposal(
                action=f"Package Management: '{cmd_clean}'",
                command=cmd_clean,
                category=ActionCategory.PACKAGE_INSTALL,
                verdict=PolicyVerdict.APPROVAL_REQUIRED,
                risk_level=RiskLevel.HIGH,
                reason=custom_reason or "Installing or modifying packages alters runtime environment dependencies.",
                network_required=True,
                timeout_sec=timeout_sec,
                requires_human_approval=True,
                status="PENDING_APPROVAL",
            )

    # 6. Test Runners & Safe Python / Node Execution
    if binary == "pytest":
        return ActionProposal(
            action=f"Execute Test Suite: '{cmd_clean}'",
            command=cmd_clean,
            category=ActionCategory.READ_ONLY,
            verdict=PolicyVerdict.AUTO_ALLOWED,
            risk_level=RiskLevel.LOW,
            reason="Sandboxed automated unit test execution.",
            timeout_sec=timeout_sec,
            requires_human_approval=False,
            status="APPROVED",
        )

    if binary in {"python", "python3", "node"}:
        # Check for inline code or script
        # If running a safe one-liner or test script inside workspace
        return ActionProposal(
            action=f"Sandboxed Code Execution: '{cmd_clean}'",
            command=cmd_clean,
            category=ActionCategory.READ_ONLY,
            verdict=PolicyVerdict.AUTO_ALLOWED,
            risk_level=RiskLevel.LOW,
            reason="Standard isolated script or expression evaluation.",
            timeout_sec=timeout_sec,
            requires_human_approval=False,
            status="APPROVED",
        )

    # Fallback default: Any unknown or unclassified binary requires human approval
    return ActionProposal(
        action=f"Execute Command: '{cmd_clean}'",
        command=cmd_clean,
        category=ActionCategory.WORKSPACE_WRITE,
        verdict=PolicyVerdict.APPROVAL_REQUIRED,
        risk_level=RiskLevel.HIGH,
        reason=custom_reason or f"Command '{binary}' requires human authorization prior to execution.",
        timeout_sec=timeout_sec,
        requires_human_approval=True,
        status="PENDING_APPROVAL",
    )


class ApprovalManager:
    """
    Manages pending proposals and issues cryptographic single-use approval tokens.
    Guarantees that an approval for 'git push origin main' cannot authorize any other command.
    """

    def __init__(self):
        self._proposals: dict[str, ActionProposal] = {}
        self._tokens: dict[str, ApprovalToken] = {}

    def create_proposal(
        self,
        command: str,
        files: list[str] | None = None,
        network_requested: bool = False,
        secrets_requested: list[str] | None = None,
        reason: str = "",
        category: ActionCategory | None = None,
        timeout_sec: int | None = None,
    ) -> ActionProposal:
        proposal = classify_action(
            command=command,
            files=files,
            network_requested=network_requested,
            secrets_requested=secrets_requested,
            custom_reason=reason,
            category=category,
            timeout_sec=timeout_sec,
        )
        self._proposals[proposal.request_id] = proposal
        return proposal

    def get_proposal(self, request_id: str) -> ActionProposal | None:
        return self._proposals.get(request_id)

    def submit_approval(
        self,
        request_id: str,
        action_hash: str,
        approved: bool,
        rejection_reason: str | None = None,
    ) -> ApprovalToken:
        proposal = self._proposals.get(request_id)
        if not proposal:
            raise ValueError(f"Unknown proposal request_id: '{request_id}'")

        if proposal.action_hash != action_hash:
            raise ValueError(
                f"ACTION_HASH_MISMATCH: Provided hash '{action_hash}' does not match proposal hash '{proposal.action_hash}'."
            )

        token = ApprovalToken(
            request_id=request_id,
            action_hash=action_hash,
            approved=approved,
            rejection_reason=rejection_reason if not approved else None,
        )
        self._tokens[request_id] = token
        proposal.status = "APPROVED" if approved else "REJECTED"
        return token

    def verify_and_consume_approval(
        self,
        request_id: str,
        command: str,
        category: str,
        network: bool = False,
        files: list[str] | None = None,
        secrets: list[str] | None = None,
        timeout_sec: int | None = None,
    ) -> tuple[bool, str | None]:
        """
        Validates the approval token against the current execution parameters and consumes it.
        Returns:
            (is_valid, failure_reason)
        """
        token = self._tokens.get(request_id)
        if not token:
            return False, f"APPROVAL_NOT_FOUND: No approval token found for request_id '{request_id}'."

        if token.consumed:
            return False, "APPROVAL_ALREADY_USED: This approval token has already been consumed (single-use policy)."

        if not token.approved:
            return False, f"APPROVAL_REJECTED: Action was rejected by human operator ({token.rejection_reason or 'No reason'})."

        # Compute current action hash with exact execution timeout
        current_hash = compute_action_hash(
            command=command,
            category=category,
            network=network,
            files=files,
            secrets=secrets,
            timeout_sec=timeout_sec,
        )

        if token.action_hash != current_hash:
            return False, (
                f"ACTION_HASH_MISMATCH: Approved action hash '{token.action_hash[:12]}' "
                f"does not match current execution hash '{current_hash[:12]}'. "
                "The command or parameters (including timeout) were modified after approval was granted."
            )

        # Consume token
        token.consumed = True
        return True, None

    def clear(self) -> None:
        self._proposals.clear()
        self._tokens.clear()


# Global Singleton
_approval_manager: ApprovalManager | None = None


def get_approval_manager() -> ApprovalManager:
    global _approval_manager
    if _approval_manager is None:
        _approval_manager = ApprovalManager()
    return _approval_manager
