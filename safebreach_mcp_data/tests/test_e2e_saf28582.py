"""
SAF-28582: E2E tests to reproduce and verify the full simulation logs error.

Bug: When the SafeBreach API returns HTTP 200 with empty dataObj.data for
simulation 3213805 / test 1771853252399.2, the code:
1. Caches the response BEFORE validation (cache-before-validation bug)
2. Raises ValueError in get_full_simulation_logs_mapping() instead of
   handling the empty data gracefully

These tests run against the staging.safebreach.com console to reproduce
the exact conditions described in the ticket.

Prerequisites:
    - SSH tunnel to staging: ssh -fN -L 9443:localhost:443 ubuntu@200.11.126.77 \
        -i $SBKeys/Dev/us-east-1.pem -o ServerAliveInterval=30
    - Environment variable: export staging_apitoken=<staging-api-key>

Run:
    export staging_apitoken=<staging-api-key>
    uv run pytest safebreach_mcp_data/tests/test_e2e_saf28582.py -v -m "e2e" -s
"""

import pytest
import os
import requests
import json
from unittest.mock import patch

from safebreach_mcp_core.environments_metadata import (
    safebreach_envs,
    get_api_account_id,
)
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_data.data_functions import (
    sb_get_full_simulation_logs,
    _get_full_simulation_logs_from_cache_or_api,
    full_simulation_logs_cache,
)
from safebreach_mcp_data.data_types import get_full_simulation_logs_mapping


# --- Constants for the specific bug reproduction ---
STAGING_CONSOLE = "staging"
# SSH tunnel: localhost:9443 → staging:443 (bypasses DNS/SSL issues)
STAGING_TUNNEL_URL = "https://localhost:9443"
STAGING_DIRECT_URL = "staging.safebreach.com"
STAGING_ACCOUNT = "3477291461"
BUG_SIMULATION_ID = "3213805"
BUG_TEST_ID = "1771853252399.2"


def _is_staging_configured() -> bool:
    """Check if staging console credentials are available."""
    return bool(os.environ.get("staging_apitoken"))


def _is_tunnel_up() -> bool:
    """Check if the SSH tunnel to staging is available."""
    try:
        requests.get(STAGING_TUNNEL_URL, timeout=3, verify=False)
        return True
    except Exception:
        return False


skip_if_no_staging = pytest.mark.skipif(
    not _is_staging_configured(),
    reason="staging_apitoken env var not set (required for SAF-28582 E2E tests)",
)


@pytest.fixture(autouse=True, scope="module")
def configure_staging_console():
    """Register the staging console in safebreach_envs for the test module.

    Uses the SSH tunnel URL (localhost:9443) so the data_functions code
    can reach the staging API.
    """
    staging_config = {
        "url": STAGING_DIRECT_URL,
        "account": STAGING_ACCOUNT,
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "staging_apitoken",
        },
    }
    already_existed = STAGING_CONSOLE in safebreach_envs
    safebreach_envs[STAGING_CONSOLE] = staging_config
    yield
    if not already_existed:
        safebreach_envs.pop(STAGING_CONSOLE, None)


def _fetch_raw_response_via_tunnel() -> dict:
    """Fetch the raw API response through the SSH tunnel (verify=False).

    This bypasses the code's normal request path to make a direct call,
    useful for inspecting the raw response independently.
    """
    apitoken = get_secret_for_console(STAGING_CONSOLE)
    account_id = get_api_account_id(STAGING_CONSOLE)
    api_url = (
        f"{STAGING_TUNNEL_URL}/api/data/v1/accounts/{account_id}"
        f"/executionsHistoryResults/{BUG_SIMULATION_ID}"
        f"?runId={BUG_TEST_ID}"
    )
    headers = {
        "Content-Type": "application/json",
        "x-apitoken": apitoken,
    }
    response = requests.get(api_url, headers=headers, timeout=120, verify=False)
    response.raise_for_status()
    return response.json(), response.status_code


class TestSAF28582ReproduceE2E:
    """E2E tests that reproduce the SAF-28582 bug on staging.safebreach.com.

    These tests use an SSH tunnel (localhost:9443 → staging:443) since
    staging.safebreach.com is not directly reachable from dev machines.
    """

    # ------------------------------------------------------------------ #
    # Test 1: Verify the raw API response structure for the buggy simulation
    # ------------------------------------------------------------------ #
    @pytest.mark.e2e
    @skip_if_no_staging
    def test_raw_api_response_has_empty_data(self):
        """Verify that the staging API returns HTTP 200 with empty dataObj.data
        for the specific simulation that triggered the bug.

        This confirms the root cause: the API returns a successful response
        but without actual execution log entries.  The simulation had status
        INTERNAL_FAIL, meaning execution logs were never captured.
        """
        print(f"\n=== SAF-28582: Inspecting raw API response ===")

        if not _is_tunnel_up():
            pytest.skip("SSH tunnel to staging not available (localhost:9443)")

        body, status_code = _fetch_raw_response_via_tunnel()

        # --- Verify HTTP 200 (the API does NOT return an error code) ---
        assert status_code == 200, f"Expected HTTP 200, got {status_code}"
        print(f"  HTTP status: {status_code}")

        # --- Parse and inspect dataObj.data ---
        assert isinstance(body, dict), "Response body should be a JSON object"
        data_obj = body.get("dataObj", {})
        data_array = data_obj.get("data", None)

        print(f"  dataObj keys: {list(data_obj.keys()) if isinstance(data_obj, dict) else type(data_obj)}")
        print(f"  dataObj.data type: {type(data_array).__name__}")
        print(f"  dataObj.data value: {json.dumps(data_array, default=str)[:200]}")

        # --- Confirm the empty-data condition that triggers the bug ---
        # Expected: data_array == [[]] — a list containing one empty list
        assert isinstance(data_array, list), "dataObj.data should be a list"
        assert len(data_array) >= 1, "dataObj.data should have at least one element"
        assert not data_array[0], (
            f"dataObj.data[0] should be empty (falsy), got: "
            f"{json.dumps(data_array[0], default=str)[:200]}"
        )
        print(f"  Confirmed: dataObj.data = [[]] (empty inner array)")

        # --- Verify the simulation status that explains the empty logs ---
        assert body.get("status") == "INTERNAL_FAIL", (
            f"Expected INTERNAL_FAIL status, got: {body.get('status')}"
        )
        print(f"  Simulation status: {body.get('status')} (explains missing logs)")

        # --- Log other useful metadata ---
        print(f"  simulation id: {body.get('id', 'N/A')}")
        print(f"  moveName: {body.get('moveName', 'N/A')}")
        print(f"  planRunId: {body.get('planRunId', 'N/A')}")
        print(f"=== Raw API inspection complete ===\n")

    # ------------------------------------------------------------------ #
    # Test 2: Reproduce the ValueError from get_full_simulation_logs_mapping
    # ------------------------------------------------------------------ #
    @pytest.mark.e2e
    @skip_if_no_staging
    def test_mapping_raises_value_error_on_empty_data(self):
        """Reproduce the exact error: get_full_simulation_logs_mapping()
        raises ValueError('Response missing dataObj.data structure') when
        the API response has empty dataObj.data.
        """
        print(f"\n=== SAF-28582: Reproducing ValueError in mapping ===")

        if not _is_tunnel_up():
            pytest.skip("SSH tunnel to staging not available (localhost:9443)")

        # Fetch the raw API response via tunnel (same data the code would get)
        raw_response, _ = _fetch_raw_response_via_tunnel()
        print(f"  Fetched raw response successfully (HTTP 200)")

        # Attempt transformation — should raise ValueError
        with pytest.raises(ValueError, match="Response missing dataObj.data structure"):
            get_full_simulation_logs_mapping(raw_response)

        print(f"  Confirmed: ValueError raised as expected")
        print(f"=== Mapping ValueError reproduction complete ===\n")

    # ------------------------------------------------------------------ #
    # Test 3: Reproduce the full error path through sb_get_full_simulation_logs
    # ------------------------------------------------------------------ #
    @pytest.mark.e2e
    @skip_if_no_staging
    def test_sb_get_full_simulation_logs_raises_on_empty_data(self):
        """Reproduce the full error path: sb_get_full_simulation_logs()
        propagates the ValueError from the mapping layer when the API
        returns empty dataObj.data.

        Patches _fetch_full_simulation_logs_from_api to return the real
        staging response (fetched via tunnel), then verifies the full
        function chain raises ValueError.
        """
        print(f"\n=== SAF-28582: Reproducing full error path ===")

        if not _is_tunnel_up():
            pytest.skip("SSH tunnel to staging not available (localhost:9443)")

        # Get the real response via tunnel
        real_response, _ = _fetch_raw_response_via_tunnel()

        # Patch the API fetch to return the real staging response
        # (avoids DNS/SSL issues while testing the full code path)
        with patch(
            "safebreach_mcp_data.data_functions._fetch_full_simulation_logs_from_api",
            return_value=real_response,
        ):
            with pytest.raises(
                ValueError, match="Response missing dataObj.data structure"
            ):
                sb_get_full_simulation_logs(
                    simulation_id=BUG_SIMULATION_ID,
                    test_id=BUG_TEST_ID,
                    console=STAGING_CONSOLE,
                )

        print(f"  Confirmed: sb_get_full_simulation_logs raises ValueError")
        print(f"=== Full error path reproduction complete ===\n")

    # ------------------------------------------------------------------ #
    # Test 4: Verify the cache-before-validation bug
    # ------------------------------------------------------------------ #
    @pytest.mark.e2e
    @skip_if_no_staging
    def test_cache_before_validation_bug(self):
        """Verify that when caching is enabled, the invalid response gets
        cached BEFORE validation, causing subsequent calls to also fail
        from the cached bad data (for up to 300 seconds).

        This confirms the 'cache-before-validation' aspect of the bug.
        """
        print(f"\n=== SAF-28582: Verifying cache-before-validation bug ===")

        if not _is_tunnel_up():
            pytest.skip("SSH tunnel to staging not available (localhost:9443)")

        cache_key = (
            f"full_simulation_logs_{STAGING_CONSOLE}_{BUG_SIMULATION_ID}_{BUG_TEST_ID}"
        )

        # Get the real response via tunnel
        real_response, _ = _fetch_raw_response_via_tunnel()

        # Clear any existing cache entry
        full_simulation_logs_cache.clear()
        assert full_simulation_logs_cache.get(cache_key) is None, (
            "Cache should be empty before test"
        )
        print(f"  Cache cleared, key '{cache_key}' is empty")

        # Enable caching temporarily for this test
        from safebreach_mcp_core.cache_config import _per_server_cache

        with patch.dict(os.environ, {"SB_MCP_CACHE_DATA": "true"}):
            # Force re-evaluation of the caching flag
            _per_server_cache.pop("data", None)

            # Patch the API fetch to return the real staging response
            with patch(
                "safebreach_mcp_data.data_functions._fetch_full_simulation_logs_from_api",
                return_value=real_response,
            ):
                # Call the cache-or-API function (this caches the raw response)
                _get_full_simulation_logs_from_cache_or_api(
                    BUG_SIMULATION_ID, BUG_TEST_ID, STAGING_CONSOLE
                )
                print(f"  Fetched from API and cached raw response")

            # Verify the bad response is now in cache
            cached = full_simulation_logs_cache.get(cache_key)
            assert cached is not None, (
                "BUG: Invalid response was NOT cached — "
                "this would mean the cache-before-validation bug is fixed"
            )
            print(f"  BUG CONFIRMED: Invalid response is in cache")

            # Verify the cached data has the empty dataObj.data structure
            assert isinstance(cached, dict), "Cached value should be a dict"
            cached_data_obj = cached.get("dataObj", {})
            cached_data_array = cached_data_obj.get("data", [[]])
            assert not cached_data_array[0], (
                "Cached response should have empty dataObj.data[0]"
            )
            print(f"  Cached response has empty dataObj.data (will fail for 300s)")

            # Verify that the cached bad data causes the same error on subsequent calls
            # (no API call needed — served from cache)
            with pytest.raises(
                ValueError, match="Response missing dataObj.data structure"
            ):
                sb_get_full_simulation_logs(
                    simulation_id=BUG_SIMULATION_ID,
                    test_id=BUG_TEST_ID,
                    console=STAGING_CONSOLE,
                )
            print(f"  Subsequent call from cache also raises ValueError")

        # Clean up: clear cache and restore caching flag
        full_simulation_logs_cache.clear()
        _per_server_cache.pop("data", None)

        print(f"=== Cache-before-validation bug confirmed ===\n")
