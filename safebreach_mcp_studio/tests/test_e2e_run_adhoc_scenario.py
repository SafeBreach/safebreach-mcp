"""
End-to-End Tests for run_adhoc_scenario (SAF-31295)

Tests the ad-hoc scenario execution pipeline using real API calls.
Pattern: dry_run → verify predictions → queue → cancel.

ZERO MOCKS — all calls hit real SafeBreach APIs.

Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v
"""

import json
import logging
import pytest
import os
import requests

from safebreach_mcp_studio.studio_functions import sb_run_adhoc_scenario
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)

E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

# Verified attacks on pentest01 with applicable simulators
E2E_ATTACK_IDS = [11653, 11662, 7207, 11663, 11622]

# Minimal simulator overrides — verified to produce non-zero, low simulation counts.
# Discovered by probing the statistics API with single-simulator pairs per attack.
# Total: ~101 sims (vs ~5,750 with all_connected = 57x reduction).
#
# 11653: host LINUX attack → rc-centos9 (attacker=target, 1 sim)
# 11662: network HTTP transfer → rc-centos9 target + external attacker infil (54 sims)
# 7207:  network Azure PS script → pz-crowdstrike target + external attacker (36 sims)
# 11663: email attack → GMX target + passmgmt attacker (4 sims)
# 11622: network HTTP transfer → pz-crowdstrike target + RC-V-W11-NEDR01 attacker (6 sims)
E2E_SIMULATOR_OVERRIDES = {
    "11653": {
        "target": ["38c27ff5-49bc-40aa-bf1e-8aac25d16154"],       # rc-centos9
    },
    "11662": {
        "target": ["38c27ff5-49bc-40aa-bf1e-8aac25d16154"],       # rc-centos9
        "attacker": ["a3d8ea5a-3077-4607-9952-4e44a702d1fe"],     # external attacker (infil+exfil)
    },
    "7207": {
        "target": ["6a3d5b57-4752-408c-9b29-1fb0233e49c0"],       # pz-crowdstrike
        "attacker": ["a3d8ea5a-3077-4607-9952-4e44a702d1fe"],     # external attacker
    },
    "11663": {
        "target": ["dfb37a8f-b726-4d41-aa59-3b92c52fcb3c"],       # GMX
        "attacker": ["52a6edc4-8b35-4bfb-8a0d-4538a0188354"],     # passmgmt
    },
    "11622": {
        "target": ["6a3d5b57-4752-408c-9b29-1fb0233e49c0"],       # pz-crowdstrike
        "attacker": ["8be96f8c-601d-49c8-81c1-509e8b87a529"],     # RC-V-W11-NEDR01
    },
}

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


def _comment_test(test_id, console, comment):
    """Leave a comment on a test run explaining what happened."""
    try:
        apitoken, _, base_url_data, account_id = _get_auth(console)
        url = f"{base_url_data}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"
        headers = {"x-apitoken": apitoken, "Content-Type": "application/json"}
        resp = requests.put(url, headers=headers, json={"comment": comment}, timeout=30)
        logger.info(f"Comment {test_id}: HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"Comment {test_id} failed: {e}")


def _cleanup_test(test_id, console, test_name, passed, detail=""):
    """Cancel and comment a test. Called in finally blocks."""
    if not test_id:
        return
    _cancel_test(test_id, console)
    status = "PASSED" if passed else "FAILED"
    comment = f"[MCP E2E] {test_name}: {status}. {detail}".strip()
    _comment_test(test_id, console, comment)


# ---------------------------------------------------------------------------
# E2E Tests — run_adhoc_scenario
# ---------------------------------------------------------------------------


@skip_e2e
@pytest.mark.e2e
class TestRunAdhocScenarioE2E:
    """E2E tests for sb_run_adhoc_scenario against a real console."""

    def test_dry_run_all_five_attacks(self):
        """Dry-run with all 5 verified attacks produces predicted_simulations > 0."""
        attack_ids_str = ",".join(str(a) for a in E2E_ATTACK_IDS)

        result = sb_run_adhoc_scenario(
            attack_ids=attack_ids_str,
            console=E2E_CONSOLE,
            dry_run=True,
        )

        assert result["status"] == "dry_run"
        assert result["predicted_simulations"] > 0
        assert len(result["steps"]) == 5
        assert len(result["predicted_per_step"]) == 5
        logger.info(
            f"Dry-run 5 attacks: {result['predicted_simulations']} predicted sims, "
            f"per-step: {result['predicted_per_step']}"
        )

    def test_dry_run_subset_two_attacks(self):
        """Dry-run with 2 attacks returns correct step count and per-step counts."""
        subset = E2E_ATTACK_IDS[:2]
        attack_ids_str = ",".join(str(a) for a in subset)

        result = sb_run_adhoc_scenario(
            attack_ids=attack_ids_str,
            console=E2E_CONSOLE,
            dry_run=True,
        )

        assert result["status"] == "dry_run"
        assert len(result["steps"]) == 2
        assert len(result["predicted_per_step"]) == 2
        # Each step should have a non-negative count
        for count in result["predicted_per_step"]:
            assert isinstance(count, int)
            assert count >= 0
        logger.info(
            f"Dry-run 2 attacks: {result['predicted_simulations']} predicted sims, "
            f"per-step: {result['predicted_per_step']}"
        )

    def test_queue_and_cancel(self):
        """Queue 2 attacks then cancel. Verifies test_id is returned."""
        subset = E2E_ATTACK_IDS[:2]
        attack_ids_str = ",".join(str(a) for a in subset)
        test_id = None
        passed = False

        try:
            result = sb_run_adhoc_scenario(
                attack_ids=attack_ids_str,
                console=E2E_CONSOLE,
                dry_run=False,
            )

            assert result["status"] == "queued"
            assert result["test_id"]
            assert len(result["step_run_ids"]) > 0
            test_id = result["test_id"]
            passed = True
            logger.info(
                f"Queued ad-hoc scenario: test_id={test_id}, "
                f"steps={result['step_count']}, "
                f"predicted={result['predicted_simulations']}"
            )
        finally:
            _cleanup_test(
                test_id, E2E_CONSOLE,
                "test_queue_and_cancel", passed,
                f"attack_ids={subset}",
            )

    def test_invalid_attack_id_raises(self):
        """Invalid attack ID mixed with valid raises ValueError."""
        # 99999999 should not exist in the playbook
        attack_ids_str = f"{E2E_ATTACK_IDS[0]},99999999"

        with pytest.raises(ValueError, match="not found"):
            sb_run_adhoc_scenario(
                attack_ids=attack_ids_str,
                console=E2E_CONSOLE,
            )

    def test_dry_run_with_simulator_overrides(self):
        """Dry-run with pre-verified simulator overrides produces minimal sims."""
        attack_ids_str = ",".join(str(a) for a in E2E_ATTACK_IDS)

        result = sb_run_adhoc_scenario(
            attack_ids=attack_ids_str,
            console=E2E_CONSOLE,
            simulator_overrides=json.dumps(E2E_SIMULATOR_OVERRIDES),
            dry_run=True,
        )

        assert result["status"] == "dry_run"
        assert result["predicted_simulations"] > 0
        # Every attack should produce at least 1 simulation
        for i, count in enumerate(result["predicted_per_step"]):
            assert count > 0, (
                f"Attack {E2E_ATTACK_IDS[i]} produced 0 sims with override"
            )
        # Targeted overrides should produce far fewer sims than all_connected
        assert result["predicted_simulations"] < 500, (
            f"Expected < 500 sims with targeted overrides, "
            f"got {result['predicted_simulations']}"
        )
        logger.info(
            f"Overrides dry-run: {result['predicted_simulations']} sims, "
            f"per-step: {result['predicted_per_step']}"
        )

    def test_queue_with_simulator_overrides_and_cancel(self):
        """Queue with simulator overrides, verify test_id, then cancel."""
        attack_ids_str = ",".join(str(a) for a in E2E_ATTACK_IDS)
        test_id = None
        passed = False

        try:
            result = sb_run_adhoc_scenario(
                attack_ids=attack_ids_str,
                console=E2E_CONSOLE,
                simulator_overrides=json.dumps(E2E_SIMULATOR_OVERRIDES),
                dry_run=False,
            )

            assert result["status"] == "queued"
            assert result["test_id"]
            assert len(result["step_run_ids"]) == 5
            assert result["predicted_simulations"] < 500
            test_id = result["test_id"]
            passed = True
            logger.info(
                f"Queued with overrides: test_id={test_id}, "
                f"sims={result['predicted_simulations']}, "
                f"per-step={result['predicted_per_step']}"
            )
        finally:
            _cleanup_test(
                test_id, E2E_CONSOLE,
                "test_queue_with_simulator_overrides", passed,
                f"attacks={E2E_ATTACK_IDS}",
            )
