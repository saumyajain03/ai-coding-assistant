"""
Phase 4 & Phase 7 Verification: Agent Loop and Orchestration Test Suite
Covers Task 7.1 (Tests 13-15 and 20):
13. test_agent_7_stage_execution: Verifies transition across all 7 stages.
14. test_diff_generation_format: Verifies unified diff format and AST validity.
15. test_patch_atomic_revert_on_rejection: Verifies file is unmodified when patch is rejected.
20. test_node_sandbox_execution: Verifies JavaScript unit test runner in sandbox (Bonus).
Additional tests:
- test_agent_rejection_flow_does_not_modify_disk
- test_failed_tests_reach_critique_truthfully
- test_final_report_generation
"""

import shutil
from pathlib import Path

import pytest

from src.agent.diff_generator import DiffGenerator
from src.agent.llm_client import DeterministicMockProvider, LLMClient
from src.agent.loop import AgentLoop, AgentStage
from src.config import get_settings
from src.mcp_server.tools.patch import apply_patch_tool, propose_patch_tool
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import get_approval_manager
from src.sandbox.runner import run_node_code


@pytest.fixture(autouse=True)
def _reset_audit_and_approvals():
    get_approval_manager().clear()
    get_audit_logger().clear()
    yield
    get_approval_manager().clear()
    get_audit_logger().clear()


# 13. Agent 7-Stage Execution
@pytest.mark.asyncio
async def test_agent_7_stage_execution():
    """
    Verify that the orchestrator transitions sequentially through all 7 stages:
    Analysis -> Plan -> Retrieval -> Patch -> Test -> Critique -> Report.
    """
    agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))

    report = await agent.run(
        task="Implement string formatting helper in utils.py",
        target_file="utils.py",
        test_command="python -c \"print('TEST_PASS')\"",
        proposed_code="def format_text(s: str) -> str:\n    return s.strip().title()\n",
        skip_rag=True,
    )

    expected_stages = [
        AgentStage.ANALYSIS,
        AgentStage.PLAN,
        AgentStage.RETRIEVAL,
        AgentStage.PATCH,
        AgentStage.TEST,
        AgentStage.CRITIQUE,
        AgentStage.REPORT,
    ]
    assert report.stages_executed == expected_stages
    assert all(stage.value in report.step_results for stage in expected_stages)
    assert report.analysis != ""
    assert report.plan != ""
    assert report.patch_result is not None
    assert report.critique != ""
    assert "# SentinelForge Execution Report" in report.final_report


# 14. Diff Generation Format & AST Validation
def test_diff_generation_format():
    """Verify unified diff format (+/- lines, headers) and AST syntax validation."""
    diff_gen = DiffGenerator()
    original = "def compute():\n    return 10\n"
    proposed = "def compute():\n    # optimized\n    return 20\n"

    diff_str = diff_gen.generate_unified_diff("calc.py", original, proposed)
    assert "--- a/calc.py" in diff_str
    assert "+++ b/calc.py" in diff_str
    assert "+    # optimized" in diff_str
    assert "-    return 10" in diff_str
    assert "+    return 20" in diff_str

    added, removed = diff_gen.calculate_diff_metrics(diff_str)
    assert added == 2
    assert removed == 1

    # Valid Python AST check
    is_valid, err = diff_gen.validate_syntax("calc.py", proposed)
    assert is_valid is True
    assert err is None

    # Invalid Python AST check (syntax error)
    invalid_code = "def broken(:\n    pass\n"
    is_valid_bad, err_bad = diff_gen.validate_syntax("calc.py", invalid_code)
    assert is_valid_bad is False
    assert "SyntaxError" in err_bad


# 15. Patch Atomic Revert on Rejection
def test_patch_atomic_revert_on_rejection():
    """
    Verify that when human approval is rejected, the target file remains strictly
    unmodified on disk, and unapproved apply attempts fail cleanly.
    """
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target_file = workspace / "revert_test.py"
    original_code = "def original_function(): return 'original'\n"
    target_file.write_text(original_code, encoding="utf-8")

    try:
        # Propose patch
        proposed_code = "def original_function(): return 'tampered'\n"
        proposal = propose_patch_tool(
            target_file="revert_test.py",
            proposed_content=proposed_code,
            rationale="Attempting change that will be rejected",
        )
        patch_id = proposal["patch_id"]
        request_id = proposal["request_id"]

        # Human operator explicitly rejects the patch
        approval_mgr = get_approval_manager()
        rejection_token = approval_mgr.submit_approval(
            request_id=request_id,
            action_hash=proposal["action_hash"],
            approved=False,
            rejection_reason="Changes violate performance guidelines",
        )
        assert rejection_token.approved is False

        # Attempt to apply rejected patch
        res = apply_patch_tool(
            patch_id=patch_id,
            approval_token=rejection_token.model_dump(),
        )
        assert res["status"] in ("APPROVAL_INVALID", "failed")

        # Invariant: File on disk must retain original content
        assert target_file.read_text(encoding="utf-8") == original_code

    finally:
        if target_file.exists():
            target_file.unlink()


@pytest.mark.asyncio
async def test_agent_rejection_flow_does_not_modify_disk():
    """Verify end-to-end agent loop with rejection preserves disk integrity."""
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target_file = workspace / "agent_revert.py"
    initial_code = "def calc(): return 1\n"
    target_file.write_text(initial_code, encoding="utf-8")

    try:
        agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))
        report = await agent.run(
            task="Change calc return to 2",
            target_file="agent_revert.py",
            proposed_code="def calc(): return 2\n",
            skip_rag=True,
        )

        assert report.patch_result is not None
        assert report.approval_request_id is not None

        # Verify disk remains unchanged prior to approval
        assert target_file.read_text(encoding="utf-8") == initial_code

    finally:
        if target_file.exists():
            target_file.unlink()


# 20. Node.js Sandbox Execution (Bonus)
def test_node_sandbox_execution():
    """Verify JavaScript test execution in sandbox via run_node_code."""
    if not shutil.which("node"):
        pytest.skip("Node.js runtime not installed in environment")

    js_code = (
        "function sum(a, b) { return a + b; }\n"
        "const result = sum(15, 27);\n"
        "console.log('NODE_TEST_RESULT: ' + result);\n"
    )
    res = run_node_code(js_code)
    assert res["passed"] is True
    assert res["exit_code"] == 0
    assert "NODE_TEST_RESULT: 42" in res["stdout"]


# Empirical Truth & Critique Verification
@pytest.mark.asyncio
async def test_failed_tests_reach_critique_truthfully():
    """Verify failing tests are accurately passed to Critique stage."""
    agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))

    report = await agent.run(
        task="Introduce intentional assertion failure",
        target_file="broken.py",
        test_command="python -c \"import sys; print('FAILING_TEST_OUTPUT'); sys.exit(1)\"",
        proposed_code="def broken(): pass\n",
        skip_rag=True,
    )

    assert report.tests_passed is False
    assert report.test_result["passed"] is False
    assert report.test_result["exit_code"] == 1
    assert "FAILING_TEST_OUTPUT" in report.test_result["stdout"]
    assert AgentStage.CRITIQUE in report.stages_executed
    assert "FAILED" in report.critique or "7/10" in report.critique


@pytest.mark.asyncio
async def test_final_report_generation():
    """Verify final execution report captures all stages, diff, and status."""
    agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))

    report = await agent.run(
        task="Create greeting function",
        target_file="greetings.py",
        test_command="python -c \"print('ALL_PASSED')\"",
        proposed_code="def greet(): return 'Hello'\n",
        skip_rag=True,
    )

    assert report.tests_passed is True
    assert "# SentinelForge Execution Report" in report.final_report
    assert "def greet():" in report.final_report
    assert "ALL_PASSED" in report.test_result["stdout"]
