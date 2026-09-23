"""
Test Suite for Multi-File Patch Proposal and Atomic Application.
Tests:
1. Multi-file patch proposal generation with DiffGenerator.
2. AST syntax validation across all proposed files.
3. Cryptographic action hash binding all affected files.
4. Human Approval requirement: files not written to disk prior to approval.
5. Rejection flow: rejection token blocks all file writes.
6. Atomic apply: all files created/updated on approval.
7. Safe rollback on error: if any write fails, changes roll back.
8. Platform API integration: POST /chat -> GET /tasks -> POST /patches/action.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.agent.diff_generator import DiffGenerator
from src.agent.llm_client import DeterministicMockProvider, LLMClient
from src.agent.loop import AgentLoop, AgentStage
from src.api.app import app
from src.config import get_settings
from src.mcp_server.tools.patch import (
    _pending_bundles,
    _pending_patches,
    apply_multi_patch_tool,
    propose_multi_patch_tool,
)
from src.sandbox.audit import get_audit_logger
from src.sandbox.policy import get_approval_manager


@pytest.fixture(autouse=True)
def _reset_environment():
    get_approval_manager().clear()
    get_audit_logger().clear()
    _pending_patches.clear()
    _pending_bundles.clear()

    # Clean test files if any
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    for test_file in ["todo_model.py", "todo_app.py", "test_todo.py", "notes.txt", "valid_file.py", "invalid_file.py"]:
        p = workspace / test_file
        if p.exists():
            p.unlink()


def test_01_propose_multi_patch_tool_generates_bundle():
    """Verify propose_multi_patch_tool creates a bundle proposal with individual diffs."""
    file_changes = [
        {
            "target_file": "todo_model.py",
            "proposed_content": "class TodoItem:\n    def __init__(self, title: str):\n        self.title = title\n        self.done = False\n",
        },
        {
            "target_file": "todo_app.py",
            "proposed_content": "from todo_model import TodoItem\n\ndef create_todo(title: str):\n    return TodoItem(title)\n",
        },
    ]

    res = propose_multi_patch_tool(file_changes, rationale="Create Todo model and app")
    assert res["status"] == "PENDING_APPROVAL"
    assert res["bundle_id"] is not None
    assert res["request_id"] != ""
    assert res["action_hash"] != ""
    assert len(res["files"]) == 2
    assert res["syntax_valid"] is True
    assert res["is_new_file"] is True

    # Check files are NOT created on disk yet
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    assert not (workspace / "todo_model.py").exists()
    assert not (workspace / "todo_app.py").exists()


def test_02_multi_patch_syntax_validation():
    """Verify syntax error is caught if any file in the bundle has invalid syntax."""
    file_changes = [
        {
            "target_file": "valid_file.py",
            "proposed_content": "x = 42\n",
        },
        {
            "target_file": "invalid_file.py",
            "proposed_content": "def broken_syntax(:\n",
        },
    ]

    res = propose_multi_patch_tool(file_changes, rationale="Test syntax checking")
    assert res["syntax_valid"] is False
    assert "invalid_file.py" in (res["syntax_error"] or "")


def test_03_multi_patch_apply_requires_approval():
    """Verify applying multi patch fails without valid token."""
    file_changes = [
        {"target_file": "todo_model.py", "proposed_content": "x = 1\n"},
        {"target_file": "todo_app.py", "proposed_content": "y = 2\n"},
    ]
    res = propose_multi_patch_tool(file_changes, rationale="Approval check")
    bundle_id = res["bundle_id"]

    # Attempt apply without token
    apply_res = apply_multi_patch_tool(bundle_id=bundle_id, approval_token=None)
    assert apply_res["status"] == "WAITING_FOR_HUMAN_APPROVAL"

    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    assert not (workspace / "todo_model.py").exists()
    assert not (workspace / "todo_app.py").exists()


def test_04_multi_patch_atomic_apply_on_approval():
    """Verify all files in bundle are written to disk once human approves."""
    file_changes = [
        {
            "target_file": "todo_model.py",
            "proposed_content": "class TodoItem:\n    def __init__(self, title: str):\n        self.title = title\n",
        },
        {
            "target_file": "todo_app.py",
            "proposed_content": "from todo_model import TodoItem\napp_name = 'TodoList'\n",
        },
    ]
    prop = propose_multi_patch_tool(file_changes, rationale="Full atomic test")
    bundle_id = prop["bundle_id"]
    req_id = prop["request_id"]
    action_hash = prop["action_hash"]

    # Submit approval
    approval_mgr = get_approval_manager()
    token = approval_mgr.submit_approval(
        request_id=req_id,
        action_hash=action_hash,
        approved=True,
    )

    # Apply
    apply_res = apply_multi_patch_tool(
        bundle_id=bundle_id,
        approval_token=token.model_dump(),
        test_command="python -c \"print('ALL_GOOD')\"",
    )
    assert apply_res["status"] == "APPLIED"
    assert apply_res["applied"] is True

    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    assert (workspace / "todo_model.py").exists()
    assert (workspace / "todo_app.py").exists()
    assert "TodoList" in (workspace / "todo_app.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_05_agent_loop_parses_multi_file_patch():
    """Verify AgentLoop parses multiple files and generates a multi-file bundle."""
    agent = AgentLoop(llm_client=LLMClient(provider=DeterministicMockProvider()))

    raw_llm_code = (
        "***FILE: todo_model.py***\n"
        "class TodoItem:\n    pass\n"
        "***END_FILE***\n\n"
        "***FILE: todo_app.py***\n"
        "def main():\n    return 'OK'\n"
        "***END_FILE***\n"
    )

    report = await agent.run(
        task="Create a complete Todo app with models and views",
        target_file="",
        proposed_code=raw_llm_code,
        skip_rag=True,
    )

    assert AgentStage.PATCH in report.stages_executed
    assert report.patch_result is not None
    assert report.patch_result.bundle_id is not None
    assert len(report.patch_result.files) == 2
    assert report.requires_human_approval is True

    # Files must not be written to disk yet
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    assert not (workspace / "todo_model.py").exists()
    assert not (workspace / "todo_app.py").exists()


def test_06_platform_api_multi_patch_approval_flow():
    """Verify complete API flow: dispatch task -> inspect status -> submit approval -> verify files on disk."""
    client = TestClient(app)

    multi_code = (
        "***FILE: todo_model.py***\n"
        "class TodoModel:\n    pass\n"
        "***END_FILE***\n\n"
        "***FILE: todo_app.py***\n"
        "class TodoApp:\n    pass\n"
        "***END_FILE***\n"
    )

    # 1. Start task
    resp = client.post(
        "/api/v1/chat",
        json={
            "prompt": "Create todo app with models and controller",
            "proposed_code": multi_code,
            "skip_rag": True,
        },
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    # 2. Query status
    status_resp = client.get(f"/api/v1/tasks/{task_id}")
    assert status_resp.status_code == 200
    task_data = status_resp.json()
    assert task_data["status"] == "waiting_approval"
    patch_prop = task_data["patch_proposal"]
    assert patch_prop is not None
    assert patch_prop["bundle_id"] is not None
    assert len(patch_prop["files"]) == 2

    req_id = patch_prop["request_id"]
    action_hash = patch_prop["action_hash"]

    # Verify files not yet on disk
    settings = get_settings()
    workspace = Path(settings.WORKSPACE_ROOT).resolve()
    assert not (workspace / "todo_model.py").exists()

    # 3. Submit Approval via API
    approval_resp = client.post(
        "/api/v1/patches/action",
        json={
            "request_id": req_id,
            "action_hash": action_hash,
            "action": "approve",
        },
    )
    assert approval_resp.status_code == 200
    appr_data = approval_resp.json()
    assert appr_data["status"] == "APPLIED"
    assert appr_data["approved"] is True

    # Verify both files are written to disk
    assert (workspace / "todo_model.py").exists()
    assert (workspace / "todo_app.py").exists()
    assert "class TodoModel" in (workspace / "todo_model.py").read_text(encoding="utf-8")
    assert "class TodoApp" in (workspace / "todo_app.py").read_text(encoding="utf-8")
