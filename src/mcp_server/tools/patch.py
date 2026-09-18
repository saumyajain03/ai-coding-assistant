"""
MCP Tool: Patch Proposal
Generates unified diffs, runs AST syntax verification, and computes risk scores
without modifying repository files on disk. Enforces HITL approval workflow.
"""

import ast
import difflib
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import get_settings


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
    created_at: float


def propose_patch_tool(
    target_file: str,
    proposed_content: str,
    rationale: str,
) -> dict[str, Any]:
    """
    Proposes a code patch as a reviewable unified diff against the workspace.
    Validates AST syntax and assesses risk without applying changes to disk.

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
        created_at=time.time(),
    ).model_dump()
