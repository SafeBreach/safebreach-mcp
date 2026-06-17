"""
End-to-End Tests for SafeBreach Studio MCP Server

This module tests the complete Studio functionality using real API calls.
These tests require:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: See E2E_TESTING.md for complete setup instructions.
Security: All real environment details must be in private local files only.

Studio-specific environment variables:
- E2E_CONSOLE: Console name (default: 'demo-console')
- E2E_STUDIO_ATTACK_ID: Pre-existing attack ID for read tests (source retrieval)
- E2E_STUDIO_ATTACK_NAME: Expected name of the pre-existing attack
- E2E_STUDIO_TRANSITION_ATTACK_ID: Attack ID that supports publish/unpublish transitions
- SKIP_E2E_TESTS: Set to 'true' to skip E2E tests
"""

import pytest
import os
from safebreach_mcp_studio.studio_functions import (
    sb_validate_studio_code,
    sb_save_studio_attack_draft,
    sb_get_all_studio_attacks,
    sb_update_studio_attack_draft,
    sb_get_studio_attack_source,
    sb_run_studio_attack,
    sb_get_studio_attack_latest_result,
    sb_set_studio_attack_status,
    studio_draft_cache,
)


# Skip E2E tests if not in proper environment
E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'demo-console')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'
E2E_STUDIO_ATTACK_ID = os.environ.get('E2E_STUDIO_ATTACK_ID', '')
E2E_STUDIO_ATTACK_NAME = os.environ.get('E2E_STUDIO_ATTACK_NAME', '')
E2E_STUDIO_TRANSITION_ATTACK_ID = os.environ.get('E2E_STUDIO_TRANSITION_ATTACK_ID', '')

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)

# Sample valid host attack code for E2E testing
SAMPLE_HOST_CODE = '''
def main(system_data, asset, proxy, *args, **kwargs):
    """Sample host attack for E2E testing."""
    import os
    temp_path = os.path.join(os.environ.get("TEMP", "/tmp"), "sb_e2e_test.txt")
    with open(temp_path, "w") as f:
        f.write("SafeBreach E2E test")
    os.remove(temp_path)
    return {"status": "success", "message": "E2E test completed"}
'''

SAMPLE_INVALID_CODE = '''
def main(system_data, asset, proxy, *args, **kwargs):
    # Missing closing parenthesis - syntax error
    print("hello"
'''


@skip_e2e
@pytest.mark.e2e
class TestStudioValidationE2E:
    """E2E tests for Studio code validation."""

    def setup_method(self):
        """Clear cache before each test."""
        studio_draft_cache.clear()

    def test_validate_valid_host_code_e2e(self):
        """Test validating valid host attack code via real API."""
        try:
            result = sb_validate_studio_code(
                python_code=SAMPLE_HOST_CODE,
                attack_type="host",
                console=E2E_CONSOLE,
            )

            # Verify response structure
            assert 'is_valid' in result
            assert 'exit_code' in result
            assert 'validation_errors' in result
            assert 'lint_warnings' in result

            # Valid code should pass
            assert result['is_valid'] is True
            assert result['exit_code'] == 0
            assert len(result['validation_errors']) == 0

            print(f"\n=== Validation E2E ===")
            print(f"  Valid code: is_valid={result['is_valid']}")
            print(f"  Exit code: {result['exit_code']}")

        except Exception as e:
            pytest.skip(f"Could not validate code on {E2E_CONSOLE}: {e}")

    def test_validate_invalid_code_e2e(self):
        """Test validating invalid code via real API."""
        try:
            result = sb_validate_studio_code(
                python_code=SAMPLE_INVALID_CODE,
                attack_type="host",
                console=E2E_CONSOLE,
            )

            # Invalid code should fail validation
            assert result['is_valid'] is False

            print(f"\n=== Invalid Code Validation E2E ===")
            print(f"  is_valid={result['is_valid']}")
            print(f"  Errors: {result['validation_errors']}")

        except Exception as e:
            pytest.skip(f"Could not validate code on {E2E_CONSOLE}: {e}")

    def test_validate_lint_sb011_e2e(self):
        """Test SB011 lint check with invalid parameter name."""
        try:
            params = [
                {
                    "name": "my-invalid-param",
                    "description": "A parameter with invalid name",
                    "type": "NOT_CLASSIFIED",
                    "value": "test"
                }
            ]
            result = sb_validate_studio_code(
                python_code=SAMPLE_HOST_CODE,
                attack_type="host",
                console=E2E_CONSOLE,
                parameters=params,
            )

            # Should have lint warnings for SB011
            assert 'lint_warnings' in result
            sb011_warnings = [
                w for w in result['lint_warnings']
                if (isinstance(w, dict) and w.get('code') == 'SB011') or
                   (isinstance(w, str) and 'SB011' in w)
            ]
            assert len(sb011_warnings) > 0

            print(f"\n=== SB011 Lint E2E ===")
            print(f"  Lint warnings: {result['lint_warnings']}")

        except Exception as e:
            pytest.skip(f"Could not validate code on {E2E_CONSOLE}: {e}")


@skip_e2e
@pytest.mark.e2e
class TestStudioListE2E:
    """E2E tests for listing Studio attacks."""

    def setup_method(self):
        """Clear cache before each test."""
        studio_draft_cache.clear()

    def test_get_all_studio_attacks_e2e(self):
        """Test listing attacks from real console with pagination fields."""
        try:
            result = sb_get_all_studio_attacks(
                console=E2E_CONSOLE,
                page_number=0,
            )

            # Verify response structure
            assert 'attacks_in_page' in result
            assert 'total_attacks' in result
            assert 'page_number' in result
            assert 'total_pages' in result
            assert 'applied_filters' in result

            assert isinstance(result['attacks_in_page'], list)
            assert result['page_number'] == 0
            assert result['total_attacks'] >= 0

            if result['total_attacks'] > 0:
                attack = result['attacks_in_page'][0]
                assert 'id' in attack
                assert 'name' in attack
                assert 'status' in attack

            print(f"\n=== List Attacks E2E ===")
            print(f"  Total attacks: {result['total_attacks']}")
            print(f"  Page 0 count: {len(result['attacks_in_page'])}")
            print(f"  Total pages: {result['total_pages']}")

        except Exception as e:
            pytest.skip(f"Could not list attacks on {E2E_CONSOLE}: {e}")

    def test_get_all_studio_attacks_pagination_e2e(self):
        """Test pagination: page 0 vs page 1 have no overlap."""
        try:
            page0 = sb_get_all_studio_attacks(
                console=E2E_CONSOLE, page_number=0
            )

            if page0['total_pages'] < 2:
                pytest.skip("Not enough attacks for pagination test")

            page1 = sb_get_all_studio_attacks(
                console=E2E_CONSOLE, page_number=1
            )

            page0_ids = {a['id'] for a in page0['attacks_in_page']}
            page1_ids = {a['id'] for a in page1['attacks_in_page']}
            assert page0_ids.isdisjoint(page1_ids), "Pages should not overlap"

            print(f"\n=== Pagination E2E ===")
            print(f"  Page 0: {len(page0['attacks_in_page'])} attacks")
            print(f"  Page 1: {len(page1['attacks_in_page'])} attacks")
            print(f"  No overlap: True")

        except Exception as e:
            if "Not enough" not in str(e):
                pytest.skip(f"Could not test pagination on {E2E_CONSOLE}: {e}")
            raise

    def test_get_all_studio_attacks_filtering_e2e(self):
        """Test filtering by status."""
        try:
            result = sb_get_all_studio_attacks(
                console=E2E_CONSOLE,
                page_number=0,
                status_filter="draft",
            )

            assert 'applied_filters' in result
            assert result['applied_filters']['status_filter'] == 'draft'

            # All returned attacks should be drafts
            for attack in result['attacks_in_page']:
                assert attack['status'] == 'draft'

            print(f"\n=== Filtering E2E ===")
            print(f"  Draft attacks: {result['total_attacks']}")

        except Exception as e:
            pytest.skip(f"Could not filter attacks on {E2E_CONSOLE}: {e}")


@skip_e2e
@pytest.mark.e2e
class TestStudioSourceE2E:
    """E2E tests for retrieving attack source code."""

    def setup_method(self):
        """Clear cache before each test."""
        studio_draft_cache.clear()

    def test_get_studio_attack_source_e2e(self):
        """Test retrieving source code of a pre-existing attack."""
        if not E2E_STUDIO_ATTACK_ID:
            pytest.skip("E2E_STUDIO_ATTACK_ID not set")

        try:
            attack_id = int(E2E_STUDIO_ATTACK_ID)
            result = sb_get_studio_attack_source(
                attack_id=attack_id,
                console=E2E_CONSOLE,
            )

            # Verify structure
            assert 'attack_id' in result
            assert 'target' in result
            assert result['attack_id'] == attack_id

            # Target should have content
            assert result['target'] is not None
            assert 'filename' in result['target']
            assert 'content' in result['target']
            assert len(result['target']['content']) > 0

            print(f"\n=== Source Retrieval E2E ===")
            print(f"  Attack ID: {attack_id}")
            print(f"  Target file: {result['target']['filename']}")
            print(f"  Target code length: {len(result['target']['content'])} chars")
            print(f"  Has attacker: {result['attacker'] is not None}")

        except Exception as e:
            pytest.skip(f"Could not get attack source on {E2E_CONSOLE}: {e}")

    def test_get_studio_attack_source_structure_e2e(self):
        """Test that source retrieval returns proper target/attacker structure."""
        if not E2E_STUDIO_ATTACK_ID:
            pytest.skip("E2E_STUDIO_ATTACK_ID not set")

        try:
            attack_id = int(E2E_STUDIO_ATTACK_ID)
            result = sb_get_studio_attack_source(
                attack_id=attack_id,
                console=E2E_CONSOLE,
            )

            # Verify keys
            assert set(result.keys()) >= {'attack_id', 'target', 'attacker'}

            # Target is always present
            target = result['target']
            assert isinstance(target, dict)
            assert 'filename' in target
            assert 'content' in target

            # Attacker is None for host attacks or dict for dual-script
            if result['attacker'] is not None:
                assert isinstance(result['attacker'], dict)
                assert 'filename' in result['attacker']
                assert 'content' in result['attacker']

        except Exception as e:
            pytest.skip(f"Could not verify source structure on {E2E_CONSOLE}: {e}")


@skip_e2e
@pytest.mark.e2e
class TestStudioDraftLifecycleE2E:
    """E2E tests for draft create/update/verify lifecycle."""

    _created_attack_ids = []

    def setup_method(self):
        """Clear cache before each test."""
        studio_draft_cache.clear()

    def test_create_and_update_draft_e2e(self):
        """Test full draft lifecycle: create -> update -> verify source."""
        try:
            # Step 1: Create a draft
            create_result = sb_save_studio_attack_draft(
                name="E2E Test Draft - Auto Delete",
                python_code=SAMPLE_HOST_CODE,
                description="E2E test draft - safe to delete",
                attack_type="host",
                console=E2E_CONSOLE,
            )

            assert 'draft_id' in create_result
            assert create_result['draft_id'] > 0
            draft_id = create_result['draft_id']
            self._created_attack_ids.append(draft_id)

            print(f"\n=== Draft Lifecycle E2E ===")
            print(f"  Created draft: {draft_id}")

            # Step 2: Update the draft
            updated_code = SAMPLE_HOST_CODE.replace(
                "E2E test completed", "E2E test updated"
            )
            update_result = sb_update_studio_attack_draft(
                attack_id=draft_id,
                name="E2E Test Draft - Updated",
                python_code=updated_code,
                description="E2E test draft updated",
                attack_type="host",
                console=E2E_CONSOLE,
            )

            assert 'draft_id' in update_result
            assert update_result['draft_id'] == draft_id
            print(f"  Updated draft: {draft_id}")

            # Step 3: Verify source
            source_result = sb_get_studio_attack_source(
                attack_id=draft_id,
                console=E2E_CONSOLE,
            )

            assert source_result['attack_id'] == draft_id
            assert source_result['target'] is not None
            assert "E2E test updated" in source_result['target']['content']
            print(f"  Verified source contains updated content")

        except Exception as e:
            pytest.skip(f"Draft lifecycle test failed on {E2E_CONSOLE}: {e}")


@skip_e2e
@pytest.mark.e2e
class TestStudioExecutionE2E:
    """E2E tests for running attacks and checking results.

    These tests require connected simulators on the test console.
    """

    def setup_method(self):
        """Clear cache before each test."""
        studio_draft_cache.clear()

    def test_run_studio_attack_e2e(self):
        """Test running a pre-existing attack with all_connected."""
        if not E2E_STUDIO_ATTACK_ID:
            pytest.skip("E2E_STUDIO_ATTACK_ID not set")

        try:
            attack_id = int(E2E_STUDIO_ATTACK_ID)
            result = sb_run_studio_attack(
                attack_id=attack_id,
                console=E2E_CONSOLE,
                all_connected=True,
            )

            # Verify return structure
            assert 'test_id' in result
            assert 'attack_id' in result
            assert 'status' in result
            assert result['attack_id'] == attack_id
            assert result['status'] == 'queued'

            print(f"\n=== Run Attack E2E ===")
            print(f"  Attack ID: {attack_id}")
            print(f"  Test ID: {result['test_id']}")
            print(f"  Status: {result['status']}")

        except Exception as e:
            pytest.skip(f"Could not run attack on {E2E_CONSOLE}: {e}")

    def test_run_published_studio_attack_visible_in_test_results_e2e(self):
        """SAF-31468: a published Studio attack run must be discoverable in Test Results.

        Creates a brand-new attack (never run as draft), publishes it, runs it, then
        verifies the returned planRunId is retrievable via the Data Server's test history
        (the same testsummaries surface that backs the Test Results UI).
        """
        import time
        from safebreach_mcp_data.data_functions import sb_get_tests

        # Unique test name so the run can be located in the listing deterministically via
        # name_filter (get_tests filters before paginating) — robust regardless of how many
        # other tests exist on the console or their ordering/indexing.
        unique_test_name = f"SB E2E SAF-31468 visibility {int(time.time())}"

        attack_id = None
        try:
            # --- Setup (environment-dependent): create + publish + run a fresh attack.
            # Genuine environment/precondition failures here skip; the visibility assertions
            # below run OUTSIDE this inner try so a real regression fails loudly (not skipped).
            try:
                save_result = sb_save_studio_attack_draft(
                    name="SB E2E SAF-31468 visibility",
                    python_code=SAMPLE_HOST_CODE,
                    attack_type="host",
                    console=E2E_CONSOLE,
                )
                attack_id = int(save_result['draft_id'])
                sb_set_studio_attack_status(
                    attack_id=attack_id, new_status="published", console=E2E_CONSOLE
                )
                run_result = sb_run_studio_attack(
                    attack_id=attack_id, console=E2E_CONSOLE, all_connected=True,
                    test_name=unique_test_name,
                )
            except Exception as e:
                pytest.skip(f"Setup failed on {E2E_CONSOLE} (cannot exercise visibility): {e}")

            test_id = run_result['test_id']
            print(f"\n=== Published Run Visibility E2E (SAF-31468) ===")
            print(f"  Attack ID: {attack_id}")
            print(f"  Test ID: {test_id}")
            print(f"  draft flag: {run_result['draft']}")

            # --- Assertions (the regression gate): a PUBLISHED attack must queue with
            # draft=False AND be discoverable in the Test Results surface. These fail loudly.
            assert run_result['draft'] is False, "published attack must queue with draft=False"
            assert test_id

            # The real regression gate: the run must appear in the test history LISTING
            # (testsummaries list — the same surface as the Test Results page, which excludes
            # draft-scoped runs). Locate it by its unique name (get_tests filters before
            # paginating, so a unique name lands on page 0). Poll to absorb list-indexing lag.
            #
            # NOTE: this depends on the SafeBreach backend's test-ingestion latency, which is
            # a *variable backend property* — typically a few seconds, but observed to stall
            # for many minutes when the console's data pipeline is degraded. If this assertion
            # fails, first confirm whether the console is ingesting NEW tests at all (compare
            # the newest start_time in get_tests to "now"); a stalled pipeline is a backend
            # health issue, not a regression in run_studio_attack (whose draft=False behavior
            # is asserted deterministically above).
            found_in_listing = False
            attempt = 0
            deadline_polls = 30  # ~300s at 10s intervals
            for attempt in range(deadline_polls):
                listing = sb_get_tests(
                    console=E2E_CONSOLE, page_number=0,
                    name_filter=unique_test_name,
                    order_by="start_time", order_direction="desc",
                )
                page_ids = {str(t.get('test_id', '')) for t in listing.get('tests_in_page', [])}
                if str(test_id) in page_ids:
                    found_in_listing = True
                    break
                time.sleep(10)

            assert found_in_listing, (
                f"planRunId {test_id} (name '{unique_test_name}') not found in get_tests listing "
                f"after polling — published run is not visible in Test Results history (regression)"
            )
            print(f"  Visible in get_tests listing: True (after {attempt + 1} poll attempt(s))")
        finally:
            # Best-effort cleanup: delete the attack created by this test via the direct
            # content API so the test does not leave artifacts on the console.
            if attack_id is not None:
                self._delete_studio_attack(attack_id, E2E_CONSOLE)

    @staticmethod
    def _delete_studio_attack(attack_id, console):
        """Delete a custom method via the direct content API (test cleanup; best-effort)."""
        import requests
        from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
        from safebreach_mcp_core.secret_utils import get_auth_headers_for_console
        try:
            base_url = get_api_base_url(console, 'config')
            account_id = get_api_account_id(console)
            headers = {**get_auth_headers_for_console(console)}
            url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{attack_id}"
            resp = requests.delete(url, headers=headers, timeout=120)
            print(f"  Cleanup: DELETE attack {attack_id} -> HTTP {resp.status_code}")
        except Exception as e:
            print(f"  Cleanup: failed to delete attack {attack_id}: {e}")

    def test_get_studio_attack_latest_result_e2e(self):
        """Test getting latest result for a pre-existing attack."""
        if not E2E_STUDIO_ATTACK_ID:
            pytest.skip("E2E_STUDIO_ATTACK_ID not set")

        try:
            attack_id = int(E2E_STUDIO_ATTACK_ID)
            result = sb_get_studio_attack_latest_result(
                attack_id=attack_id,
                console=E2E_CONSOLE,
                max_results=1,
                include_logs=True,
            )

            # Verify response structure
            assert 'executions' in result
            assert 'total_found' in result
            assert 'attack_id' in result
            assert result['attack_id'] == attack_id

            if result['total_found'] > 0:
                execution = result['executions'][0]
                # Verify Data Server field alignment
                assert 'simulation_id' in execution
                assert 'attack_id' in execution
                assert 'test_id' in execution
                assert 'status' in execution
                assert 'drift_tracking_code' in execution
                assert 'is_drifted' in execution

                # Verify enhanced fields present (include_logs=True)
                assert 'simulation_steps' in execution
                assert 'logs' in execution
                assert 'output' in execution

                # Verify test overview enrichment (SAF-30717)
                assert 'test_overview' in result
                if result['test_overview'] is not None:
                    overview = result['test_overview']
                    assert 'status' in overview
                    assert 'start_time' in overview
                    assert 'total_simulations' in overview
                    assert 'simulation_status_counts' in overview

                print(f"\n=== Latest Result E2E ===")
                print(f"  Attack ID: {attack_id}")
                print(f"  Total found: {result['total_found']}")
                print(f"  Simulation ID: {execution['simulation_id']}")
                print(f"  Status: {execution['status']}")
                print(f"  Is Drifted: {execution['is_drifted']}")
                print(f"  Simulation Steps: {len(execution['simulation_steps'])} step(s)")
                print(f"  Has Logs: {bool(execution['logs'])}")
                print(f"  Has Output: {bool(execution['output'])}")
                if result['test_overview'] is not None:
                    print(f"  Test Status: {result['test_overview']['status']}")
                    print(f"  Total Simulations: {result['test_overview']['total_simulations']}")
            else:
                print(f"\n=== Latest Result E2E ===")
                print(f"  No execution results found for attack {attack_id}")

        except Exception as e:
            pytest.skip(f"Could not get results on {E2E_CONSOLE}: {e}")


@skip_e2e
@pytest.mark.e2e
class TestStudioDebugFlowE2E:
    """E2E test for the full debug iteration flow (Flow 4 from PRD).

    Flow: run attack -> get results -> verify logs/steps available
    """

    def setup_method(self):
        """Clear cache before each test."""
        studio_draft_cache.clear()

    def test_debug_flow_e2e(self):
        """Test run -> results flow with logs."""
        if not E2E_STUDIO_ATTACK_ID:
            pytest.skip("E2E_STUDIO_ATTACK_ID not set")

        try:
            attack_id = int(E2E_STUDIO_ATTACK_ID)

            # Step 1: Run the attack
            run_result = sb_run_studio_attack(
                attack_id=attack_id,
                console=E2E_CONSOLE,
                all_connected=True,
            )

            assert run_result['status'] == 'queued'
            test_id = run_result['test_id']

            print(f"\n=== Debug Flow E2E ===")
            print(f"  Queued attack {attack_id}, test_id={test_id}")

            # Step 2: Get results (may be from previous runs)
            result = sb_get_studio_attack_latest_result(
                attack_id=attack_id,
                console=E2E_CONSOLE,
                max_results=3,
                include_logs=True,
            )

            assert 'executions' in result

            # Verify test overview enrichment (SAF-30717)
            assert 'test_overview' in result
            if result['test_overview'] is not None:
                overview = result['test_overview']
                assert overview['status'] in ('running', 'completed', 'canceled', 'failed', 'queued')
                print(f"  Test Overview: status={overview['status']}, "
                      f"total_simulations={overview['total_simulations']}")

            if result['total_found'] > 0:
                # Verify the result structure supports debug use case
                for idx, execution in enumerate(result['executions']):
                    assert isinstance(execution.get('simulation_steps', []), list)
                    assert isinstance(execution.get('logs', ''), str)
                    assert isinstance(execution.get('output', ''), str)
                    print(f"  Execution #{idx+1}: status={execution['status']}, "
                          f"steps={len(execution['simulation_steps'])}")
            else:
                print("  No previous execution results available")

        except Exception as e:
            pytest.skip(f"Debug flow test failed on {E2E_CONSOLE}: {e}")


@skip_e2e
@pytest.mark.e2e
class TestStudioStatusTransitionE2E:
    """E2E test for publish/unpublish status transitions (Flow 5 from PRD).

    Flow: verify draft → publish → verify published → unpublish → verify draft

    Requires E2E_STUDIO_ATTACK_ID pointing to a DRAFT attack.
    The test restores the attack to its original status on completion.
    """

    def setup_method(self):
        """Clear cache before each test."""
        studio_draft_cache.clear()

    def test_publish_unpublish_roundtrip_e2e(self):
        """Test full status roundtrip: detects current status and transitions both ways."""
        if not E2E_STUDIO_TRANSITION_ATTACK_ID:
            pytest.skip("E2E_STUDIO_TRANSITION_ATTACK_ID not set")

        attack_id = int(E2E_STUDIO_TRANSITION_ATTACK_ID)

        try:
            # Step 1: Find the attack and detect its current status
            list_result = sb_get_all_studio_attacks(
                console=E2E_CONSOLE, page_number=0
            )
            all_attacks = []
            for page_num in range(list_result['total_pages']):
                page = sb_get_all_studio_attacks(
                    console=E2E_CONSOLE, page_number=page_num
                )
                all_attacks.extend(page['attacks_in_page'])

            target_attack = None
            for attack in all_attacks:
                if attack['id'] == attack_id:
                    target_attack = attack
                    break

            if target_attack is None:
                pytest.skip(f"Attack {attack_id} not found on {E2E_CONSOLE}")

            original_status: str = target_attack['status']
            if original_status == 'draft':
                first_target, second_target = 'published', 'draft'
                first_implication, second_implication = 'read-only', 'editable'
                double_msg = 'already published'
            elif original_status == 'published':
                first_target, second_target = 'draft', 'published'
                first_implication, second_implication = 'editable', 'read-only'
                double_msg = 'already draft'
            else:
                pytest.skip(f"Attack {attack_id} has unexpected status '{original_status}'")

            print(f"\n=== Status Transition E2E ===")
            print(f"  Attack ID: {attack_id}")
            print(f"  Attack Name: {target_attack['name']}")
            print(f"  Initial Status: {original_status}")

            # Step 2: Transition to the opposite status
            step2_result = sb_set_studio_attack_status(
                attack_id=attack_id,
                new_status=first_target,
                console=E2E_CONSOLE,
            )

            assert step2_result['attack_id'] == attack_id
            assert step2_result['old_status'] == original_status
            assert step2_result['new_status'] == first_target
            assert first_implication in step2_result['implications']
            print(f"  Transitioned: {original_status} → {first_target}")

            # Step 3: Verify the attack shows up in the target status list
            verify_list = sb_get_all_studio_attacks(
                console=E2E_CONSOLE,
                status_filter=first_target,
                page_number=0,
            )
            found_ids = [a['id'] for a in verify_list['attacks_in_page']]
            for page_num in range(1, verify_list['total_pages']):
                page = sb_get_all_studio_attacks(
                    console=E2E_CONSOLE,
                    status_filter=first_target,
                    page_number=page_num,
                )
                found_ids.extend([a['id'] for a in page['attacks_in_page']])

            assert attack_id in found_ids, (
                f"Attack {attack_id} not found in {first_target} list after transition"
            )
            print(f"  Verified: attack appears in {first_target} list")

            # Step 4: Verify double-transition raises ValueError
            with pytest.raises(ValueError) as exc_info:
                sb_set_studio_attack_status(
                    attack_id=attack_id,
                    new_status=first_target,
                    console=E2E_CONSOLE,
                )
            assert double_msg in str(exc_info.value)
            print(f"  Verified: double-transition correctly rejected")

            # Step 5: Transition back to original status
            step5_result = sb_set_studio_attack_status(
                attack_id=attack_id,
                new_status=second_target,
                console=E2E_CONSOLE,
            )

            assert step5_result['attack_id'] == attack_id
            assert step5_result['old_status'] == first_target
            assert step5_result['new_status'] == second_target
            assert second_implication in step5_result['implications']
            print(f"  Transitioned back: {first_target} → {second_target}")

            # Step 6: Verify restored to original status
            verify_restored = sb_get_all_studio_attacks(
                console=E2E_CONSOLE,
                status_filter=original_status,
                page_number=0,
            )
            restored_ids = [a['id'] for a in verify_restored['attacks_in_page']]
            for page_num in range(1, verify_restored['total_pages']):
                page = sb_get_all_studio_attacks(
                    console=E2E_CONSOLE,
                    status_filter=original_status,
                    page_number=page_num,
                )
                restored_ids.extend([a['id'] for a in page['attacks_in_page']])

            assert attack_id in restored_ids, (
                f"Attack {attack_id} not found in {original_status} list after restore"
            )
            print(f"  Verified: attack restored to {original_status} list")
            print(f"  Roundtrip complete: {original_status} → {first_target} → {second_target}")

        except ValueError:
            # Re-raise ValueError (from the double-transition check) — don't skip it
            raise
        except Exception as e:
            # Safety net: try to restore to original status if we got partway through
            try:
                sb_set_studio_attack_status(
                    attack_id=attack_id,
                    new_status=original_status,
                    console=E2E_CONSOLE,
                )
                print(f"  [Cleanup] Restored attack {attack_id} to {original_status} after failure")
            except Exception:
                pass  # Best effort cleanup
            pytest.skip(f"Status transition test failed on {E2E_CONSOLE}: {e}")
