"""
MCP Tool: Patch Proposal & Application
Generates unified diffs, runs AST syntax verification, and computes risk scores
without modifying repository files on disk. Enforces Phase 4 HITL approval workflow:
PROPOSE -> HUMAN APPROVAL -> APPLY -> RUN TESTS.
"""

import ast
import difflib
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import ActionCategory, RiskLevel, get_approval_manager
from src.sandbox.runner import execute_sandboxed_command

# In-memory registry of proposed patches pending human review
_pending_patches: dict[str, dict[str, Any]] = {}


class PatchProposalResult(BaseModel):
    patch_id: str
    target_file: str
    rationale: str
    unified_diff: str
    lines_added: int
    lines_removed: int
    syntax_valid: bool
    syntax_error: str | None = None
    risk_score: int  # 1 (low) to 10 (critical)
    risk_notes: list[str]
    status: str = "PENDING_APPROVAL"
    request_id: str = ""
    action_hash: str = ""
    created_at: float = Field(default_factory=time.time)


def propose_patch_tool(
    target_file: str,
    proposed_content: str,
    rationale: str,
) -> dict[str, Any]:
    """
    Proposes a code patch as a reviewable unified diff against the workspace.
    Validates AST syntax and assesses risk without applying changes to disk.
    Enforces Phase 4 HITL authorization flow.

    Args:
        target_file: Relative path to the file within the workspace.
        proposed_content: The full new content proposed for the file.
        rationale: Explanation and reasoning for the proposed modification.

    Returns:
        Structured dictionary containing the unified diff, syntax status, risk notes, and patch ID.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target_path = (workspace / target_file).resolve()

    # Enforce path jail invariant
    if not settings.is_path_in_workspace(target_path):
        return {
            "error": "SECURITY_VIOLATION: Target file resolves outside workspace root.",
            "target_file": target_file,
            "status": "failed",
        }

    # Read original content if file exists
    if target_path.exists():
        if target_path.is_dir():
            return {
                "error": f"Target path '{target_file}' is a directory, not a file.",
                "status": "failed",
            }
        try:
            original_content = target_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {
                "error": f"Target file '{target_file}' is binary or unreadable as UTF-8 text.",
                "status": "failed",
            }
    else:
        # Creating a new file
        original_content = ""

    # Generate unified diff
    orig_lines = original_content.splitlines(keepends=True)
    prop_lines = proposed_content.splitlines(keepends=True)

    rel_name = target_path.relative_to(workspace)
    diff = difflib.unified_diff(
        orig_lines,
        prop_lines,
        fromfile=f"a/{rel_name}",
        tofile=f"b/{rel_name}",
        n=3,
    )
    unified_diff_str = "".join(diff)

    lines_added = sum(
        1 for line in unified_diff_str.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    lines_removed = sum(
        1 for line in unified_diff_str.splitlines() if line.startswith("-") and not line.startswith("---")
    )

    # AST Syntax check for Python files
    syntax_valid = True
    syntax_error = None
    if target_path.suffix == ".py":
        try:
            ast.parse(proposed_content, filename=target_file)
        except SyntaxError as e:
            syntax_valid = False
            syntax_error = f"SyntaxError at line {e.lineno}: {e.msg}"

    # Risk analysis
    risk_score = 1
    risk_notes: list[str] = []

    if lines_added + lines_removed > 100:
        risk_score += 2
        risk_notes.append("Large change: modifies more than 100 lines.")

    lower_content = proposed_content.lower()
    dangerous_keywords = ["os.system", "subprocess.call", "eval(", "exec(", "shutil.rmtree", "__import__"]
    found_dangerous = [kw for kw in dangerous_keywords if kw in lower_content]
    if found_dangerous:
        risk_score += 4
        risk_notes.append(f"High risk API calls detected: {', '.join(found_dangerous)}")

    if not syntax_valid:
        risk_score += 3
        risk_notes.append(f"Syntax validation failed: {syntax_error}")

    risk_score = min(risk_score, 10)
    if not risk_notes:
        risk_notes.append("Standard patch: no dangerous primitives detected.")

    patch_id = f"patch_{sha256((target_file + proposed_content + str(time.time())).encode()).hexdigest()[:12]}"

    # Register with Phase 4 Approval Manager
    approval_mgr = get_approval_manager()
    patch_cmd = f"apply_patch {patch_id} {str(rel_name)}"
    proposal = approval_mgr.create_proposal(
        command=patch_cmd,
        files=[str(rel_name)],
        reason=rationale or f"Apply verified code modifications to {str(rel_name)}",
        category=ActionCategory.PATCH_APPLICATION,
    )
    proposal.risk_level = RiskLevel.HIGH if risk_score >= 5 else RiskLevel.MEDIUM

    # Save to pending patches
    _pending_patches[patch_id] = {
        "patch_id": patch_id,
        "target_file": str(rel_name),
        "proposed_content": proposed_content,
        "rationale": rationale,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "request_id": proposal.request_id,
        "action_hash": proposal.action_hash,
        "applied": False,
    }

    # Record audit event
    audit = get_audit_logger()
    audit.record(
        event_type="PATCH_PROPOSED",
        caller="patch_tool",
        details={
            "patch_id": patch_id,
            "target_file": str(rel_name),
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "risk_score": risk_score,
            "request_id": proposal.request_id,
            "action_hash": proposal.action_hash,
        },
        risk_level=proposal.risk_level.value,
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        affected_files=[str(rel_name)],
    )

    return PatchProposalResult(
        patch_id=patch_id,
        target_file=str(rel_name),
        rationale=rationale,
        unified_diff=unified_diff_str or "(No changes detected)",
        lines_added=lines_added,
        lines_removed=lines_removed,
        syntax_valid=syntax_valid,
        syntax_error=syntax_error,
        risk_score=risk_score,
        risk_notes=risk_notes,
        status="PENDING_APPROVAL",
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        created_at=time.time(),
    ).model_dump()


def apply_patch_tool(
    patch_id: str,
    approval_token: dict[str, Any] | None = None,
    test_command: str = "",
) -> dict[str, Any]:
    """
    Applies an approved patch to the workspace file, verifies diff, and runs automated tests.
    Strictly enforces human approval before disk write.
    """
    patch_entry = _pending_patches.get(patch_id)
    if not patch_entry:
        return {
            "status": "failed",
            "error": f"PATCH_NOT_FOUND: No pending patch with ID '{patch_id}'.",
        }

    if patch_entry["applied"]:
        return {
            "status": "failed",
            "error": f"PATCH_ALREADY_APPLIED: Patch '{patch_id}' has already been applied.",
        }

    # Verify human approval token
    if not approval_token:
        return {
            "status": "WAITING_FOR_HUMAN_APPROVAL",
            "patch_id": patch_id,
            "request_id": patch_entry["request_id"],
            "action_hash": patch_entry["action_hash"],
            "error": "APPROVAL_REQUIRED: Applying a patch modifies the workspace and requires explicit human approval.",
        }

    approval_mgr = get_approval_manager()
    req_id = approval_token.get("request_id", "")
    target_file = patch_entry["target_file"]
    patch_cmd = f"apply_patch {patch_id} {target_file}"

    valid, err = approval_mgr.verify_and_consume_approval(
        request_id=req_id,
        command=patch_cmd,
        category=ActionCategory.PATCH_APPLICATION.value,
        files=[target_file],
    )
    if not valid:
        return {
            "status": "APPROVAL_INVALID",
            "error": err,
            "patch_id": patch_id,
        }

    # Apply patch to disk
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target_path = (workspace / target_file).resolve()

    if not settings.is_path_in_workspace(target_path):
        return {
            "status": "failed",
            "error": "SECURITY_VIOLATION: Target file resolves outside workspace root.",
        }

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(patch_entry["proposed_content"], encoding="utf-8")
    patch_entry["applied"] = True

    # Audit application
    audit = get_audit_logger()
    audit.record(
        event_type="PATCH_APPLIED",
        caller="patch_tool",
        details={
            "patch_id": patch_id,
            "target_file": target_file,
            "request_id": req_id,
        },
        risk_level="MEDIUM",
        request_id=req_id,
        affected_files=[target_file],
    )

    test_result = None
    tests_passed = True
    if test_command:
        test_result = execute_sandboxed_command(test_command)
        tests_passed = bool(test_result.get("passed", False))

    final_report = {
        "patch_id": patch_id,
        "target_file": target_file,
        "applied": True,
        "lines_added": patch_entry.get("lines_added", 0),
        "lines_removed": patch_entry.get("lines_removed", 0),
        "test_command": test_command or None,
        "tests_passed": tests_passed if test_command else None,
        "verification_summary": (
            f"Patch '{patch_id}' applied successfully. "
            + (f"Verification test '{test_command}' {'PASSED' if tests_passed else 'FAILED'}." if test_command else "No automated tests requested.")
        ),
    }

    return {
        "status": "APPLIED",
        "patch_id": patch_id,
        "target_file": target_file,
        "applied": True,
        "test_result": test_result,
        "final_report": final_report,
        "message": f"Patch '{patch_id}' successfully applied to '{target_file}'.",
    }
