"""
Unified Diff Generator & AST Validation Module for Phase 4 Agent Core.
Generates unified diffs, verifies AST/syntax correctness, tracks changed files,
and registers proposals with the Phase 4 Approval Manager without modifying disk files.
"""

import ast
import difflib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings
from src.mcp_server.tools.patch import propose_multi_patch_tool, propose_patch_tool


class DiffValidationResult(BaseModel):
    target_file: str
    original_content: str
    proposed_content: str
    unified_diff: str
    lines_added: int
    lines_removed: int
    syntax_valid: bool
    syntax_error: str | None = None
    risk_score: int = 1
    risk_notes: list[str] = Field(default_factory=list)
    rationale: str = ""
    status: str = "PENDING_APPROVAL"
    patch_id: str | None = None
    request_id: str | None = None
    action_hash: str | None = None
    created_at: float = 0.0
    # Multi-file fields
    bundle_id: str | None = None
    is_new_file: bool = False
    files: list[dict[str, Any]] = Field(default_factory=list)


class DiffGenerator:
    """
    Diff generation and AST validation service.
    Ensures:
    1. Clean standard unified diff formatting.
    2. Real AST parsing for Python files before staging.
    3. Integration with the existing Phase 4 propose_patch_tool.
    4. Disk files remain untouched until explicit human approval.
    """

    @staticmethod
    def validate_syntax(filename: str, content: str) -> tuple[bool, str | None]:
        """Validates Python syntax via AST parsing."""
        if filename.endswith(".py"):
            try:
                ast.parse(content, filename=filename)
                return True, None
            except SyntaxError as e:
                return False, f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
            except Exception as e:
                return False, f"AST Parsing Error: {str(e)}"
        # For other files (JSON, JS, MD, etc.), treat as valid unless unparseable
        if filename.endswith(".json"):
            import json

            try:
                json.loads(content)
                return True, None
            except Exception as e:
                return False, f"JSON SyntaxError: {str(e)}"
        return True, None

    @staticmethod
    def generate_unified_diff(
        target_file: str,
        original_content: str,
        proposed_content: str,
    ) -> str:
        """Generates standard unified diff output."""
        orig_lines = original_content.splitlines(keepends=True)
        prop_lines = proposed_content.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                prop_lines,
                fromfile=f"a/{target_file}",
                tofile=f"b/{target_file}",
                lineterm="",
            )
        )
        return "\n".join(diff_lines)

    @staticmethod
    def calculate_diff_metrics(unified_diff: str) -> tuple[int, int]:
        """Calculates lines added (+) and lines removed (-) in diff."""
        added = 0
        removed = 0
        for line in unified_diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        return added, removed

    def create_patch_proposal(
        self,
        target_file: str,
        proposed_content: str,
        rationale: str,
    ) -> DiffValidationResult:
        """
        Validates the patch, generates the diff, and registers it with the Phase 4 Approval Manager
        via propose_patch_tool. Disk files remain unmodified.
        """
        settings = get_settings()
        workspace = Path(settings.WORKSPACE_ROOT).resolve()
        target_path = (workspace / target_file).resolve()

        original_content = ""
        if target_path.exists() and target_path.is_file():
            try:
                original_content = target_path.read_text(encoding="utf-8")
            except Exception:
                pass

        # Syntax / AST Validation
        syntax_valid, syntax_error = self.validate_syntax(target_file, proposed_content)

        # Generate Unified Diff
        diff_str = self.generate_unified_diff(target_file, original_content, proposed_content)
        lines_added, lines_removed = self.calculate_diff_metrics(diff_str)

        # Delegate proposal registration to existing Phase 4 tool
        mcp_res = propose_patch_tool(
            target_file=target_file,
            proposed_content=proposed_content,
            rationale=rationale,
        )

        patch_id = mcp_res.get("patch_id")
        request_id = mcp_res.get("request_id")
        action_hash = mcp_res.get("action_hash")
        risk_score = mcp_res.get("risk_score", 1)
        risk_notes = mcp_res.get("risk_notes", [])

        # Crucial Invariant: Verify disk file was NOT modified by proposal
        if target_path.exists():
            assert target_path.read_text(encoding="utf-8") == original_content

        return DiffValidationResult(
            target_file=target_file,
            original_content=original_content,
            proposed_content=proposed_content,
            unified_diff=diff_str or mcp_res.get("unified_diff", ""),
            lines_added=lines_added,
            lines_removed=lines_removed,
            syntax_valid=syntax_valid,
            syntax_error=syntax_error,
            risk_score=risk_score,
            risk_notes=risk_notes,
            rationale=rationale,
            status=mcp_res.get("status", "PENDING_APPROVAL"),
            patch_id=patch_id,
            request_id=request_id,
            action_hash=action_hash,
            created_at=mcp_res.get("created_at", 0.0),
        )

    def create_multi_patch_proposal(
        self,
        file_changes: list[dict[str, str]],
        rationale: str,
    ) -> DiffValidationResult:
        """
        Validates multiple file changes, generates individual & combined diffs,
        and registers a unified multi-file proposal bundle via propose_multi_patch_tool.
        Disk files remain untouched until explicit operator authorization.
        """
        mcp_res = propose_multi_patch_tool(
            file_changes=file_changes,
            rationale=rationale,
        )

        return DiffValidationResult(
            target_file=mcp_res.get("target_file", "Multiple files"),
            original_content="",
            proposed_content="",
            unified_diff=mcp_res.get("unified_diff", ""),
            lines_added=mcp_res.get("lines_added", 0),
            lines_removed=mcp_res.get("lines_removed", 0),
            syntax_valid=mcp_res.get("syntax_valid", True),
            syntax_error=mcp_res.get("syntax_error"),
            risk_score=mcp_res.get("risk_score", 1),
            risk_notes=mcp_res.get("risk_notes", []),
            rationale=rationale,
            status=mcp_res.get("status", "PENDING_APPROVAL"),
            patch_id=mcp_res.get("patch_id"),
            request_id=mcp_res.get("request_id"),
            action_hash=mcp_res.get("action_hash"),
            created_at=mcp_res.get("created_at", 0.0),
            bundle_id=mcp_res.get("bundle_id"),
            is_new_file=mcp_res.get("is_new_file", False),
            files=mcp_res.get("files", []),
        )
