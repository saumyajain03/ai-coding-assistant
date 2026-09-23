"""
End-to-End Manual Test Runner for Phase 4: Cart Service & Promotional Coupons.
Demonstrates:
  1. Uploading feature spec + buggy code + unit tests
  2. Pure Planning Phase -> Stage 1-3 + Plan roadmap + Citations
  3. Implementation Phase -> Stage 4 Patch generation + Syntax/Risk check -> HITL Gate
  4. Human Operator Approval -> Cryptographic verification -> Patch applied to disk
  5. Post-apply Sandbox Regression Tests -> 100% Pass
"""
import os
import time
import json
import requests
import subprocess
from pathlib import Path

BASE_URL = "http://localhost:8001/api/v1"
TEST_DIR = Path("/Users/saumyajain/Desktop/dexter/data/test_cases/phase4_cart_service")

def step(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)

def main():
    step("0. PRE-FLIGHT: Verify baseline tests fail on unpatched code")
    res = subprocess.run(
        [".venv/bin/pytest", str(TEST_DIR / "test_cart_service.py"), "-v"],
        capture_output=True,
        text=True,
        cwd="/Users/saumyajain/Desktop/dexter"
    )
    print(f"Pre-flight exit code: {res.returncode} (expected != 0 because stub is incomplete)")
    assert res.returncode != 0, "Tests must fail on the unpatched stub!"
    print("Pre-flight confirmed: Stub fails tests as expected.")

    step("1. UPLOAD & INGESTION: Upload cart_spec.md, cart_service.py, test_cart_service.py")
    files_to_upload = [
        ("files", ("cart_spec.md", open(TEST_DIR / "cart_spec.md", "rb"), "text/markdown")),
        ("files", ("cart_service.py", open(TEST_DIR / "cart_service.py", "rb"), "text/x-python")),
        ("files", ("test_cart_service.py", open(TEST_DIR / "test_cart_service.py", "rb"), "text/x-python")),
    ]
    resp = requests.post(f"{BASE_URL}/upload?clear_previous=true", files=files_to_upload)
    print(f"Upload status: {resp.status_code}")
    assert resp.status_code == 200
    for item in resp.json():
        print(f"  Indexed: {item['filename']} ({item['chunk_count']} chunks, status: {item['status']})")

    step("2. PLANNING PHASE: Request architectural plan based on spec (no code mutation)")
    plan_payload = {
        "prompt": "Provide an architectural and implementation plan for the CartService based on cart_spec.md and test_cart_service.py",
        "target_file": "",
        "test_command": "pytest test_cart_service.py"
    }
    chat_resp = requests.post(f"{BASE_URL}/chat", json=plan_payload)
    assert chat_resp.status_code == 202
    plan_task_id = chat_resp.json()["task_id"]
    print(f"Plan Task ID: {plan_task_id}")

    print("Polling planning task (2s intervals)...")
    plan_state = None
    for _ in range(30):
        time.sleep(2)
        res = requests.get(f"{BASE_URL}/tasks/{plan_task_id}")
        if res.status_code != 200:
            print(f"  Polling warning ({res.status_code}): {res.text[:100]}")
            continue
        t_resp = res.json()
        status = t_resp.get("status")
        stage = t_resp.get("current_stage")
        print(f"  Status: {status} | Stage: {stage}")
        if status in ("completed", "failed"):
            plan_state = t_resp
            break

    assert plan_state is not None, "Planning task did not finish in time"
    print(f"\nPlanning completed: status={plan_state['status']}")
    print(f"Citations count: {len(plan_state.get('citations', []))}")
    print(f"Plan summary preview: {plan_state.get('plan', '')[:200]}...")

    print("\nWaiting 10s cooldown to respect API rate limits...")
    time.sleep(10)

    step("3. IMPLEMENTATION PHASE: Dispatch coding agent to patch cart_service.py")
    impl_payload = {
        "prompt": "Implement the complete CartService in cart_service.py to satisfy all coupon requirements in cart_spec.md and make test_cart_service.py pass",
        "target_file": "cart_service.py",
        "test_command": "pytest test_cart_service.py"
    }
    impl_resp = requests.post(f"{BASE_URL}/chat", json=impl_payload)
    assert impl_resp.status_code == 202
    impl_task_id = impl_resp.json()["task_id"]
    print(f"Implementation Task ID: {impl_task_id}")

    print("Polling implementation task until HITL approval gate...")
    task_state = None
    for _ in range(45):
        time.sleep(2)
        res = requests.get(f"{BASE_URL}/tasks/{impl_task_id}")
        if res.status_code != 200:
            print(f"  Polling warning ({res.status_code}): {res.text[:100]}")
            continue
        t_resp = res.json()
        status = t_resp.get("status")
        stage = t_resp.get("current_stage")
        print(f"  Status: {status} | Stage: {stage}")
        if status in ("waiting_approval", "completed", "failed"):
            task_state = t_resp
            break

    assert task_state is not None, "Timed out waiting for task to reach HITL state"
    assert task_state["status"] == "waiting_approval", f"Expected waiting_approval, got {task_state['status']}"

    proposal = task_state.get("patch_proposal", {})
    req_id = proposal.get("request_id")
    action_hash = proposal.get("action_hash")
    print("\n--- HITL Gate Reached! ---")
    print(f"Target File: {proposal.get('target_file')}")
    print(f"Request ID: {req_id}")
    print(f"Action Hash: {action_hash}")
    print(f"Risk Score: {proposal.get('risk_score')}/10")
    print(f"Syntax Valid: {proposal.get('syntax_valid')}")
    print(f"Lines Added: +{proposal.get('lines_added')} | Lines Removed: -{proposal.get('lines_removed')}")

    step("4. HITL APPROVAL: Submit operator approval with cryptographic action hash")
    action_payload = {
        "request_id": req_id,
        "action_hash": action_hash,
        "action": "approve",
        "reason": "Approved by automated test suite"
    }
    act_resp = requests.post(f"{BASE_URL}/patches/action", json=action_payload)
    print(f"Action response status: {act_resp.status_code}")
    act_data = act_resp.json()
    print(f"Patch applied: {act_data.get('status') == 'APPLIED'}")
    
    test_res = act_data.get("test_result", {})
    print(f"Post-apply verification tests passed: {test_res.get('passed')}")
    print(f"Exit code: {test_res.get('exit_code')}")
    print("\nVerification Test Output:")
    print(test_res.get("stdout", "") or test_res.get("stderr", ""))

    step("5. VERIFY FINAL TASK STATE ON POLLING")
    final_task = requests.get(f"{BASE_URL}/tasks/{impl_task_id}").json()
    print(f"Final task status: {final_task.get('status')}")
    print(f"Tests passed flag: {final_task.get('tests_passed')}")

if __name__ == "__main__":
    main()
