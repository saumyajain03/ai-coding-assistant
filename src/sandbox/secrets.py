"""
SentinelForge Secret Management & Disclosure Control Module
Enforces:
1. Secure secret request workflow (emits structured SecretRequest).
2. Ephemeral in-memory secret injection (secrets exist only during child process execution).
3. Secret Discovery vs Secret Disclosure distinction (returns code references, never raw secrets).
4. High-risk confirmation challenges for explicit secret disclosure.
"""

import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings


class SecretRequest(BaseModel):
    type: str = "secret_request"
    secret_name: str
    reason: str
    execution_scope: str = "current_task"
    requested_at: float = Field(default_factory=lambda: __import__("time").time())


class SecretDisclosureChallenge(BaseModel):
    challenge_type: str = "HIGH_RISK_SECRET_DISCLOSURE"
    secret_name: str
    warning: str = (
        "You're requesting disclosure of a credential value. "
        "This will expose the secret in the conversation and may persist in chat history. Continue?"
    )
    confirmed: bool = False


class SecretVault:
    """
    Ephemeral in-memory vault for user-provided secrets.
    Secrets are never persisted to disk, never logged in plaintext,
    and scrubbed from memory after single-command execution.
    """

    def __init__(self):
        self._secrets: dict[str, str] = {}

    def supply_secret(self, secret_name: str, secret_value: str) -> None:
        """Stores a secret temporarily for the current execution."""
        clean_name = secret_name.strip()
        clean_val = secret_value.strip()
        self._secrets[clean_name] = clean_val

    def get_secret(self, secret_name: str) -> str | None:
        return self._secrets.get(secret_name.strip())

    def pop_secrets(self) -> dict[str, str]:
        """Consumes all pending secrets for single execution and clears the vault."""
        consumed = dict(self._secrets)
        self._secrets.clear()
        return consumed

    def clear(self) -> None:
        self._secrets.clear()


_secret_vault: SecretVault | None = None


def get_secret_vault() -> SecretVault:
    global _secret_vault
    if _secret_vault is None:
        _secret_vault = SecretVault()
    return _secret_vault


def request_secret(secret_name: str, reason: str, scope: str = "current_task") -> dict[str, Any]:
    """Emits the structured secret request required by Section 7."""
    req = SecretRequest(
        secret_name=secret_name,
        reason=reason,
        execution_scope=scope,
    )
    return req.model_dump()


def inspect_secret_references(query: str, repo_path: Path | None = None) -> dict[str, Any]:
    """
    Section 8: Secret Discovery vs. Disclosure.
    When asked 'Where are API keys used in this project?', returns code and configuration
    references, NOT secret values.
    """
    settings = get_settings()
    if repo_path:
        search_roots = [Path(repo_path).resolve()]
    else:
        search_roots = [
            Path("src").resolve(),
            Path("data/manual_test/code_repo").resolve(),
            Path(settings.WORKSPACE_ROOT).resolve(),
        ]

    references: list[dict[str, Any]] = []

    # Common credential symbols to search for
    key_patterns = [
        re.compile(r"\b(OPENAI_API_KEY|ANTHROPIC_API_KEY|GROQ_API_KEY|GITHUB_TOKEN|API_KEY|SECRET_KEY)\b"),
        re.compile(r"\b(api_key|access_token|auth_token|secret_key)\b", re.IGNORECASE),
    ]

    target_extensions = {".py", ".json", ".md", ".env.example", ".txt", ".js", ".ts"}
    cwd = Path.cwd().resolve()

    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in target_extensions:
                # Skip hidden files or test caches
                if any(part.startswith(".") and part != ".env.example" for part in path.parts):
                    continue
                if "__pycache__" in path.parts or ".venv" in path.parts:
                    continue
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                    for idx, line in enumerate(lines, start=1):
                        for pat in key_patterns:
                            match = pat.search(line)
                            if match:
                                symbol = match.group(0)
                                try:
                                    rel_file = str(path.relative_to(cwd))
                                except ValueError:
                                    rel_file = str(path.relative_to(root)) if root in path.parents else path.name
                                references.append({
                                    "symbol": symbol,
                                    "file": rel_file,
                                    "line_number": idx,
                                    "citation": f"{rel_file}:L{idx}",
                                    "context": line.strip()[:100],
                                })
                                break
                except Exception:
                    pass

    return {
        "query": query,
        "disclosure_type": "REFERENCE_DISCOVERY",
        "reference_count": len(references),
        "references": references[:25],
        "notice": (
            "This inspection returns code configuration references and source locations only. "
            "Raw secret values are never displayed during reference discovery."
        ),
    }


def create_secret_disclosure_challenge(secret_name: str) -> dict[str, Any]:
    """
    Section 9: Explicit Secret Disclosure.
    Requires separate confirmation challenge before exposing a secret value.
    """
    challenge = SecretDisclosureChallenge(secret_name=secret_name)
    return challenge.model_dump()


def reveal_secret_if_confirmed(
    secret_name: str,
    confirmation_token: bool = False,
) -> dict[str, Any]:
    """
    Reveals a secret only after explicit confirmation challenge is confirmed.
    """
    vault = get_secret_vault()
    if not confirmation_token:
        return {
            "status": "CONFIRMATION_REQUIRED",
            "challenge": create_secret_disclosure_challenge(secret_name),
            "revealed": False,
        }

    secret_val = vault.get_secret(secret_name) or os.environ.get(secret_name)
    if not secret_val:
        return {
            "status": "NOT_FOUND",
            "secret_name": secret_name,
            "revealed": False,
            "message": f"No secret found with identifier '{secret_name}'.",
        }

    return {
        "status": "DISCLOSED_AFTER_CONFIRMATION",
        "secret_name": secret_name,
        "value": secret_val,
        "revealed": True,
        "warning": "Credential disclosed in plaintext following explicit confirmation.",
    }
