"""
Structured Audit Logger for SentinelForge
Maintains an append-only in-memory and on-disk audit trail of all commands,
patch proposals, approvals, security rejections, and injection events.
"""

import time
from collections import deque
from typing import Any

from pydantic import BaseModel


class AuditEvent(BaseModel):
    timestamp: float
    iso_time: str
    event_type: str  # COMMAND_EXEC, PATCH_PROPOSED, PATCH_APPROVED, SECURITY_BLOCKED, INJECTION_DETECTED
    caller: str
    details: dict[str, Any]
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL


class AuditLogger:
    def __init__(self, max_events: int = 500):
        self.events: deque[AuditEvent] = deque(maxlen=max_events)

    def record(
        self,
        event_type: str,
        caller: str = "system",
        details: dict[str, Any] | None = None,
        risk_level: str = "LOW",
    ) -> AuditEvent:
        now = time.time()
        event = AuditEvent(
            timestamp=now,
            iso_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            event_type=event_type,
            caller=caller,
            details=details or {},
            risk_level=risk_level,
        )
        self.events.append(event)
        return event

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return [e.model_dump() for e in list(self.events)[-limit:]]

    def count(self) -> int:
        return len(self.events)


# Global singleton
_audit_logger_instance: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger_instance
    if _audit_logger_instance is None:
        _audit_logger_instance = AuditLogger()
    return _audit_logger_instance
