"""
Tests for Sandbox Timeout and Human Approval Fix:
1. Default timeout handling (proposal & UI display).
2. Approved extended timeout (e.g. 60s) executes successfully using exact approved timeout.
3. Timeout tampering after approval (approving 60s cannot be reused for 600s or 5s).
4. Hard system maximum timeout enforcement (SANDBOX_MAX_TIMEOUT_SEC rejection).
5. Backward compatibility for existing callers without explicit timeout_sec.
"""

from unittest.mock import MagicMock, patch

from src.config import get_settings
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import (
    PolicyVerdict,
    RiskLevel,
    classify_action,
    compute_action_hash,
    get_approval_manager,
)
from src.sandbox.runner import execute_sandboxed_command


def _reset_state():
    get_approval_manager().clear()
    get_audit_logger().clear()


def test_01_default_timeout():
    """Verify default timeout is applied and presented in the approval UI."""
    _reset_state()
    settings = get_settings()

    # Proposal with default/unspecified timeout
    proposal = classify_action("git commit -m 'test'")
    assert proposal.timeout_sec is None
    # UI representation displays default timeout
    assert f"{settings.SANDBOX_TIMEOUT_SEC}s (Default)" in proposal.ui_representation
    assert "REQUESTED TIMEOUT:" in proposal.ui_representation

    # Compute action hash matches default
    expected_hash = compute_action_hash(
        command="git commit -m 'test'",
        category=proposal.category.value,
        network=False,
        files=[],
        secrets=[],
        timeout_sec=settings.SANDBOX_TIMEOUT_SEC,
    )
    assert proposal.action_hash == expected_hash


def test_02_approved_extended_timeout():
    """Verify that an approved extended timeout (e.g. 60s) is executed with exact 60s timeout."""
    _reset_state()
    approval_mgr = get_approval_manager()

    requested_timeout = 60
    cmd = "python -c \"print('APPROVED_MIGRATION')\""
    proposal = approval_mgr.create_proposal(
        command=cmd,
        network_requested=True,
        timeout_sec=requested_timeout,
    )
    assert proposal.timeout_sec == requested_timeout
    assert f"{requested_timeout}s" in proposal.ui_representation
    assert "(Default)" not in proposal.ui_representation

    # Submit human approval
    token = approval_mgr.submit_approval(
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        approved=True,
    )
    assert token.approved is True

    # Mock subprocess execution to verify exact timeout passed to communicate
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("APPROVED_MIGRATION\n", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        res = execute_sandboxed_command(
            command=cmd,
            allow_network=True,
            approval_token=token,
            timeout_sec=requested_timeout,
        )

        assert res["status"] == "success"
        assert res["passed"] is True
        # Verify that subprocess communicate was called with exact approved timeout (60s)
        mock_proc.communicate.assert_called_once()
        assert mock_proc.communicate.call_args[1]["timeout"] == 60


def test_03_timeout_tampering_after_approval():
    """Verify that an approval granted for 60s cannot be used to execute with 600s."""
    _reset_state()
    approval_mgr = get_approval_manager()

    # Agent requests approval for 60s
    proposal = approval_mgr.create_proposal(
        command="git commit -m 'legitimate work'",
        timeout_sec=60,
    )

    token = approval_mgr.submit_approval(
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        approved=True,
    )

    # Attacker tries to execute with tampered 600s timeout using the 60s approval token
    res = execute_sandboxed_command(
        command="git commit -m 'legitimate work'",
        approval_token=token,
        timeout_sec=600,
    )

    assert res["status"] in {"blocked", "APPROVAL_INVALID"}
    assert res["passed"] is False
    assert "ACTION_HASH_MISMATCH" in res["error"] or "SECURITY_VIOLATION" in res["error"]

    # Also verify that the token was NOT consumed by the failed tampered execution
    # and trying to consume directly with wrong timeout fails
    valid, err = approval_mgr.verify_and_consume_approval(
        request_id=token.request_id,
        command="git commit -m 'legitimate work'",
        category=proposal.category.value,
        timeout_sec=600,
    )
    assert valid is False
    assert "ACTION_HASH_MISMATCH" in err


def test_04_maximum_timeout_enforcement():
    """Verify that requesting a timeout exceeding the system maximum is rejected immediately."""
    _reset_state()
    settings = get_settings()

    excessive_timeout = settings.SANDBOX_MAX_TIMEOUT_SEC + 100

    # 1. Direct classification
    proposal = classify_action(
        command="git commit -m 'unbounded work'",
        timeout_sec=excessive_timeout,
    )
    assert proposal.verdict == PolicyVerdict.ALWAYS_BLOCKED
    assert proposal.risk_level == RiskLevel.CRITICAL
    assert proposal.status == "BLOCKED"
    assert proposal.requires_human_approval is False
    assert "exceeds maximum allowed system limit" in proposal.reason

    # 2. Execution attempt without approval fails immediately
    res = execute_sandboxed_command(
        command="git commit -m 'unbounded work'",
        timeout_sec=excessive_timeout,
    )
    assert res["status"] == "blocked"
    assert "exceeds maximum allowed system limit" in res["error"]


def test_05_backward_compatibility():
    """Verify that existing callers without timeout_sec continue to work seamlessly."""
    _reset_state()
    approval_mgr = get_approval_manager()

    cmd = "python -c \"print('LEGACY_CALLER_OK')\""
    # Proposal created without timeout_sec
    proposal = approval_mgr.create_proposal(
        command=cmd,
        network_requested=True,
    )
    assert proposal.verdict == PolicyVerdict.APPROVAL_REQUIRED
    assert proposal.timeout_sec is None

    token = approval_mgr.submit_approval(
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        approved=True,
    )

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("LEGACY_CALLER_OK\n", "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        # Call execute_sandboxed_command without timeout_sec
        res = execute_sandboxed_command(
            command=cmd,
            allow_network=True,
            approval_token=token,
        )

        assert res["status"] == "success"
        assert res["passed"] is True
        # Uses default settings.SANDBOX_TIMEOUT_SEC
        settings = get_settings()
        assert mock_proc.communicate.call_args[1]["timeout"] == settings.SANDBOX_TIMEOUT_SEC
