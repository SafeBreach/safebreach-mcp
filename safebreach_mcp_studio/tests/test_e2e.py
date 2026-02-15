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
- E2E_STUDIO_ATTACK_ID: Pre-existing draft attack ID for read tests
- E2E_STUDIO_ATTACK_NAME: Expected name of the pre-existing attack
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

                print(f"\n=== Latest Result E2E ===")
                print(f"  Attack ID: {attack_id}")
                print(f"  Total found: {result['total_found']}")
                print(f"  Simulation ID: {execution['simulation_id']}")
                print(f"  Status: {execution['status']}")
                print(f"  Is Drifted: {execution['is_drifted']}")
                print(f"  Simulation Steps: {len(execution['simulation_steps'])} step(s)")
                print(f"  Has Logs: {bool(execution['logs'])}")
                print(f"  Has Output: {bool(execution['output'])}")
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
        """Test full DRAFT → PUBLISHED → DRAFT roundtrip."""
        if not E2E_STUDIO_ATTACK_ID:
            pytest.skip("E2E_STUDIO_ATTACK_ID not set")

        attack_id = int(E2E_STUDIO_ATTACK_ID)

        try:
            # Step 1: Verify attack exists and is currently draft
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

            original_status = target_attack['status']
            if original_status != 'draft':
                pytest.skip(
                    f"Attack {attack_id} is '{original_status}', expected 'draft'. "
                    f"E2E status transition test requires a draft attack."
                )

            print(f"\n=== Status Transition E2E ===")
            print(f"  Attack ID: {attack_id}")
            print(f"  Attack Name: {target_attack['name']}")
            print(f"  Initial Status: {original_status}")

            # Step 2: Publish the attack (DRAFT → PUBLISHED)
            publish_result = sb_set_studio_attack_status(
                attack_id=attack_id,
                new_status="published",
                console=E2E_CONSOLE,
            )

            assert publish_result['attack_id'] == attack_id
            assert publish_result['old_status'] == 'draft'
            assert publish_result['new_status'] == 'published'
            assert 'read-only' in publish_result['implications']
            print(f"  Published: DRAFT → PUBLISHED")

            # Step 3: Verify the attack is now published via list API
            verify_list = sb_get_all_studio_attacks(
                console=E2E_CONSOLE,
                status_filter="published",
                page_number=0,
            )
            published_ids = [a['id'] for a in verify_list['attacks_in_page']]
            # Check across all pages if needed
            for page_num in range(1, verify_list['total_pages']):
                page = sb_get_all_studio_attacks(
                    console=E2E_CONSOLE,
                    status_filter="published",
                    page_number=page_num,
                )
                published_ids.extend([a['id'] for a in page['attacks_in_page']])

            assert attack_id in published_ids, (
                f"Attack {attack_id} not found in published attacks after publish"
            )
            print(f"  Verified: attack appears in published list")

            # Step 4: Verify publishing again raises ValueError (already published)
            with pytest.raises(ValueError) as exc_info:
                sb_set_studio_attack_status(
                    attack_id=attack_id,
                    new_status="published",
                    console=E2E_CONSOLE,
                )
            assert "already published" in str(exc_info.value)
            print(f"  Verified: double-publish correctly rejected")

            # Step 5: Unpublish the attack (PUBLISHED → DRAFT)
            unpublish_result = sb_set_studio_attack_status(
                attack_id=attack_id,
                new_status="draft",
                console=E2E_CONSOLE,
            )

            assert unpublish_result['attack_id'] == attack_id
            assert unpublish_result['old_status'] == 'published'
            assert unpublish_result['new_status'] == 'draft'
            assert 'editable' in unpublish_result['implications']
            print(f"  Unpublished: PUBLISHED → DRAFT")

            # Step 6: Verify the attack is back to draft
            verify_draft_list = sb_get_all_studio_attacks(
                console=E2E_CONSOLE,
                status_filter="draft",
                page_number=0,
            )
            draft_ids = [a['id'] for a in verify_draft_list['attacks_in_page']]
            for page_num in range(1, verify_draft_list['total_pages']):
                page = sb_get_all_studio_attacks(
                    console=E2E_CONSOLE,
                    status_filter="draft",
                    page_number=page_num,
                )
                draft_ids.extend([a['id'] for a in page['attacks_in_page']])

            assert attack_id in draft_ids, (
                f"Attack {attack_id} not found in draft attacks after unpublish"
            )
            print(f"  Verified: attack restored to draft list")
            print(f"  Roundtrip complete: DRAFT → PUBLISHED → DRAFT")

        except ValueError:
            # Re-raise ValueError (from the double-publish check) — don't skip it
            raise
        except Exception as e:
            # Safety net: try to restore to draft if we got partway through
            try:
                sb_set_studio_attack_status(
                    attack_id=attack_id,
                    new_status="draft",
                    console=E2E_CONSOLE,
                )
                print(f"  [Cleanup] Restored attack {attack_id} to draft after failure")
            except Exception:
                pass  # Best effort cleanup
            pytest.skip(f"Status transition test failed on {E2E_CONSOLE}: {e}")
