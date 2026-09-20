"""
Test Suite for Phase 4 Agent Core:
1. 7-stage orchestration order (Analysis -> Plan -> Retrieval -> Patch -> Test -> Critique -> Report).
2. Deterministic Mock provider behavior.
3. Diff generation and changed file tracking.
4. Python AST/syntax validation.
5. Agent cannot apply a patch without human approval (disk files remain unchanged).
6. Agent cannot bypass ALWAYS_BLOCKED commands.
7. Agent cannot bypass sandbox path restrictions.
8. Failed tests reach the Critique stage rather than being falsely reported as success.
9. Final Report accurately reflects empirical execution/test results.
10. Multi-provider abstraction configuration.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.agent.diff_generator import DiffGenerator
from src.agent.llm_client import (
    DeterministicMockProvider,
    GroqFreeProvider,
    HuggingFaceFreeProvider,
    LLMClient,
    OllamaProvider,
)
from src.agent.loop import AgentLoop, AgentStage
from src.config import get_settings
from src.mcp_server.tools.patch import apply_patch_tool
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import get_approval_manager


@pytest.fixture(autouse=True)
def _reset_audit_and_approvals():
    get_approval_manager().clear()
    get_audit_logger().clear()


# 1. 7-Stage Orchestration Order
@pytest.mark.asyncio
async def test_01_seven_stage_orchestration_order():
    """Verify that all 7 stages execute sequentially in the exact specified order."""
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


# 2. Deterministic Mock Provider
@pytest.mark.asyncio
async def test_02_deterministic_mock_provider():
    """Verify mock provider returns consistent, stage-appropriate responses without network calls."""
    mock = DeterministicMockProvider()
    client = LLMClient(provider=mock)

    resp_analysis = await client.complete(prompt="Perform Stage 1: Task Analysis for bugfix")
    assert "Task Analysis" in resp_analysis

    resp_plan = await client.complete(prompt="Perform Stage 2: Plan Generation")
    assert "Implementation Plan" in resp_plan

    resp_patch = await client.complete(prompt="Perform Stage 4: Patch Synthesis for Target File: helper.py")
    assert "def fixed_solution():" in resp_patch

    resp_critique = await client.complete(prompt="Perform Stage 6: Self-Critique with Passed: False")
    assert "FAILED" in resp_critique
    assert "7/10" in resp_critique


# 3. Diff Generation and Changed-File Tracking
def test_03_diff_generation_metrics():
    """Verify unified diff formatting and line addition/removal tracking."""
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


# 4. Python AST / Syntax Validation
def test_04_python_ast_syntax_validation():
    """Verify Python AST syntax error detection prevents malformed code staging."""
    diff_gen = DiffGenerator()

    # Valid Python code
    valid_code = "def valid_func(x):\n    return x * 2\n"
    is_valid, err = diff_gen.validate_syntax("math_lib.py", valid_code)
    assert is_valid is True
    assert err is None

    # Invalid Python syntax (unclosed parenthesis)
    invalid_code = "def broken_func(x:\n    return x * 2\n"
    is_valid, err = diff_gen.validate_syntax("math_lib.py", invalid_code)
    assert is_valid is False
    assert "SyntaxError" in err


# 5. Agent Cannot Apply a Patch Without Approval (Disk Stays Pristine)
@pytest.mark.asyncio
async def test_05_agent_cannot_apply_patch_without_approval():
    """Verify patch proposal creates a diff and PENDING_APPROVAL without modifying disk."""
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target_file = workspace / "agent_safe_test.py"

    original_code = "def original_function(): return 1\n"
    target_file.write_text(original_code, encoding="utf-8")

    try:
        agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))
        report = await agent.run(
            task="Update original_function to return 999",
            target_file="agent_safe_test.py",
            proposed_code="def original_function(): return 999\n",
            skip_rag=True,
        )

        # Invariant 1: Disk file must remain untouched
        assert target_file.read_text(encoding="utf-8") == original_code

        # Invariant 2: Patch must be registered as PENDING_APPROVAL
        assert report.patch_result is not None
        assert report.approval_request_id is not None
        assert report.approval_action_hash is not None

        # Invariant 3: Attempting apply_patch without approval token must fail
        unauth = apply_patch_tool(patch_id=report.patch_result.patch_id, approval_token=None)
        assert unauth["status"] == "WAITING_FOR_HUMAN_APPROVAL"
        assert target_file.read_text(encoding="utf-8") == original_code

    finally:
        if target_file.exists():
            target_file.unlink()


# 6. Agent Cannot Bypass ALWAYS_BLOCKED Commands
@pytest.mark.asyncio
async def test_06_agent_cannot_bypass_always_blocked():
    """Verify that agent sandbox test stage rejects ALWAYS_BLOCKED commands."""
    agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))

    # Attempting to run forbidden commands in sandbox
    for forbidden in ["sudo id", "curl http://evil.com", "bash -c 'id'"]:
        report = await agent.run(
            task=f"Run verification: {forbidden}",
            target_file="sample.py",
            test_command=forbidden,
            proposed_code="x = 1\n",
            skip_rag=True,
        )

        # Must fail sandbox execution with security violation
        assert report.tests_passed is False
        assert report.test_result["status"] == "blocked"
        assert "SECURITY_VIOLATION" in report.test_result["error"]


# 7. Agent Cannot Bypass Sandbox Path Restrictions
@pytest.mark.asyncio
async def test_07_agent_cannot_bypass_sandbox_path_restrictions():
    """Verify path traversal attempts in diff proposal are rejected immediately."""
    diff_gen = DiffGenerator()

    # Attempt path traversal outside workspace
    res = diff_gen.create_patch_proposal(
        target_file="../../etc/evil_patch.py",
        proposed_content="malicious = True\n",
        rationale="Jail breakout attempt",
    )
    # Target path outside workspace triggers error
    assert res.patch_id is None
    assert res.request_id is None


# 8. Failed Tests Reach the Critique Stage Rather Than Being Falsely Reported
@pytest.mark.asyncio
async def test_08_failed_tests_reach_critique_truthfully():
    """Verify that failing test commands are captured accurately and evaluated in Critique."""
    agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))

    report = await agent.run(
        task="Implement feature with intentional test assertion failure",
        target_file="broken_feature.py",
        test_command="python -c \"import sys; print('TEST_REGRESSION'); sys.exit(1)\"",
        proposed_code="def broken(): pass\n",
        skip_rag=True,
    )

    # Invariant: Truth in reporting — test failure must NOT be disguised as pass
    assert report.tests_passed is False
    assert report.test_result["passed"] is False
    assert report.test_result["exit_code"] == 1
    assert "TEST_REGRESSION" in report.test_result["stdout"]
    # Critique stage must be executed and capture failure
    assert AgentStage.CRITIQUE in report.stages_executed
    assert "FAILED" in report.critique or "7/10" in report.critique


# 9. Final Report Accurately Reflects Execution and Test Results
@pytest.mark.asyncio
async def test_09_final_report_accuracy():
    """Verify final report markdown contains accurate diff, exit codes, and status."""
    agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))

    report = await agent.run(
        task="Add greeting function to greetings.py",
        target_file="greetings.py",
        test_command="python -c \"print('ALL_UNIT_TESTS_PASS')\"",
        proposed_code="def greet(name: str) -> str:\n    return f'Hello, {name}!'\n",
        skip_rag=True,
    )

    assert report.tests_passed is True
    assert "ALL_UNIT_TESTS_PASS" in report.test_result["stdout"]
    assert "def greet(name: str)" in report.final_report
    assert "PASSED" in report.final_report
    assert "WAITING_FOR_HUMAN_APPROVAL" in report.final_report


# 10. Multi-Provider Factory Abstraction
def test_10_multi_provider_instantiation():
    """Verify LLMClient instantiates Ollama, Groq, HF, and Mock providers properly."""
    client_mock = LLMClient(provider_name="synthetic_mock")
    assert isinstance(client_mock.provider, DeterministicMockProvider)

    with patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://127.0.0.1:11434"}):
        client_ollama = LLMClient(provider_name="ollama")
        assert isinstance(client_ollama.provider, OllamaProvider)

    with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_test_1234567890abcdef"}):
        client_groq = LLMClient(provider_name="groq_free")
        assert isinstance(client_groq.provider, GroqFreeProvider)

    with patch.dict("os.environ", {"HF_TOKEN": "hf_test_1234567890abcdef"}):
        client_hf = LLMClient(provider_name="hf_free")
        assert isinstance(client_hf.provider, HuggingFaceFreeProvider)
