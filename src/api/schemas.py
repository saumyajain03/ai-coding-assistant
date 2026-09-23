"""
FastAPI Request and Response Models for SentinelForge Platform API.
Guarantees strict schema validation for all endpoints.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Agent Tasks ---
class CreateTaskRequest(BaseModel):
    prompt: str = Field(..., min_length=3, description="Task prompt or bug description")
    target_file: str = Field(default="", description="Workspace relative path of target file")
    test_command: str = Field(default="", description="Test runner command to execute in sandbox")
    skip_rag: bool = Field(default=False, description="Whether to bypass local vector RAG")
    proposed_code: str | None = Field(default=None, description="Optional predetermined candidate code")
    active_documents: list[str] = Field(default_factory=list, description="Explicit list of active documents for this task")


class StepResultSchema(BaseModel):
    stage: str
    status: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class PatchProposalSchema(BaseModel):
    patch_id: str
    target_file: str
    rationale: str
    unified_diff: str
    lines_added: int
    lines_removed: int
    syntax_valid: bool
    syntax_error: str | None = None
    risk_score: int
    risk_notes: list[str] = Field(default_factory=list)
    status: str
    request_id: str
    action_hash: str
    created_at: float
    bundle_id: str | None = None
    is_new_file: bool = False
    files: list[dict[str, Any]] = Field(default_factory=list)


class TaskStatusResponse(BaseModel):
    task_id: str
    status: Literal["idle", "running", "waiting_approval", "approved", "rejected", "completed", "failed"]
    stages_executed: list[str] = Field(default_factory=list)
    current_stage: str | None = None
    step_results: dict[str, Any] = Field(default_factory=dict)
    analysis: str = ""
    plan: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    patch_proposal: PatchProposalSchema | None = None
    test_result: dict[str, Any] | None = None
    tests_passed: bool = False
    critique: str = ""
    final_report: str = ""
    error: str | None = None


# --- Human Approval ---
class PatchApprovalRequest(BaseModel):
    request_id: str = Field(..., description="Approval proposal request ID")
    action_hash: str = Field(..., description="Cryptographic SHA-256 action hash")
    action: Literal["approve", "reject"] = Field(..., description="Operator decision: 'approve' or 'reject'")
    reason: str | None = Field(default=None, description="Optional operator rationale")


class PatchApprovalResponse(BaseModel):
    status: str  # APPLIED, REJECTED, APPROVAL_INVALID
    approved: bool
    patch_id: str | None = None
    target_file: str | None = None
    test_result: dict[str, Any] | None = None
    final_report: dict[str, Any] | None = None
    error: str | None = None


# --- Sandbox On-Demand ---
class SandboxRunRequest(BaseModel):
    command: str = Field(..., min_length=1, description="Command to execute inside sandbox")
    timeout_sec: int | None = Field(default=15, description="Timeout in seconds")
    cwd_subpath: str = Field(default="", description="Workspace subpath")


class SandboxRunResponse(BaseModel):
    status: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    timed_out: bool
    passed: bool
    error: str | None = None


# --- System Health & Telemetry ---
class HealthResponse(BaseModel):
    app_name: str
    version: str
    status: str
    active_provider: str
    workspace_root: str
    sandbox_timeout_sec: int
    vector_index_ready: bool
    timestamp: float
