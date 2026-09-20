"""
Structured Audit Logger for SentinelForge
Maintains an append-only in-memory and on-disk audit trail of all commands,
action proposals, human approvals, security rejections, and injection events.
Enforces strict secret redaction on all recorded telemetry.
"""

import json
import time
from collections import deque
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings
from src.sandbox.security import sanitize_sandbox_output


class AuditEvent(BaseModel):
    timestamp: float
    iso_time: str
    event_type: str  # COMMAND_EXEC, APPROVAL_REQUESTED, ACTION_APPROVED, PATCH_PROPOSED, SECURITY_BLOCKED, TIMEOUT_TERMINATED
    caller: str
    details: dict[str, Any]
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    request_id: str | None = None
    action_hash: str | None = None
    network_capability: bool = False
    affected_files: list[str] = Field(default_factory=list)


def _deep_sanitize_dict(obj: Any) -> Any:
    """Recursively redacts secrets from dictionary values, lists, and strings."""
    if isinstance(obj, str):
        return sanitize_sandbox_output(obj)
    elif isinstance(obj, dict):
        return {k: _deep_sanitize_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deep_sanitize_dict(v) for v in obj]
    return obj


class AuditLogger:
    def __init__(self, max_events: int = 1000):
        self.events: deque[AuditEvent] = deque(maxlen=max_events)
        settings = get_settings()
        self.log_file = settings.SCRATCH_DIR / "audit_log.jsonl"
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def record(
        self,
        event_type: str,
        caller: str = "sandbox",
        details: dict[str, Any] | None = None,
        risk_level: str = "LOW",
        request_id: str | None = None,
        action_hash: str | None = None,
        network_capability: bool = False,
        affected_files: list[str] | None = None,
    ) -> AuditEvent:
        now = time.time()
        # Ensure deep sanitization so secrets are NEVER persisted to disk
        sanitized_details = _deep_sanitize_dict(details or {})

        event = AuditEvent(
            timestamp=now,
            iso_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            event_type=event_type,
            caller=caller,
            details=sanitized_details,
            risk_level=risk_level,
            request_id=request_id or sanitized_details.get("request_id"),
            action_hash=action_hash or sanitized_details.get("action_hash"),
            network_capability=network_capability or sanitized_details.get("network_required", False),
            affected_files=affected_files or sanitized_details.get("files_affected", []),
        )
        self.events.append(event)

        # Append to disk log
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.model_dump()) + "\n")
        except Exception:
            pass

        return event

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return [e.model_dump() for e in list(self.events)[-limit:]]

    def count(self) -> int:
        return len(self.events)

    def clear(self) -> None:
        self.events.clear()
        if self.log_file.exists():
            try:
                self.log_file.unlink()
            except Exception:
                pass


# Global singleton
_audit_logger_instance: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger_instance
    if _audit_logger_instance is None:
        _audit_logger_instance = AuditLogger()
    return _audit_logger_instance
