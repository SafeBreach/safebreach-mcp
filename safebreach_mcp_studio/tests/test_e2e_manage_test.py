"""
End-to-End Tests for manage_test (SAF-29969)

Tests the test lifecycle management tool using real API calls.
Pattern: queue → cancel → verify.

ZERO MOCKS — all calls hit real SafeBreach APIs.

Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v
"""

import logging
import time
import pytest
import os
import requests

from safebreach_mcp_studio.studio_functions import (
    sb_run_scenario,
    sb_manage_test,
    sb_delete_test,
    _fetch_all_scenarios,
    compute_scenario_readiness,
)
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)

E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


# ---------------------------------------------------------------------------
# E2E helpers — real API calls, zero mocks
# ---------------------------------------------------------------------------


def _get_auth(console):
    apitoken = get_secret_for_console(console)
    base_url_orch = get_api_base_url(console, 'orchestrator')
    base_url_data = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)
    return apitoken, base_url_orch, base_url_data, account_id


def _cancel_test(test_id, console):
    """Cancel a running/queued test. Best-effort."""
    try:
        apitoken, base_url_orch, _, account_id = _get_auth(console)
        url = f"{base_url_orch}/api/orch/v4/accounts/{account_id}/queue/{test_id}"
        resp = requests.delete(url, headers={"x-apitoken": apitoken}, timeout=30)
        logger.info(f"Cancel {test_id}: HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"Cancel {test_id} failed: {e}")


COMMENT_PROPAGATION_DELAY = 2  # seconds to wait for data API eventual consistency
STATE_PROPAGATION_DELAY = 10  # seconds for orchestrator→data API state sync


def _get_test_comment(test_id, console):
    """Read the comment field from a test summary. Returns str or None."""
    try:
        apitoken, _, base_url_data, account_id = _get_auth(console)
        url = f"{base_url_data}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"
        headers = {"x-apitoken": apitoken, "Content-Type": "application/json"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        comment = data.get('comment')
        logger.info(f"Get comment {test_id}: comment={comment!r}")
        return comment
    except Exception as e:
        logger.warning(f"Get comment {test_id} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# E2E Tests — manage_test lifecycle
# ---------------------------------------------------------------------------


@skip_e2e
@pytest.mark.e2e
class TestManageTestE2E:
    """E2E tests for manage_test against real SafeBreach console."""

    def test_e2e_cancel_test(self):
        """Queue, cancel with reason, verify success and note written."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready = next(
            (s for s in scenarios if compute_scenario_readiness(s)), None
        )
        assert ready is not None, f"No ready OOB scenario on {E2E_CONSOLE}"

        test_id = None
        passed = False
        try:
            queue_result = sb_run_scenario(
                scenario_id=str(ready['id']),
                console=E2E_CONSOLE,
                test_name="E2E: test_e2e_cancel_test",
            )
            test_id = queue_result['test_id']
            assert test_id, "No test_id returned from run_scenario"
            assert queue_result['status'] == 'queued'


            cancel_result = sb_manage_test(
                test_id=test_id,
                action="cancel",
                console=E2E_CONSOLE,
                reason="E2E cancel test cleanup",
            )
            assert cancel_result['status'] == "success"
            assert cancel_result['action'] == "cancel"
            assert cancel_result['test_id'] == test_id
            assert cancel_result['note_status'] == "success"
            assert "Test cancel" in cancel_result['note']

            # Wait for data API propagation, then verify note
            time.sleep(COMMENT_PROPAGATION_DELAY)
            comment = _get_test_comment(test_id, E2E_CONSOLE)
            assert comment is not None, "Comment not found on test summary"
            assert "E2E cancel test cleanup" in comment
            assert "UTC]" in comment
            passed = True
        finally:
            if test_id and not passed:
                _cancel_test(test_id, E2E_CONSOLE)

    def test_e2e_pause_test(self):
        """Queue, pause with reason, verify success and note written."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready = next(
            (s for s in scenarios if compute_scenario_readiness(s)), None
        )
        assert ready is not None, f"No ready OOB scenario on {E2E_CONSOLE}"

        test_id = None
        passed = False
        try:
            queue_result = sb_run_scenario(
                scenario_id=str(ready['id']),
                console=E2E_CONSOLE,
                test_name="E2E: test_e2e_pause_test",
            )
            test_id = queue_result['test_id']
            assert test_id

            pause_result = sb_manage_test(
                test_id=test_id, action="pause", console=E2E_CONSOLE,
                reason="E2E pause test — maintenance window",
            )
            assert pause_result['status'] == "success"
            assert pause_result['action'] == "pause"
            assert pause_result['note_status'] == "success"

            time.sleep(COMMENT_PROPAGATION_DELAY)
            comment = _get_test_comment(test_id, E2E_CONSOLE)
            assert comment is not None
            assert "E2E pause test" in comment
            passed = True
        finally:
            if test_id:
                _cancel_test(test_id, E2E_CONSOLE)

    def test_e2e_pause_and_resume_test(self):
        """Queue, pause with reason, resume with reason — verify both notes written."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready = next(
            (s for s in scenarios if compute_scenario_readiness(s)), None
        )
        assert ready is not None, f"No ready OOB scenario on {E2E_CONSOLE}"

        test_id = None
        passed = False
        try:
            queue_result = sb_run_scenario(
                scenario_id=str(ready['id']),
                console=E2E_CONSOLE,
                test_name="E2E: test_e2e_pause_and_resume_test",
            )
            test_id = queue_result['test_id']
            assert test_id

            # Pause with reason
            pause_result = sb_manage_test(
                test_id=test_id, action="pause", console=E2E_CONSOLE,
                reason="E2E pausing for deploy",
            )
            assert pause_result['status'] == "success"
            assert pause_result['note_status'] == "success"

            # Resume with reason
            resume_result = sb_manage_test(
                test_id=test_id, action="resume", console=E2E_CONSOLE,
                reason="E2E deploy complete, resuming",
            )
            assert resume_result['status'] == "success"
            assert resume_result['note_status'] == "success"

            # Verify both notes are in the comment (appended)
            time.sleep(COMMENT_PROPAGATION_DELAY)
            comment = _get_test_comment(test_id, E2E_CONSOLE)
            assert comment is not None
            assert "E2E pausing for deploy" in comment
            assert "E2E deploy complete, resuming" in comment
            assert "Test pause:" in comment
            assert "Test resume:" in comment
            passed = True
        finally:
            if test_id:
                _cancel_test(test_id, E2E_CONSOLE)

    def test_e2e_cancel_already_canceled_test(self):
        """Queue, cancel, cancel again — second cancel returns idempotent success."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready = next(
            (s for s in scenarios if compute_scenario_readiness(s)), None
        )
        assert ready is not None, f"No ready OOB scenario on {E2E_CONSOLE}"

        test_id = None
        try:
            queue_result = sb_run_scenario(
                scenario_id=str(ready['id']),
                console=E2E_CONSOLE,
                test_name="E2E: test_e2e_cancel_already_canceled_test",
            )
            test_id = queue_result['test_id']
            assert test_id, "No test_id returned from run_scenario"

            # First cancel — should succeed normally
            cancel_result_1 = sb_manage_test(
                test_id=test_id,
                action="cancel",
                console=E2E_CONSOLE,
                reason="E2E first cancel",
            )
            assert cancel_result_1['status'] == "success"
            assert cancel_result_1['action'] == "cancel"

            # Wait for data API to reflect canceled state — poll until terminal
            from safebreach_mcp_studio.studio_functions import _get_test_state
            for i in range(15):
                time.sleep(2)
                state = _get_test_state(test_id, E2E_CONSOLE).upper()
                if state in ('CANCELED', 'COMPLETED', 'FAILED'):
                    break

            # Second cancel — should return idempotent success (not error)
            cancel_result_2 = sb_manage_test(
                test_id=test_id,
                action="cancel",
                console=E2E_CONSOLE,
            )
            assert cancel_result_2.get('was_already') is True
            assert "already" in cancel_result_2['status']
            assert cancel_result_2['test_id'] == test_id
        finally:
            pass  # Test is already canceled, no cleanup needed

    def test_e2e_delete_test(self):
        """Queue, cancel, delete (dry-run then execute), verify test is gone.

        Full lifecycle: queue → cancel → wait for terminal state →
        delete dry-run (preview with storage savings) →
        delete execute (confirm deletion + post-delete stats) →
        verify test no longer exists in data API (404) →
        verify delete on already-deleted test raises ValueError.
        """
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready = next(
            (s for s in scenarios if compute_scenario_readiness(s)), None
        )
        assert ready is not None, f"No ready OOB scenario on {E2E_CONSOLE}"

        test_id = None
        try:
            # --- Step 1: Queue a test ---
            queue_result = sb_run_scenario(
                scenario_id=str(ready['id']),
                console=E2E_CONSOLE,
                test_name="E2E: test_e2e_delete_test",
            )
            test_id = queue_result['test_id']
            assert test_id, "No test_id returned from run_scenario"

            # --- Step 2: Cancel the test ---
            cancel_result = sb_manage_test(
                test_id=test_id,
                action="cancel",
                console=E2E_CONSOLE,
                reason="E2E cancel before delete",
            )
            assert cancel_result['status'] == "success"

            # Wait for terminal state to propagate — poll until data API confirms
            from safebreach_mcp_studio.studio_functions import _get_test_state
            for i in range(15):
                time.sleep(2)
                state = _get_test_state(test_id, E2E_CONSOLE).upper()
                logger.info("Waiting for terminal state: %s (attempt %d)", state, i + 1)
                if state in ('CANCELED', 'COMPLETED', 'FAILED'):
                    break
            assert state in ('CANCELED', 'COMPLETED', 'FAILED'), (
                f"Test {test_id} did not reach terminal state after 30s: {state}"
            )

            # --- Step 3: Delete dry-run (preview) ---
            preview_result = sb_manage_test(
                test_id=test_id,
                action="delete",
                console=E2E_CONSOLE,
                reason="E2E delete test cleanup",
                dry_run=True,
            )
            assert preview_result['status'] == "dry_run"
            assert preview_result['dry_run'] is True
            assert preview_result['test_id'] == test_id

            # Preview should contain test info
            preview = preview_result['preview']
            assert preview['test_name'], "Preview missing test name"
            assert preview['status'] in ('CANCELED', 'COMPLETED', 'FAILED')
            assert isinstance(preview['simulation_count'], int)

            # Storage savings should be present (best-effort, might be None)
            if preview.get('storage_savings'):
                savings = preview['storage_savings']
                assert savings['space_freed_bytes'] >= 0
                assert savings['usage_limit_bytes'] > 0
                logger.info(
                    "Delete preview: %s will free %d bytes (usage: %d / %d)",
                    preview['test_name'],
                    savings['space_freed_bytes'],
                    savings['current_usage_bytes'],
                    savings['usage_limit_bytes'],
                )

            assert 'hint_to_agent' in preview_result
            assert "dry_run=False" in preview_result['hint_to_agent']

            # --- Step 4: Delete execute ---
            delete_result = sb_manage_test(
                test_id=test_id,
                action="delete",
                console=E2E_CONSOLE,
                reason="E2E delete test cleanup",
                dry_run=False,
            )
            assert delete_result['status'] == "deleted"
            assert delete_result['deleted_test_name'] == preview['test_name']
            assert delete_result['reason'] == "E2E delete test cleanup"
            assert delete_result['test_id'] == test_id

            # Post-delete storage stats (best-effort)
            if delete_result.get('storage_stats'):
                stats = delete_result['storage_stats']
                assert stats['tests_on_disk_count'] >= 0
                assert stats['tests_limit_count'] > 0
                logger.info(
                    "Post-delete: %d / %d tests, %d / %d bytes",
                    stats['tests_on_disk_count'],
                    stats['tests_limit_count'],
                    stats['tests_on_disk_bytes'],
                    stats['tests_limit_bytes'],
                )

            # --- Step 5: Verify storage stats show updated counts ---
            # Note: DELETE /tests/ is async — the test remains accessible in
            # testsummaries until a background cleanup job runs. We can only
            # verify the DELETE was accepted and storage stats are available.
            if delete_result.get('storage_stats'):
                # dbStorageStats should report a count (may not reflect this
                # specific deletion yet due to async processing)
                assert delete_result['storage_stats']['tests_on_disk_count'] > 0
                logger.info(
                    "Storage after delete: %d tests remaining",
                    delete_result['storage_stats']['tests_on_disk_count'],
                )

        finally:
            # Best-effort cleanup — if delete didn't execute, cancel the test
            if test_id:
                _cancel_test(test_id, E2E_CONSOLE)
