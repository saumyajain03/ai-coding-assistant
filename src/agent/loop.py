"""
SentinelForge Phase 4 7-Stage Autonomous Agent Orchestration Loop.
Implements the full 7-stage workflow:
Stage 1: Task Analysis
Stage 2: Plan Generation
Stage 3: Context Retrieval (via MCP tools)
Stage 4: Patch Proposal (via DiffGenerator & propose_patch_tool)
Stage 5: Sandbox Execution (via run_sandbox_command_tool)
Stage 6: Self-Critique & Risk Scoring
Stage 7: Final Report & Unified Diff

Strict Security Invariants:
- Connects exclusively to the existing RAG, MCP, Sandbox, Policy, and Audit subsystems.
- Never bypasses Phase 3 sandbox boundaries or Phase 4 Human-In-The-Loop approval gates.
- Proposes patches; never applies patches to disk without explicit human approval.
- Failed tests reach the Critique stage rather than being falsely reported as successes.
"""

import re
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.agent.diff_generator import DiffGenerator, DiffValidationResult
from src.agent.llm_client import LLMClient
from src.agent.prompts import (
    STAGE_ANALYSIS_PROMPT,
    STAGE_CRITIQUE_PROMPT,
    STAGE_PATCH_PROMPT,
    STAGE_PLAN_PROMPT,
    SYSTEM_DEFENSIVE_PROMPT,
)
from src.config import get_settings
from src.mcp_server.server import invoke_mcp_tool
from src.sandbox.audit import get_audit_logger


class AgentStage(StrEnum):
    ANALYSIS = "Analysis"
    PLAN = "Plan"
    RETRIEVAL = "Retrieval"
    PATCH = "Patch"
    TEST = "Test"
    CRITIQUE = "Critique"
    REPORT = "Report"


class AgentStepResult(BaseModel):
    stage: AgentStage
    status: str = "completed"  # completed, failed, blocked
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentExecutionReport(BaseModel):
    task: str
    stages_executed: list[AgentStage] = Field(default_factory=list)
    step_results: dict[str, AgentStepResult] = Field(default_factory=dict)
    analysis: str = ""
    plan: str = ""
    retrieved_citations: list[dict[str, Any]] = Field(default_factory=list)
    patch_result: DiffValidationResult | None = None
    test_result: dict[str, Any] | None = None
    critique: str = ""
    final_report: str = ""
    tests_passed: bool = False
    requires_human_approval: bool = True
    approval_request_id: str | None = None
    approval_action_hash: str | None = None


class AgentLoop:
    """
    Orchestrates the 7-stage autonomous agent execution loop.
    Interacts with RAG, repository inspection, diff proposal, and sandbox execution
    strictly through existing MCP tools and security gates.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        diff_generator: DiffGenerator | None = None,
    ):
        self.llm = llm_client or LLMClient()
        self.diff_gen = diff_generator or DiffGenerator()
        self.audit = get_audit_logger()
        self.settings = get_settings()

    async def run(
        self,
        task: str,
        target_file: str = "",
        test_command: str = "pytest",
        proposed_code: str | None = None,
        skip_rag: bool = False,
    ) -> AgentExecutionReport:
        """
        Executes the 7-stage loop sequentially.
        """
        report = AgentExecutionReport(task=task)

        # ----------------------------------------------------------------------
        # STAGE 1: Task Analysis
        # ----------------------------------------------------------------------
        stage1_res = await self._execute_stage_analysis(task)
        report.stages_executed.append(AgentStage.ANALYSIS)
        report.step_results[AgentStage.ANALYSIS.value] = stage1_res
        report.analysis = stage1_res.details.get("analysis_text", "")

        # ----------------------------------------------------------------------
        # STAGE 2: Plan Generation
        # ----------------------------------------------------------------------
        stage2_res = await self._execute_stage_plan(task, report.analysis)
        report.stages_executed.append(AgentStage.PLAN)
        report.step_results[AgentStage.PLAN.value] = stage2_res
        report.plan = stage2_res.details.get("plan_text", "")

        # ----------------------------------------------------------------------
        # STAGE 3: Context Retrieval (via MCP tools)
        # ----------------------------------------------------------------------
        stage3_res = await self._execute_stage_retrieval(task, skip_rag=skip_rag)
        report.stages_executed.append(AgentStage.RETRIEVAL)
        report.step_results[AgentStage.RETRIEVAL.value] = stage3_res
        report.retrieved_citations = stage3_res.details.get("citations", [])

        # ----------------------------------------------------------------------
        # STAGE 4: Patch Proposal (via DiffGenerator & propose_patch_tool)
        # ----------------------------------------------------------------------
        stage4_res = await self._execute_stage_patch(
            task=task,
            target_file=target_file,
            plan=report.plan,
            citations=report.retrieved_citations,
            proposed_code=proposed_code,
        )
        report.stages_executed.append(AgentStage.PATCH)
        report.step_results[AgentStage.PATCH.value] = stage4_res
        report.patch_result = stage4_res.details.get("diff_result")
        if report.patch_result:
            report.approval_request_id = report.patch_result.request_id
            report.approval_action_hash = report.patch_result.action_hash

        # ----------------------------------------------------------------------
        # STAGE 5: Sandbox Execution (via run_sandbox_command_tool)
        # ----------------------------------------------------------------------
        stage5_res = await self._execute_stage_test(test_command)
        report.stages_executed.append(AgentStage.TEST)
        report.step_results[AgentStage.TEST.value] = stage5_res
        report.test_result = stage5_res.details.get("sandbox_result")
        report.tests_passed = bool(report.test_result and report.test_result.get("passed", False))

        # ----------------------------------------------------------------------
        # STAGE 6: Self-Critique & Risk Scoring
        # ----------------------------------------------------------------------
        stage6_res = await self._execute_stage_critique(
            patch_result=report.patch_result,
            test_result=report.test_result,
        )
        report.stages_executed.append(AgentStage.CRITIQUE)
        report.step_results[AgentStage.CRITIQUE.value] = stage6_res
        report.critique = stage6_res.details.get("critique_text", "")

        # ----------------------------------------------------------------------
        # STAGE 7: Final Report & Unified Diff
        # ----------------------------------------------------------------------
        stage7_res = await self._execute_stage_report(report)
        report.stages_executed.append(AgentStage.REPORT)
        report.step_results[AgentStage.REPORT.value] = stage7_res
        report.final_report = stage7_res.details.get("report_markdown", "")

        # Record structured audit event for entire execution loop
        risk_str = (
            "HIGH"
            if report.patch_result and report.patch_result.risk_score >= 5
            else ("MEDIUM" if report.patch_result and report.patch_result.risk_score >= 3 else "LOW")
        )
        self.audit.record(
            event_type="AGENT_LOOP_COMPLETED",
            caller="agent_orchestrator",
            details={
                "task": task,
                "stages_count": len(report.stages_executed),
                "tests_passed": report.tests_passed,
                "has_patch": report.patch_result is not None,
                "request_id": report.approval_request_id,
                "action_hash": report.approval_action_hash,
            },
            risk_level=risk_str,
            request_id=report.approval_request_id,
            action_hash=report.approval_action_hash,
        )

        return report

    # --------------------------------------------------------------------------
    # Stage Implementation Handlers
    # --------------------------------------------------------------------------

    async def _execute_stage_analysis(self, task: str) -> AgentStepResult:
        """Stage 1: Analyzes requirements, files, and objectives."""
        workspace_info = f"Workspace Root: {self.settings.WORKSPACE_ROOT}"
        prompt = STAGE_ANALYSIS_PROMPT.format(task=task, workspace_info=workspace_info)
        analysis_text = await self.llm.complete(prompt=prompt, system_prompt=SYSTEM_DEFENSIVE_PROMPT)

        return AgentStepResult(
            stage=AgentStage.ANALYSIS,
            status="completed",
            summary="Requirements analyzed and scope defined.",
            details={"analysis_text": analysis_text},
        )

    async def _execute_stage_plan(self, task: str, analysis: str) -> AgentStepResult:
        """Stage 2: Generates a step-by-step implementation and verification plan."""
        prompt = STAGE_PLAN_PROMPT.format(analysis=analysis)
        plan_text = await self.llm.complete(prompt=prompt, system_prompt=SYSTEM_DEFENSIVE_PROMPT)

        return AgentStepResult(
            stage=AgentStage.PLAN,
            status="completed",
            summary="Step-by-step implementation plan generated.",
            details={"plan_text": plan_text},
        )

    async def _execute_stage_retrieval(self, task: str, skip_rag: bool = False) -> AgentStepResult:
        """Stage 3: Retrieves relevant context using existing retrieve_context MCP tool."""
        citations = []
        if not skip_rag:
            try:
                # Query RAG context through official MCP tool
                rag_result = await invoke_mcp_tool(
                    "retrieve_context",
                    {"query": task, "top_k": 3},
                )
                if isinstance(rag_result, dict) and "results" in rag_result:
                    for item in rag_result["results"]:
                        citations.append({
                            "filename": item.get("filename", ""),
                            "page": item.get("page"),
                            "start_line": item.get("start_line"),
                            "end_line": item.get("end_line"),
                            "snippet": item.get("content", "")[:200],
                        })
            except Exception as e:
                citations.append({"error": f"Retrieval note: {str(e)}"})

        return AgentStepResult(
            stage=AgentStage.RETRIEVAL,
            status="completed",
            summary=f"Context retrieval completed with {len(citations)} citations.",
            details={"citations": citations},
        )

    async def _execute_stage_patch(
        self,
        task: str,
        target_file: str,
        plan: str,
        citations: list[dict[str, Any]],
        proposed_code: str | None = None,
    ) -> AgentStepResult:
        """Stage 4: Proposes candidate unified diff without modifying disk files."""
        if not target_file:
            # Attempt to infer target file from task description (e.g. "in smoke_calc.py")
            file_match = re.search(r"([\w_]+\.py)", task)
            target_file = file_match.group(1) if file_match else "main.py"

        workspace = Path(self.settings.WORKSPACE_ROOT).resolve()
        target_path = (workspace / target_file).resolve()

        current_content = ""
        if target_path.exists() and target_path.is_file():
            try:
                current_content = target_path.read_text(encoding="utf-8")
            except Exception:
                pass

        if proposed_code is None:
            # Synthesize patch content via LLM
            citations_str = "\n".join(f"- {c.get('filename')}: {c.get('snippet')}" for c in citations if isinstance(c, dict))
            prompt = STAGE_PATCH_PROMPT.format(
                target_file=target_file,
                current_content=current_content or "# New file",
                plan=plan,
                context=citations_str,
            )
            proposed_code = await self.llm.complete(prompt=prompt, system_prompt=SYSTEM_DEFENSIVE_PROMPT)

        # Generate diff & register proposal with Phase 4 Approval Manager
        diff_res = self.diff_gen.create_patch_proposal(
            target_file=target_file,
            proposed_content=proposed_code,
            rationale=f"Automated patch proposed for task: {task}",
        )

        return AgentStepResult(
            stage=AgentStage.PATCH,
            status="completed" if diff_res.syntax_valid else "syntax_error",
            summary=(
                f"Patch proposed for '{target_file}' "
                f"(+{diff_res.lines_added} / -{diff_res.lines_removed} lines). "
                f"Status: PENDING_APPROVAL."
            ),
            details={"diff_result": diff_res},
        )

    async def _execute_stage_test(self, test_command: str) -> AgentStepResult:
        """Stage 5: Executes test suite in sandbox via run_sandbox_command MCP tool."""
        try:
            sandbox_res = await invoke_mcp_tool(
                "run_sandbox_command",
                {"command": test_command, "timeout_sec": 15},
            )
        except Exception as e:
            sandbox_res = {
                "status": "failed",
                "passed": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Failed to execute sandbox test: {str(e)}",
                "timed_out": False,
            }

        passed = bool(sandbox_res.get("passed", False))
        return AgentStepResult(
            stage=AgentStage.TEST,
            status="completed" if passed else "failed",
            summary=f"Sandbox test '{test_command}' {'PASSED' if passed else 'FAILED'}.",
            details={"sandbox_result": sandbox_res},
        )

    async def _execute_stage_critique(
        self,
        patch_result: DiffValidationResult | None,
        test_result: dict[str, Any] | None,
    ) -> AgentStepResult:
        """Stage 6: Inspects test output, exit code, regressions, and scores risk."""
        diff_str = patch_result.unified_diff if patch_result else "(No patch)"
        exit_code = test_result.get("exit_code", 1) if test_result else 1
        passed = test_result.get("passed", False) if test_result else False
        stdout = test_result.get("stdout", "") if test_result else ""
        stderr = test_result.get("stderr", "") if test_result else ""

        prompt = STAGE_CRITIQUE_PROMPT.format(
            diff=diff_str,
            exit_code=exit_code,
            passed=passed,
            stdout=stdout,
            stderr=stderr,
        )
        critique_text = await self.llm.complete(prompt=prompt, system_prompt=SYSTEM_DEFENSIVE_PROMPT)

        return AgentStepResult(
            stage=AgentStage.CRITIQUE,
            status="completed",
            summary="Self-critique and empirical risk assessment completed.",
            details={"critique_text": critique_text},
        )

    async def _execute_stage_report(self, report_state: AgentExecutionReport) -> AgentStepResult:
        """Stage 7: Formulates comprehensive markdown final execution report."""
        diff_str = report_state.patch_result.unified_diff if report_state.patch_result else "No diff generated."
        test_summary = "PASSED" if report_state.tests_passed else "FAILED / INCOMPLETE"
        approval_status = (
            f"WAITING_FOR_HUMAN_APPROVAL (Request ID: `{report_state.approval_request_id}`, "
            f"Hash: `{report_state.approval_action_hash[:12] if report_state.approval_action_hash else ''}...`)"
            if report_state.approval_request_id
            else "NO_APPROVAL_PENDING"
        )

        report_markdown = f"""# SentinelForge Execution Report

## 1. Task Objective
{report_state.task}

## 2. Implementation Plan
{report_state.plan}

## 3. Retrieved Citations
Total Citations: {len(report_state.retrieved_citations)}

## 4. Proposed Unified Diff
```diff
{diff_str}
```

## 5. Empirical Sandbox Test Verification
- **Command Executed**: `{report_state.test_result.get('command', 'test') if report_state.test_result else 'None'}`
- **Test Result**: **{test_summary}**
- **Exit Code**: {report_state.test_result.get('exit_code', -1) if report_state.test_result else -1}

## 6. Self-Critique & Risk Scoring
{report_state.critique}

## 7. Operational Status
- **Status**: {approval_status}
- **Security Invariant**: Disk modification is deferred until explicit operator sign-off.
"""

        return AgentStepResult(
            stage=AgentStage.REPORT,
            status="completed",
            summary="Final markdown execution report generated.",
            details={"report_markdown": report_markdown},
        )
