"""
Comprehensive Verification Suite for Phase 4 Security Model:
PROPOSE -> HUMAN APPROVAL -> EXECUTE

Validates all 18 mandatory requirements:
 1. git status executes without approval (AUTO_ALLOWED).
 2. git diff executes without approval (AUTO_ALLOWED).
 3. git push is proposed but NOT executed without approval.
 4. git push executes after explicit approval.
 5. changing the approved command invalidates the approval (Action-hash bound).
 6. network request is proposed but not executed without approval.
 7. network executes only after approval.
 8. patch is proposed but not applied without approval.
 9. patch applies after approval.
10. workspace escape remains blocked even after approval (Approval is not a bypass).
11. dangerous sandbox escape remains blocked even after approval.
12. secret request produces a secure secret-input flow.
13. supplied secret is available only to the approved execution.
14. supplied secret is redacted from logs.
15. "where is API key used?" returns references, not the secret value.
16. explicit secret disclosure triggers a separate high-risk confirmation.
17. rejected approval does not execute the operation.
18. approval for action A cannot authorize materially different action B.
"""

import os
from pathlib import Path

from src.config import get_settings
from src.mcp_server.tools.patch import apply_patch_tool, propose_patch_tool
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import (
    ActionCategory,
    PolicyVerdict,
    classify_action,
    get_approval_manager,
)
from src.sandbox.runner import execute_sandboxed_command
from src.sandbox.secrets import (
    inspect_secret_references,
    request_secret,
    reveal_secret_if_confirmed,
)


# Helper fixture to ensure clean approval and audit state
def _reset_state():
    get_approval_manager().clear()
    get_audit_logger().clear()


# 1. git status executes without approval (AUTO_ALLOWED)
def test_01_git_status_executes_without_approval():
    _reset_state()
    proposal = classify_action("git status")
    assert proposal.verdict == PolicyVerdict.AUTO_ALLOWED
    assert proposal.category == ActionCategory.GIT_READ
    assert proposal.requires_human_approval is False

    res = execute_sandboxed_command("git status")
    assert res.get("status") != "WAITING_FOR_HUMAN_APPROVAL"
    assert res.get("requires_approval") is not True


# 2. git diff executes without approval (AUTO_ALLOWED)
def test_02_git_diff_executes_without_approval():
    _reset_state()
    proposal = classify_action("git diff")
    assert proposal.verdict == PolicyVerdict.AUTO_ALLOWED
    assert proposal.requires_human_approval is False

    res = execute_sandboxed_command("git diff")
    assert res.get("status") != "WAITING_FOR_HUMAN_APPROVAL"


# 3. git push is proposed but NOT executed without approval
def test_03_git_push_is_proposed_not_executed_without_approval():
    _reset_state()
    res = execute_sandboxed_command("git push origin main")
    assert res["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    assert res["passed"] is False
    assert res["requires_approval"] is True
    assert "request_id" in res
    assert "action_hash" in res
    assert "HUMAN APPROVAL REQUIRED" in res["ui"]
    assert "Waiting for human approval" in res["ui"]
    assert res["proposal"]["category"] == ActionCategory.GIT_NETWORK.value
    assert res["proposal"]["network_required"] is True


# 4. git push executes after explicit approval
def test_04_git_push_executes_after_explicit_approval():
    _reset_state()
    approval_mgr = get_approval_manager()

    # Step 1: Agent proposes action
    proposal = approval_mgr.create_proposal(
        command="git push origin main",
        network_requested=True,
        reason="Publish verified bugfix to origin main branch",
    )
    assert proposal.status == "PENDING_APPROVAL"

    # Step 2: Human approves the exact proposal
    token = approval_mgr.submit_approval(
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        approved=True,
    )
    assert token.approved is True

    # Step 3: Execution proceeds with valid token
    res = execute_sandboxed_command(
        command="git push origin main",
        approval_token=token,
    )
    # Execution must NOT be blocked by approval check
    assert res.get("status") != "WAITING_FOR_HUMAN_APPROVAL"
    assert res.get("status") != "APPROVAL_INVALID"
    # Token must now be consumed
    assert token.consumed is True


# 5. changing the approved command invalidates the approval (Action-hash bound)
def test_05_changing_approved_command_invalidates_approval():
    _reset_state()
    approval_mgr = get_approval_manager()

    # Human approves 'git push origin main'
    proposal = approval_mgr.create_proposal(
        command="git push origin main",
        network_requested=True,
    )
    token = approval_mgr.submit_approval(
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        approved=True,
    )

    # Malicious or unintended alteration to 'git push origin production'
    res1 = execute_sandboxed_command(
        command="git push origin production",
        approval_token=token,
    )
    assert res1["status"] == "APPROVAL_INVALID"
    assert "ACTION_HASH_MISMATCH" in res1["error"]

    # Alteration to 'git push --force'
    res2 = execute_sandboxed_command(
        command="git push --force origin main",
        approval_token=token,
    )
    assert res2["status"] == "APPROVAL_INVALID"


# 6. network request is proposed but not executed without approval
def test_06_network_request_proposed_not_executed_without_approval():
    _reset_state()
    cmd = "python -c \"import urllib.request; print('NETWORK_TEST')\""
    res = execute_sandboxed_command(
        command=cmd,
        allow_network=True,
        rationale="Download external CVE definition dataset",
    )
    assert res["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    assert res["proposal"]["network_required"] is True
    assert res["proposal"]["category"] == ActionCategory.NETWORK_REQUEST.value


# 7. network executes only after approval
def test_07_network_executes_only_after_approval():
    _reset_state()
    approval_mgr = get_approval_manager()
    audit = get_audit_logger()

    cmd = "python -c \"print('NETWORK_AUTHORIZED')\""
    proposal = approval_mgr.create_proposal(
        command=cmd,
        network_requested=True,
        reason="Ephemeral network synchronization",
    )
    token = approval_mgr.submit_approval(
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        approved=True,
    )

    res = execute_sandboxed_command(
        command=cmd,
        allow_network=True,
        approval_token=token,
    )
    assert res["status"] == "success"
    assert "NETWORK_AUTHORIZED" in res["stdout"]

    # Check audit log confirms network capability was granted only for this run
    events = audit.get_recent_events(limit=5)
    exec_event = next(e for e in events if e["event_type"] == "COMMAND_EXEC")
    assert exec_event["network_capability"] is True


# 8. patch is proposed but not applied without approval
def test_08_patch_proposed_not_applied_without_approval():
    _reset_state()
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target = workspace / "src_patch_test.py"
    if target.exists():
        target.unlink()

    proposal_res = propose_patch_tool(
        target_file="src_patch_test.py",
        proposed_content="def unapproved_code(): return 42\n",
        rationale="Add unapproved function",
    )
    assert proposal_res["status"] == "PENDING_APPROVAL"
    assert target.exists() is False  # Must not modify disk


# 9. patch applies after approval
def test_09_patch_applies_after_approval():
    _reset_state()
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    target = workspace / "src_patch_test.py"
    if target.exists():
        target.unlink()

    proposal_res = propose_patch_tool(
        target_file="src_patch_test.py",
        proposed_content="def approved_function(): return 100\n",
        rationale="Implement approved arithmetic feature",
    )
    patch_id = proposal_res["patch_id"]
    req_id = proposal_res["request_id"]
    act_hash = proposal_res["action_hash"]

    # Try applying without approval
    unauth_res = apply_patch_tool(patch_id=patch_id, approval_token=None)
    assert unauth_res["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    assert target.exists() is False

    # Grant approval
    approval_mgr = get_approval_manager()
    token = approval_mgr.submit_approval(request_id=req_id, action_hash=act_hash, approved=True)

    # Apply with approval and automated test verification
    auth_res = apply_patch_tool(
        patch_id=patch_id,
        approval_token=token.model_dump(),
        test_command="python -c \"import src_patch_test; assert src_patch_test.approved_function() == 100\"",
    )
    assert auth_res["status"] == "APPLIED"
    assert target.exists() is True
    assert "approved_function" in target.read_text(encoding="utf-8")
    assert "final_report" in auth_res
    assert auth_res["final_report"]["applied"] is True
    assert auth_res["final_report"]["tests_passed"] is True
    assert "PASSED" in auth_res["final_report"]["verification_summary"]

    # Cleanup
    if target.exists():
        target.unlink()


# 10. workspace escape remains blocked even after approval (Approval is not a bypass)
def test_10_workspace_escape_remains_blocked_after_approval():
    _reset_state()

    # Even if an operator accidentally generated an approval token for an escape path
    fake_token = {
        "request_id": "req_bypass_attempt",
        "action_hash": "hash_fake",
        "approved": True,
    }

    # Attempting to read outside workspace jail
    res = execute_sandboxed_command(
        command="python ../../etc/passwd",
        approval_token=fake_token,
    )
    assert res["status"] == "blocked"
    assert res["exit_code"] == 126
    assert "SECURITY_VIOLATION" in res["error"]


# 11. dangerous sandbox escape remains blocked even after approval
def test_11_dangerous_sandbox_escape_remains_blocked_after_approval():
    _reset_state()
    fake_token = {
        "request_id": "req_bypass_token",
        "action_hash": "hash_fake",
        "approved": True,
    }

    for dangerous_cmd in [
        "curl http://169.254.169.254/latest/meta-data/",
        "sudo rm -rf /",
        "bash -c 'id'",
        "nc -lvp 4444",
        "python -c 'print(1)' ; rm -rf /",
    ]:
        res = execute_sandboxed_command(dangerous_cmd, approval_token=fake_token)
        assert res["status"] == "blocked"
        assert res["exit_code"] == 126
        assert "SECURITY_VIOLATION" in res["error"]


# 12. secret request produces a secure secret-input flow
def test_12_secret_request_produces_secure_flow():
    _reset_state()
    req = request_secret(
        secret_name="OPENAI_API_KEY",
        reason="Required to invoke model embedding benchmark",
        scope="current_task",
    )
    assert req["type"] == "secret_request"
    assert req["secret_name"] == "OPENAI_API_KEY"
    assert req["execution_scope"] == "current_task"
    assert "Required to invoke" in req["reason"]


# 13. supplied secret is available only to the approved execution
def test_13_supplied_secret_available_only_to_approved_execution():
    _reset_state()
    approval_mgr = get_approval_manager()

    cmd = "python -c \"import os; print('KEY_DETECTED=' + str('sk-secret998877' in os.environ.get('PROVIDER_KEY', '')))\""
    proposal = approval_mgr.create_proposal(
        command=cmd,
        secrets_requested=["PROVIDER_KEY"],
        reason="Authenticated API call",
    )
    token = approval_mgr.submit_approval(proposal.request_id, proposal.action_hash, approved=True)

    secret_val = "sk-secret998877665544332211"
    res = execute_sandboxed_command(
        command=cmd,
        secrets={"PROVIDER_KEY": secret_val},
        approval_token=token,
    )
    assert res["status"] == "success"
    assert "KEY_DETECTED=True" in res["stdout"]

    # Verify secret is absent from host parent environment
    assert "PROVIDER_KEY" not in os.environ


# 14. supplied secret is redacted from logs
def test_14_supplied_secret_is_redacted_from_logs():
    _reset_state()
    approval_mgr = get_approval_manager()

    secret_key = "sk-live_credential_999888777"
    cmd = f"python -c \"print('DEBUG: {secret_key}')\""
    proposal = approval_mgr.create_proposal(command=cmd, secrets_requested=["SECRET_TOKEN"])
    token = approval_mgr.submit_approval(proposal.request_id, proposal.action_hash, approved=True)

    res = execute_sandboxed_command(
        command=cmd,
        secrets={"SECRET_TOKEN": secret_key},
        approval_token=token,
    )
    assert secret_key not in res["stdout"]
    assert "[REDACTED_SECRET]" in res["stdout"]

    # Verify disk audit log contains zero plaintext secret instances
    settings = get_settings()
    audit_file = settings.SCRATCH_DIR / "audit_log.jsonl"
    if audit_file.exists():
        raw_log = audit_file.read_text(encoding="utf-8")
        assert secret_key not in raw_log


# 15. "where is API key used?" returns references, not the secret value
def test_15_where_is_api_key_used_returns_references_not_secret():
    _reset_state()
    res = inspect_secret_references("Where is the API key used in this project?")
    assert res["disclosure_type"] == "REFERENCE_DISCOVERY"
    assert res["reference_count"] > 0
    # Returns file citations, not actual credential strings
    assert any("config.py" in ref["file"] for ref in res["references"])
    assert all("sk-" not in ref["context"] for ref in res["references"])


# 16. explicit secret disclosure triggers a separate high-risk confirmation
def test_16_explicit_secret_disclosure_triggers_high_risk_confirmation():
    _reset_state()
    # Step 1: Request without confirmation token
    res1 = reveal_secret_if_confirmed("OPENAI_API_KEY", confirmation_token=False)
    assert res1["status"] == "CONFIRMATION_REQUIRED"
    assert res1["revealed"] is False
    assert res1["challenge"]["challenge_type"] == "HIGH_RISK_SECRET_DISCLOSURE"
    assert "expose the secret in the conversation" in res1["challenge"]["warning"]

    # Step 2: Request with confirmed token
    res2 = reveal_secret_if_confirmed("OPENAI_API_KEY", confirmation_token=True)
    # Even when confirmed, returns properly flagged status
    assert res2["status"] in {"DISCLOSED_AFTER_CONFIRMATION", "NOT_FOUND"}


# 17. rejected approval does not execute the operation
def test_17_rejected_approval_does_not_execute():
    _reset_state()
    approval_mgr = get_approval_manager()

    proposal = approval_mgr.create_proposal(
        command="git push origin main",
        network_requested=True,
    )
    # Operator clicks [Reject]
    token = approval_mgr.submit_approval(
        request_id=proposal.request_id,
        action_hash=proposal.action_hash,
        approved=False,
        rejection_reason="Unauthorized push to main branch",
    )
    assert token.approved is False

    res = execute_sandboxed_command(
        command="git push origin main",
        approval_token=token,
    )
    assert res["status"] == "APPROVAL_INVALID"
    assert "APPROVAL_REJECTED" in res["error"]
    assert res["passed"] is False


# 18. approval for action A cannot authorize materially different action B
def test_18_approval_for_action_a_cannot_authorize_action_b():
    _reset_state()
    approval_mgr = get_approval_manager()

    # Action A: Git commit
    prop_a = approval_mgr.create_proposal(command="git commit -m 'feat: add login'")
    token_a = approval_mgr.submit_approval(prop_a.request_id, prop_a.action_hash, approved=True)

    # Attacker or agent attempts to use Token A to execute Action B (Package installation)
    res_b = execute_sandboxed_command(
        command="npm install lodash",
        approval_token=token_a,
    )
    assert res_b["status"] == "APPROVAL_INVALID"
    assert "ACTION_HASH_MISMATCH" in res_b["error"]
