"""
Orchestrator queue state lookup.

Provides real-time test state from the orchestrator ``GET /queue`` endpoint.
The data API (``testsummaries``) has 10-15 seconds of eventual consistency lag
after lifecycle changes; the orchestrator queue reflects state immediately.

Usage::

    from safebreach_mcp_core.queue_state import get_orchestrator_test_state

    state = get_orchestrator_test_state("1778787545455.150", "pentest01")
    # Returns "RUNNING", "PAUSED", or None (test not in queue)
"""

import logging

import requests
from safebreach_mcp_core.secret_utils import get_auth_headers_for_console, check_rbac_response
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)


def get_orchestrator_test_state(test_id: str, console: str) -> str | None:
    """
    Check the orchestrator queue for a test's real-time state.

    Calls ``GET /api/orch/v4/accounts/{account_id}/queue`` and searches
    ``slotState`` for the given ``planRunId``.

    Args:
        test_id: Test execution ID (planRunId)
        console: SafeBreach console identifier

    Returns:
        ``"RUNNING"`` or ``"PAUSED"`` if the test is in an active slot,
        ``None`` if the test is not in the queue (terminal or unknown).
        On API error, returns ``None`` (caller should fall back to data API).
    """
    try:
        orch_base = get_api_base_url(console, 'orchestrator')
        account_id = get_api_account_id(console)
        queue_url = f"{orch_base}/api/orch/v4/accounts/{account_id}/queue"
        headers = {"accept": "application/json", **get_auth_headers_for_console(console)}

        response = requests.get(queue_url, headers=headers, timeout=30)
        check_rbac_response(response)
        queue_data = response.json().get('data', {})

        for slot in queue_data.get('slotState', []):
            if slot.get('planRunId') == test_id:
                if slot.get('isPaused'):
                    return "PAUSED"
                return "RUNNING"

        return None  # Test not in any slot

    except Exception as e:
        logger.warning(
            "Orchestrator queue check failed for '%s': %s", test_id, e
        )
        return None
