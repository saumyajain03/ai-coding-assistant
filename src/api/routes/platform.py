"""
FastAPI Route Handlers for SentinelForge Platform API.
Routes:
- POST /api/v1/chat: Dispatches an agent task using the existing 7-stage AgentLoop.
- GET  /api/v1/tasks/{task_id}: Retrieves live execution state, stage progression, diff, and reports.
- POST /api/v1/patches/action: Submits explicit Human Approval via ApprovalManager & apply_patch_tool.
- POST /api/v1/sandbox/run: Runs on-demand commands through execute_sandboxed_command.
- GET  /api/v1/health: System health and runtime telemetry.
- GET  /api/v1/audit: Retrieves the structured audit trail from AuditLogger.
"""

import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from src.agent.loop import AgentExecutionReport, AgentLoop
from src.api.schemas import (
    CreateTaskRequest,
    HealthResponse,
    PatchApprovalRequest,
    PatchApprovalResponse,
    PatchProposalSchema,
    SandboxRunRequest,
    SandboxRunResponse,
    TaskStatusResponse,
)
from src.config import get_settings
from src.mcp_server.tools.patch import _pending_patches, apply_patch_tool
from src.rag.indexer import RAGIndexer
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import get_approval_manager
from src.sandbox.runner import execute_sandboxed_command

router = APIRouter(prefix="/api/v1", tags=["SentinelForge Platform"])

# In-memory execution registry for tasks
_active_tasks: dict[str, dict[str, Any]] = {}


@router.post("/chat", response_model=dict[str, str], status_code=202)
async def start_agent_task(
    payload: CreateTaskRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Initiates an asynchronous agent task through the 7-stage AgentLoop.
    Task state can be polled or inspected via GET /api/v1/tasks/{task_id}.
    """
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task_entry: dict[str, Any] = {
        "task_id": task_id,
        "status": "running",
        "task_prompt": payload.prompt,
        "target_file": payload.target_file,
        "test_command": payload.test_command,
        "stages_executed": [],
        "current_stage": "analysis",
        "step_results": {},
        "analysis": "",
        "plan": "",
        "citations": [],
        "patch_proposal": None,
        "test_result": None,
        "tests_passed": False,
        "critique": "",
        "final_report": "",
        "error": None,
        "created_at": time.time(),
    }
    _active_tasks[task_id] = task_entry

    # Execute orchestrator loop
    async def _run_loop():
        loop = AgentLoop()
        try:
            report: AgentExecutionReport = await loop.run(
                task=payload.prompt,
                target_file=payload.target_file,
                test_command=payload.test_command,
                proposed_code=payload.proposed_code,
                skip_rag=payload.skip_rag,
            )

            task_entry["stages_executed"] = [s.value for s in report.stages_executed]
            task_entry["step_results"] = {
                k: v.model_dump() for k, v in report.step_results.items()
            }
            task_entry["analysis"] = report.analysis
            task_entry["plan"] = report.plan
            task_entry["citations"] = report.retrieved_citations
            task_entry["test_result"] = report.test_result
            task_entry["tests_passed"] = report.tests_passed
            task_entry["critique"] = report.critique
            task_entry["final_report"] = report.final_report

            if report.patch_result:
                task_entry["patch_proposal"] = {
                    "patch_id": report.patch_result.patch_id,
                    "target_file": report.patch_result.target_file,
                    "rationale": report.patch_result.rationale,
                    "unified_diff": report.patch_result.unified_diff,
                    "lines_added": report.patch_result.lines_added,
                    "lines_removed": report.patch_result.lines_removed,
                    "syntax_valid": report.patch_result.syntax_valid,
                    "syntax_error": report.patch_result.syntax_error,
                    "risk_score": report.patch_result.risk_score,
                    "risk_notes": report.patch_result.risk_notes,
                    "status": report.patch_result.status,
                    "request_id": report.patch_result.request_id,
                    "action_hash": report.patch_result.action_hash,
                    "created_at": report.patch_result.created_at,
                }
                # Check if waiting for approval
                if report.patch_result.status == "PENDING_APPROVAL":
                    task_entry["status"] = "waiting_approval"
                else:
                    task_entry["status"] = "completed" if report.tests_passed else "failed"
            else:
                task_entry["status"] = "completed"

        except Exception as e:
            task_entry["status"] = "failed"
            task_entry["error"] = str(e)

    # Launch task in background
    background_tasks.add_task(_run_loop)

    return {"task_id": task_id, "status": "accepted"}


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Retrieves the execution status, telemetry, patch proposal, and report of a task.
    Supports clean lookup with whitespace/quote sanitization.
    """
    clean_id = task_id.strip().strip('"\'')
    task = _active_tasks.get(clean_id)
    if not task:
        # Also check without 'task_' prefix if user passed just the hex string, or vice versa
        if clean_id.startswith("task_"):
            alt_id = clean_id[5:]
        else:
            alt_id = f"task_{clean_id}"
        task = _active_tasks.get(alt_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    patch_prop = None
    if task.get("patch_proposal"):
        patch_prop = PatchProposalSchema(**task["patch_proposal"])

    return TaskStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        stages_executed=task.get("stages_executed", []),
        current_stage=task.get("current_stage"),
        step_results=task.get("step_results", {}),
        analysis=task.get("analysis", ""),
        plan=task.get("plan", ""),
        citations=task.get("citations", []),
        patch_proposal=patch_prop,
        test_result=task.get("test_result"),
        tests_passed=task.get("tests_passed", False),
        critique=task.get("critique", ""),
        final_report=task.get("final_report", ""),
        error=task.get("error"),
    )


@router.post("/patches/action", response_model=PatchApprovalResponse)
async def submit_patch_action(payload: PatchApprovalRequest) -> PatchApprovalResponse:
    """
    Submits a Human-in-the-Loop decision ('approve' or 'reject') for a pending patch proposal.
    Guarantees that unapproved patches are NEVER applied to disk.
    """
    approval_mgr = get_approval_manager()
    proposal = approval_mgr.get_proposal(payload.request_id)
    if not proposal:
        raise HTTPException(
            status_code=404,
            detail=f"Approval request '{payload.request_id}' not found in registry.",
        )

    # Verify action hash before granting approval
    if proposal.action_hash != payload.action_hash:
        raise HTTPException(
            status_code=400,
            detail=f"ACTION_HASH_MISMATCH: Provided hash '{payload.action_hash}' does not match registered hash '{proposal.action_hash}'.",
        )

    # If rejected by human operator
    if payload.action == "reject":
        token = approval_mgr.submit_approval(
            request_id=payload.request_id,
            action_hash=payload.action_hash,
            approved=False,
            rejection_reason=payload.reason or "Rejected by human operator via API",
        )
        # Update any corresponding task in the registry
        for t in _active_tasks.values():
            if t.get("patch_proposal") and t["patch_proposal"].get("request_id") == payload.request_id:
                t["status"] = "rejected"
                t["patch_proposal"]["status"] = "REJECTED"

        return PatchApprovalResponse(
            status="REJECTED",
            approved=False,
            error=token.rejection_reason,
        )

    # Operator approved: generate cryptographic token bound to action hash
    token = approval_mgr.submit_approval(
        request_id=payload.request_id,
        action_hash=payload.action_hash,
        approved=True,
    )

    # Find the patch_id associated with this request
    target_patch_id = None
    target_file = None
    for pid, entry in _pending_patches.items():
        if entry.get("request_id") == payload.request_id:
            target_patch_id = pid
            target_file = entry.get("target_file")
            break

    if not target_patch_id:
        raise HTTPException(
            status_code=404,
            detail=f"No pending patch found matching request ID '{payload.request_id}'.",
        )

    # Find if there is an associated test_command in active tasks
    test_cmd = ""
    associated_task = None
    for t in _active_tasks.values():
        if t.get("patch_proposal") and t["patch_proposal"].get("request_id") == payload.request_id:
            test_cmd = t.get("test_command", "")
            associated_task = t
            break

    # Apply patch using existing apply_patch_tool with token
    apply_res = apply_patch_tool(
        patch_id=target_patch_id,
        approval_token=token.model_dump(),
        test_command=test_cmd,
    )

    if apply_res.get("status") != "APPLIED":
        return PatchApprovalResponse(
            status=apply_res.get("status", "failed"),
            approved=False,
            error=apply_res.get("error", "Failed to apply approved patch"),
        )

    # Update active task state if found
    if associated_task:
        associated_task["status"] = "completed" if apply_res.get("final_report", {}).get("tests_passed", True) else "failed"
        associated_task["patch_proposal"]["status"] = "APPLIED"
        if apply_res.get("test_result"):
            associated_task["test_result"] = apply_res.get("test_result")
            associated_task["tests_passed"] = bool(apply_res.get("test_result", {}).get("passed", False))

    return PatchApprovalResponse(
        status="APPLIED",
        approved=True,
        patch_id=target_patch_id,
        target_file=target_file,
        test_result=apply_res.get("test_result"),
        final_report=apply_res.get("final_report"),
    )


@router.post("/sandbox/run", response_model=SandboxRunResponse)
async def run_sandbox_command_endpoint(payload: SandboxRunRequest) -> SandboxRunResponse:
    """
    Executes a command inside the isolated workspace sandbox with Phase 3 & 4 policy checks.
    ALWAYS_BLOCKED commands are rejected immediately regardless of parameters.
    """
    result = execute_sandboxed_command(
        command=payload.command,
        timeout_sec=payload.timeout_sec,
        cwd_subpath=payload.cwd_subpath,
    )

    return SandboxRunResponse(
        status=result.get("status", "failed"),
        command=payload.command,
        exit_code=result.get("exit_code", -1),
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        execution_time_ms=result.get("execution_time_ms", 0.0),
        timed_out=result.get("timed_out", False),
        passed=result.get("passed", False),
        error=result.get("error"),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Returns platform health, active LLM provider, and sandbox boundaries.
    """
    settings = get_settings()
    return HealthResponse(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        status="healthy",
        active_provider=settings.LLM_PROVIDER,
        workspace_root=str(settings.WORKSPACE_ROOT),
        sandbox_timeout_sec=settings.SANDBOX_TIMEOUT_SEC,
        vector_index_ready=True,
        timestamp=time.time(),
    )


@router.get("/audit", response_model=list[dict[str, Any]])
async def get_audit_trail(limit: int = 50) -> list[dict[str, Any]]:
    """
    Exposes the structured, append-only security audit log stream.
    """
    audit = get_audit_logger()
    return audit.get_recent_events(limit=limit)


@router.post("/upload", response_model=list[dict[str, Any]])
async def upload_documents(files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:  # noqa: B008
    """
    Uploads and indexes documents (.pdf, .md, .py, .js, .ts) into the RAG vector and lexical stores.
    Delegates strictly to the existing RAGIndexer without duplicating logic.
    """
    allowed_exts = {".pdf", ".md", ".py", ".js", ".ts"}
    indexer = RAGIndexer()
    results = []

    for uploaded_file in files:
        filename = uploaded_file.filename or "unknown"
        ext = Path(filename).suffix.lower()
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Allowed: {sorted(allowed_exts)}",
            )

        content = await uploaded_file.read()
        settings = get_settings()
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File '{filename}' exceeds maximum allowed upload size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
            )

        try:
            res = indexer.index_file(filename=filename, content_bytes=content)
            results.append({
                "filename": filename,
                "status": res.status,
                "chunk_count": res.chunk_count,
                "sha256": res.sha256_hash,
                "is_duplicate": res.is_duplicate,
            })
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to index '{filename}': {str(e)}") from e

    return results


@router.post("/bootstrap", response_model=dict[str, Any])
async def bootstrap_workspace() -> dict[str, Any]:
    """
    Initializes an ephemeral sample workspace with starter files for testing and demo flows.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    smoke_calc = workspace / "smoke_calc.py"
    if not smoke_calc.exists():
        smoke_calc.write_text(
            "def calculate_discount(price: float, discount: float) -> float:\n"
            "    '''Calculate discounted price with tax.'''\n"
            "    return price - (price * discount)\n",
            encoding="utf-8",
        )

    test_smoke_calc = workspace / "test_smoke_calc.py"
    if not test_smoke_calc.exists():
        test_smoke_calc.write_text(
            "from smoke_calc import calculate_discount\n\n"
            "def test_calculate_discount():\n"
            "    assert calculate_discount(100.0, 0.2) == 80.0\n",
            encoding="utf-8",
        )

    return {
        "status": "bootstrapped",
        "workspace_root": str(workspace),
        "files_created": ["smoke_calc.py", "test_smoke_calc.py"],
        "timestamp": time.time(),
    }
