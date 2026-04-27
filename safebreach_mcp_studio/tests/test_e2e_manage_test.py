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
