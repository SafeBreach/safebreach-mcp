"""
End-to-End Tests for SafeBreach Playbook Server

This module tests the complete functionality using real API calls.
These tests require:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: See E2E_TESTING.md for complete setup instructions.
Security: All real environment details must be in private local files only.
"""

import pytest
import os
import time
import requests
from safebreach_mcp_playbook.playbook_functions import (
    sb_get_playbook_attacks,
    sb_get_playbook_attack_details,
    sb_get_playbook_attack_tags,
    sb_add_playbook_attack_tag,
    sb_remove_playbook_attack_tag,
    sb_rename_playbook_attack_tag,
    sb_bulk_add_playbook_attack_tags,
    sb_bulk_remove_playbook_attack_tags,
    sb_bulk_rename_playbook_attack_tag,
    MAX_BULK_ATTACK_IDS,
    MAX_BULK_TAG_VALUES,
    clear_playbook_cache,
)
from safebreach_mcp_core.cache_config import is_caching_enabled
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from safebreach_mcp_core.secret_utils import get_auth_headers_for_console


# Skip E2E tests if not in proper environment
E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'demo-console')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


def _move_exists_in_content_store(console, attack_id):
    """True if the move has a base row in the /content/v3 store (i.e. tag writes will not 404)."""
    base = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = get_auth_headers_for_console(console)
    url = f"{base}/api/content/v3/accounts/{account_id}/moves/{attack_id}/tags"
    return requests.get(url, headers=headers, timeout=60).status_code == 200


@pytest.fixture(scope="class")
def writable_move_ids():
    """Discover up to 2 playbook attacks whose moves exist in the /content/v3 write store.

    Self-discovering — no hardcoded IDs. Some consoles (e.g. pentest01) expose the KB moves
    but have an EMPTY /content/v3 store, so tag writes 404 there; on those, this fixture skips
    the whole write-suite class cleanly rather than failing.
    """
    found = []
    for page in range(0, 5):
        response = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=page)
        for attack in response.get('attacks_in_page', []):
            aid = attack['id']
            if _move_exists_in_content_store(E2E_CONSOLE, aid):
                found.append(aid)
                if len(found) >= 2:
                    return found
        if page + 1 >= response.get('total_pages', 0):
            break
    if not found:
        pytest.skip(
            f"Console '{E2E_CONSOLE}' has no writable /content/v3 move store "
            "(empty-store data condition); tag-write E2E cannot run here."
        )
    return found


@skip_e2e
@pytest.mark.e2e
class TestPlaybookE2E:
    """End-to-end tests for playbook functionality."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_playbook_cache()
    
    def test_get_playbook_attacks_real_api(self):
        """Test getting playbook attacks from real SafeBreach API."""
        try:
            result = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)
            
            # Verify response structure
            assert 'page_number' in result
            assert 'total_pages' in result
            assert 'total_attacks' in result
            assert 'attacks_in_page' in result
            assert 'applied_filters' in result
            
            # Verify we got some attacks
            assert result['total_attacks'] > 0
            assert len(result['attacks_in_page']) > 0
            
            # Verify attack structure
            first_attack = result['attacks_in_page'][0]
            required_fields = ['id', 'name', 'description', 'modifiedDate', 'publishedDate']
            for field in required_fields:
                assert field in first_attack
                assert first_attack[field] is not None
            
            # Verify ID is numeric
            assert isinstance(first_attack['id'], int)
            assert first_attack['id'] > 0
            
            print(f"✅ Successfully retrieved {result['total_attacks']} attacks from {E2E_CONSOLE}")
            
        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_get_playbook_attack_details_real_api(self):
        """Test getting attack details from real SafeBreach API."""
        try:
            # First get list of attacks to get a valid ID
            attacks_result = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)
            assert len(attacks_result['attacks_in_page']) > 0
            
            # Get details for first attack
            first_attack_id = attacks_result['attacks_in_page'][0]['id']
            
            # Test basic details
            basic_details = sb_get_playbook_attack_details(first_attack_id, console=E2E_CONSOLE)
            
            # Verify response structure
            required_fields = ['id', 'name', 'description', 'modifiedDate', 'publishedDate']
            for field in required_fields:
                assert field in basic_details
                assert basic_details[field] is not None
            
            assert basic_details['id'] == first_attack_id
            
            # Test with all verbosity options
            full_details = sb_get_playbook_attack_details(
                first_attack_id,
                console=E2E_CONSOLE,
                include_fix_suggestions=True,
                include_tags=True,
                include_parameters=True
            )
            
            # Should have same basic fields
            assert full_details['id'] == first_attack_id
            assert full_details['name'] == basic_details['name']
            
            # Check if optional fields are present (they might be None if not available)
            optional_fields = ['fix_suggestions', 'tags', 'params']
            for field in optional_fields:
                assert field in full_details  # Field should exist, even if None
            
            print(f"✅ Successfully retrieved details for attack {first_attack_id}")
            
        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_filtering_real_api(self):
        """Test filtering functionality with real API data."""
        try:
            # Get all attacks first
            all_attacks = sb_get_playbook_attacks(E2E_CONSOLE)
            total_all = all_attacks['total_attacks']
            
            # Test name filtering - try to find attacks with common terms
            common_terms = ['file', 'network', 'DNS', 'HTTP', 'SSH']
            found_filtered = False
            
            for term in common_terms:
                filtered_result = sb_get_playbook_attacks(console=E2E_CONSOLE, name_filter=term)
                
                # Should have applied the filter
                assert filtered_result['applied_filters'].get('name_filter') == term
                
                # Filtered result should be <= all attacks
                assert filtered_result['total_attacks'] <= total_all
                
                if filtered_result['total_attacks'] > 0:
                    found_filtered = True
                    # Verify filtering worked - attack names should contain the term
                    for attack in filtered_result['attacks_in_page']:
                        assert term.lower() in attack['name'].lower()
                    break
            
            # Should have found at least one filter that returns results
            assert found_filtered, f"No attacks found with common terms: {common_terms}"
            
            print(f"✅ Successfully tested filtering on {E2E_CONSOLE}")
            
        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_id_range_filtering_real_api(self):
        """Test ID range filtering with real API data."""
        try:
            # Get first page to see ID range
            first_page = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)
            
            if len(first_page['attacks_in_page']) >= 2:
                # Get min and max IDs from first few attacks
                ids = [attack['id'] for attack in first_page['attacks_in_page']]
                min_id = min(ids)
                max_id = max(ids)
                
                # Test filtering with a range that should include some attacks
                mid_range_min = min_id
                mid_range_max = min_id + ((max_id - min_id) // 2) if max_id > min_id else max_id
                
                filtered_result = sb_get_playbook_attacks(
                    console=E2E_CONSOLE,
                    id_min=mid_range_min,
                    id_max=mid_range_max
                )
                
                # Should have applied the filters
                assert filtered_result['applied_filters'].get('id_min') == mid_range_min
                assert filtered_result['applied_filters'].get('id_max') == mid_range_max
                
                # All returned attacks should be in range
                for attack in filtered_result['attacks_in_page']:
                    assert mid_range_min <= attack['id'] <= mid_range_max
                
                print(f"✅ Successfully tested ID range filtering: {mid_range_min}-{mid_range_max}")
            
        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_pagination_real_api(self):
        """Test pagination with real API data."""
        try:
            # Get first page
            page0 = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)
            
            if page0['total_pages'] > 1:
                # Get second page
                page1 = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=1)
                
                # Should have different attacks
                page0_ids = {attack['id'] for attack in page0['attacks_in_page']}
                page1_ids = {attack['id'] for attack in page1['attacks_in_page']}
                
                # Pages should not have overlapping attacks
                assert page0_ids.isdisjoint(page1_ids), "Pages have overlapping attacks"
                
                # Both pages should have consistent total counts
                assert page0['total_attacks'] == page1['total_attacks']
                assert page0['total_pages'] == page1['total_pages']
                
                print(f"✅ Successfully tested pagination: {page0['total_pages']} pages total")
            else:
                print(f"ℹ️ Only one page of results, pagination test limited")
                
        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_cache_behavior_real_api(self):
        """Test cache behavior with real API calls.

        This test only runs when caching is enabled via SB_MCP_CACHE_PLAYBOOK.
        """
        if not is_caching_enabled("playbook"):
            pytest.skip("Caching is disabled (SB_MCP_CACHE_PLAYBOOK not set to truthy value)")

        try:
            # Clear cache to ensure clean state
            clear_playbook_cache()

            start_time = time.time()

            # First call - should hit API
            first_call = sb_get_playbook_attacks(E2E_CONSOLE)
            first_call_time = time.time() - start_time

            start_time = time.time()

            # Second call - should use cache
            second_call = sb_get_playbook_attacks(E2E_CONSOLE)
            second_call_time = time.time() - start_time

            # Results should be identical
            assert first_call['total_attacks'] == second_call['total_attacks']
            assert len(first_call['attacks_in_page']) == len(second_call['attacks_in_page'])

            # Second call should be faster (cached)
            assert second_call_time < first_call_time, "Cache should make second call faster"

            print(f"✅ Cache working: First call {first_call_time:.2f}s, Second call {second_call_time:.2f}s")

        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_error_handling_real_api(self):
        """Test error handling with real API."""
        try:
            # Test invalid console
            with pytest.raises(ValueError) as exc_info:
                sb_get_playbook_attacks('nonexistent-console')

            err = str(exc_info.value).lower()
            assert "not found" in err or "no url configured" in err

            # Test invalid attack ID
            with pytest.raises(ValueError) as exc_info:
                sb_get_playbook_attack_details(999999999, console=E2E_CONSOLE)

            err = str(exc_info.value).lower()
            assert "not found" in err or "no url configured" in err
            
            # Test invalid page number
            invalid_page_result = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=999)
            assert 'error' in invalid_page_result
            assert 'Invalid page_number' in invalid_page_result['error']
            
            print(f"✅ Error handling working correctly")
            
        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_data_quality_real_api(self):
        """Test data quality from real API."""
        try:
            result = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)
            
            # Check data quality
            for attack in result['attacks_in_page'][:5]:  # Check first 5 attacks
                # ID should be positive integer
                assert isinstance(attack['id'], int)
                assert attack['id'] > 0
                
                # Name should be non-empty string
                assert isinstance(attack['name'], str)
                assert len(attack['name'].strip()) > 0
                
                # Description should be non-empty string
                assert isinstance(attack['description'], str)
                assert len(attack['description'].strip()) > 0
                
                # Dates should be in ISO format
                for date_field in ['modifiedDate', 'publishedDate']:
                    if attack[date_field]:
                        date_str = attack[date_field]
                        assert 'T' in date_str, f"{date_field} should be ISO format"
                        assert date_str.endswith('Z'), f"{date_field} should end with Z"
            
            print(f"✅ Data quality verified for {len(result['attacks_in_page'])} attacks")
            
        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")
    
    def test_verbosity_levels_real_api(self):
        """Test different verbosity levels with real API data."""
        try:
            # Get an attack ID
            attacks_result = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)
            attack_id = attacks_result['attacks_in_page'][0]['id']

            # Test different verbosity combinations (including MITRE)
            verbosity_tests = [
                {'include_fix_suggestions': True, 'include_tags': False, 'include_parameters': False},
                {'include_fix_suggestions': False, 'include_tags': True, 'include_parameters': False},
                {'include_fix_suggestions': False, 'include_tags': False, 'include_parameters': True},
                {'include_fix_suggestions': True, 'include_tags': True, 'include_parameters': True},
                {'include_mitre_techniques': True},
            ]

            for verbosity_options in verbosity_tests:
                details = sb_get_playbook_attack_details(attack_id, console=E2E_CONSOLE, **verbosity_options)

                # Basic fields should always be present
                basic_fields = ['id', 'name', 'description', 'modifiedDate', 'publishedDate']
                for field in basic_fields:
                    assert field in details

                # Check verbosity-specific fields
                if verbosity_options.get('include_fix_suggestions'):
                    assert 'fix_suggestions' in details
                if verbosity_options.get('include_tags'):
                    assert 'tags' in details
                if verbosity_options.get('include_parameters'):
                    assert 'params' in details
                if verbosity_options.get('include_mitre_techniques'):
                    assert 'mitre_tactics' in details
                    assert 'mitre_techniques' in details
                    assert 'mitre_sub_techniques' in details

            print(f"✅ Verbosity levels working correctly for attack {attack_id}")

        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")

    def test_mitre_data_real_api(self):
        """Test MITRE data retrieval from real SafeBreach API."""
        try:
            result = sb_get_playbook_attacks(
                console=E2E_CONSOLE, page_number=0, include_mitre_techniques=True
            )

            attacks = result['attacks_in_page']
            assert len(attacks) > 0

            # All attacks should have MITRE keys (even if empty lists)
            for attack in attacks:
                assert 'mitre_tactics' in attack
                assert 'mitre_techniques' in attack
                assert 'mitre_sub_techniques' in attack

            # Check multiple pages to find at least some with MITRE data
            found_mitre = False
            for page in range(min(5, result['total_pages'])):
                page_result = sb_get_playbook_attacks(
                    console=E2E_CONSOLE, page_number=page, include_mitre_techniques=True
                )
                for attack in page_result['attacks_in_page']:
                    if attack.get('mitre_techniques'):
                        found_mitre = True
                        # Verify structure
                        tech = attack['mitre_techniques'][0]
                        assert 'id' in tech
                        assert 'display_name' in tech
                        assert 'url' in tech
                        assert tech['url'].startswith('https://attack.mitre.org/techniques/')
                        break
                if found_mitre:
                    break

            assert found_mitre, "Expected at least some attacks with MITRE technique data"
            print(f"✅ MITRE data verified from {E2E_CONSOLE}")

        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")

    def test_mitre_filtering_real_api(self):
        """Test MITRE filtering with real SafeBreach API."""
        try:
            # Test tactic filter
            discovery_result = sb_get_playbook_attacks(
                console=E2E_CONSOLE, mitre_tactic_filter="Discovery"
            )
            assert discovery_result['total_attacks'] > 0

            # Verify all returned attacks have Discovery tactic
            for attack in discovery_result['attacks_in_page']:
                tactic_names = [t['name'].lower() for t in attack.get('mitre_tactics', [])]
                assert any('discovery' in name for name in tactic_names), \
                    f"Attack {attack['id']} missing Discovery tactic"

            # Test technique filter
            technique_result = sb_get_playbook_attacks(
                console=E2E_CONSOLE, mitre_technique_filter="T1046"
            )
            # T1046 may or may not be present, but the call should succeed
            assert 'total_attacks' in technique_result
            assert technique_result['applied_filters']['mitre_technique_filter'] == 'T1046'

            print(f"✅ MITRE filtering verified on {E2E_CONSOLE}")

        except Exception as e:
            pytest.fail(f"E2E test failed: {str(e)}")


VALID_OS_VALUES = {'ANY', 'AWS', 'AZURE', 'DOCKER', 'GCP', 'LINUX', 'MAC', 'MAILBOX', 'WEBAPPLICATION', 'WINDOWS'}


@skip_e2e
@pytest.mark.e2e
class TestPlatformE2E:
    """End-to-end tests for platform filtering — zero mocks."""

    def setup_method(self):
        clear_playbook_cache()

    def test_platform_fields_real_api(self):
        """Verify platform fields exist on every attack from real API."""
        result = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)
        assert result['total_attacks'] > 0

        for attack in result['attacks_in_page']:
            assert 'attacker_platform' in attack
            assert 'target_platform' in attack
            # Values are either None or a valid OS string
            for field in ['attacker_platform', 'target_platform']:
                val = attack[field]
                assert val is None or val in VALID_OS_VALUES, \
                    f"Attack {attack['id']} has unexpected {field}={val}"

        print(f"✅ Platform fields verified for {len(result['attacks_in_page'])} attacks")

    def test_target_platform_filter_windows(self):
        """Filter by target_platform=WINDOWS returns only WINDOWS attacks (strict)."""
        result = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS"
        )
        assert result['total_attacks'] > 0
        assert result['applied_filters']['target_platform_filter'] == 'WINDOWS'

        for attack in result['attacks_in_page']:
            tp = attack.get('target_platform')
            assert tp == 'WINDOWS', \
                f"Attack {attack['id']} has target_platform={tp}, expected WINDOWS"

        print(f"✅ WINDOWS target filter (strict): {result['total_attacks']} attacks")

    def test_attacker_platform_filter_linux(self):
        """Filter by attacker_platform=LINUX returns only LINUX attacker attacks (strict)."""
        result = sb_get_playbook_attacks(
            console=E2E_CONSOLE, attacker_platform_filter="LINUX"
        )
        assert result['total_attacks'] > 0

        for attack in result['attacks_in_page']:
            ap = attack.get('attacker_platform')
            assert ap == 'LINUX', \
                f"Attack {attack['id']} has attacker_platform={ap}, expected LINUX"

        print(f"✅ LINUX attacker filter (strict): {result['total_attacks']} attacks")

    def test_target_platform_filter_linux(self):
        """Filter by target_platform=LINUX returns only LINUX attacks (strict)."""
        result = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="LINUX"
        )
        assert result['total_attacks'] > 0

        for attack in result['attacks_in_page']:
            tp = attack.get('target_platform')
            assert tp == 'LINUX', f"Expected LINUX, got {tp}"

        print(f"✅ LINUX target filter: {result['total_attacks']} attacks")

    def test_platform_filter_multi_value(self):
        """Multi-value OR filter: WINDOWS,LINUX."""
        combined = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS,LINUX"
        )
        assert combined['total_attacks'] > 0

        for attack in combined['attacks_in_page']:
            tp = attack.get('target_platform')
            assert tp in ('WINDOWS', 'LINUX'), f"Expected WINDOWS or LINUX, got {tp}"

        # Combined should be >= individual filters
        win_only = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS"
        )
        linux_only = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="LINUX"
        )
        assert combined['total_attacks'] >= max(win_only['total_attacks'], linux_only['total_attacks'])

        print(f"✅ Multi-value filter: {combined['total_attacks']} attacks")

    def test_platform_filter_partial_match(self):
        """Partial match: 'win' should match WINDOWS."""
        partial = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="win"
        )
        full = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS"
        )
        assert partial['total_attacks'] == full['total_attacks']

        for attack in partial['attacks_in_page']:
            tp = attack.get('target_platform')
            assert tp == 'WINDOWS', f"Expected WINDOWS, got {tp}"

        print(f"✅ Partial match: {partial['total_attacks']} attacks")

    def test_platform_filter_case_insensitive(self):
        """Case insensitivity: 'windows' == 'WINDOWS'."""
        lower = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="windows"
        )
        upper = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS"
        )
        assert lower['total_attacks'] == upper['total_attacks']

        print(f"✅ Case insensitive: both return {lower['total_attacks']} attacks")

    def test_platform_filter_strict_excludes_any(self):
        """Strict filter: WINDOWS filter excludes ANY platform attacks."""
        strict_result = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS"
        )
        with_any_result = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS,ANY"
        )

        # Adding ANY should return more attacks
        assert with_any_result['total_attacks'] > strict_result['total_attacks'], \
            "WINDOWS,ANY should return more attacks than WINDOWS alone"

        # Strict result should have no ANY attacks
        for attack in strict_result['attacks_in_page']:
            tp = attack.get('target_platform')
            assert tp is None or 'WINDOWS' in tp, \
                f"Strict filter returned non-WINDOWS: {tp}"

        print(f"✅ Strict filtering verified: WINDOWS={strict_result['total_attacks']}, "
              f"WINDOWS,ANY={with_any_result['total_attacks']}")

    def test_platform_plus_name_filter(self):
        """Combined platform + name filter."""
        result = sb_get_playbook_attacks(
            console=E2E_CONSOLE,
            target_platform_filter="WINDOWS",
            name_filter="registry"
        )

        for attack in result['attacks_in_page']:
            assert 'registry' in attack['name'].lower()
            tp = attack.get('target_platform')
            assert tp == 'WINDOWS', f"Expected WINDOWS, got {tp}"

        # Combined should be <= individual filters
        win_only = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS"
        )
        name_only = sb_get_playbook_attacks(
            console=E2E_CONSOLE, name_filter="registry"
        )
        assert result['total_attacks'] <= win_only['total_attacks']
        assert result['total_attacks'] <= name_only['total_attacks']

        print(f"✅ Platform + name: {result['total_attacks']} attacks")

    def test_platform_plus_mitre_filter(self):
        """Combined platform + MITRE tactic filter."""
        result = sb_get_playbook_attacks(
            console=E2E_CONSOLE,
            target_platform_filter="WINDOWS",
            mitre_tactic_filter="Discovery"
        )

        for attack in result['attacks_in_page']:
            tp = attack.get('target_platform')
            assert tp == 'WINDOWS', f"Expected WINDOWS, got {tp}"
            tactic_names = [t['name'].lower() for t in attack.get('mitre_tactics', [])]
            assert any('discovery' in name for name in tactic_names), \
                f"Attack {attack['id']} missing Discovery tactic"

        print(f"✅ Platform + MITRE: {result['total_attacks']} attacks")

    def test_platform_filter_metadata(self):
        """Applied filters metadata contains both platform filters."""
        result = sb_get_playbook_attacks(
            console=E2E_CONSOLE,
            attacker_platform_filter="LINUX",
            target_platform_filter="WINDOWS"
        )

        assert result['applied_filters']['attacker_platform_filter'] == 'LINUX'
        assert result['applied_filters']['target_platform_filter'] == 'WINDOWS'

        print(f"✅ Filter metadata verified")

    def test_platform_filter_nonexistent(self):
        """Nonexistent platform returns no results (strict matching)."""
        result = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="NONEXISTENT_OS"
        )

        assert result['total_attacks'] == 0, \
            f"Expected 0 attacks for nonexistent platform, got {result['total_attacks']}"

        print(f"✅ Nonexistent filter: 0 attacks (strict)")

    def test_platform_filter_pagination(self):
        """Pagination works correctly with platform filter."""
        page0 = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS", page_number=0
        )

        if page0['total_pages'] > 1:
            page1 = sb_get_playbook_attacks(
                console=E2E_CONSOLE, target_platform_filter="WINDOWS", page_number=1
            )

            page0_ids = {a['id'] for a in page0['attacks_in_page']}
            page1_ids = {a['id'] for a in page1['attacks_in_page']}
            assert page0_ids.isdisjoint(page1_ids), "Pages have overlapping attacks"
            assert page0['total_attacks'] == page1['total_attacks']

            print(f"✅ Pagination: {page0['total_pages']} pages, disjoint verified")
        else:
            print(f"ℹ️ Only one page with WINDOWS filter")

    def test_platform_in_attack_details(self):
        """Get details for a WINDOWS attack from filtered list."""
        attacks_result = sb_get_playbook_attacks(
            console=E2E_CONSOLE, target_platform_filter="WINDOWS"
        )

        # Find first attack with actual WINDOWS platform (not None)
        target_id = None
        for attack in attacks_result['attacks_in_page']:
            if attack.get('target_platform') == 'WINDOWS':
                target_id = attack['id']
                break

        if target_id:
            details = sb_get_playbook_attack_details(target_id, console=E2E_CONSOLE)
            assert details['id'] == target_id
            assert details['name'] is not None
            print(f"✅ Attack details verified for {target_id}")
        else:
            print(f"ℹ️ No WINDOWS attacks found in first page")


def _unique_tag(suffix=""):
    """A tag value unlikely to collide with existing data, so tests are self-isolating."""
    return f"mcp-e2e-{int(time.time() * 1000)}{('-' + suffix) if suffix else ''}"


def _current_tags(console, attack_id):
    """Read-back helper: clear cache then fetch the attack's custom tags fresh."""
    clear_playbook_cache()
    return sb_get_playbook_attack_tags(console=console, attack_id=attack_id)['tags']


def _cleanup_tags(console, attack_ids, candidate_tags):
    """Best-effort, residue-free cleanup.

    Removes ONLY the candidate tags actually present on each move — the backend returns HTTP 400
    when asked to remove a tag that isn't there (so a blind remove-both after a rename would fail
    and leave residue). Errors are swallowed so cleanup never masks the test's real assertion.
    """
    for attack_id in attack_ids:
        present = set(_current_tags(console, attack_id))
        for tag in candidate_tags:
            if tag in present:
                try:
                    sb_remove_playbook_attack_tag(console=console, attack_id=attack_id, tag_value=tag)
                except Exception:  # noqa: BLE001 - cleanup is best-effort
                    pass
    clear_playbook_cache()


@skip_e2e
@pytest.mark.e2e
class TestPlaybookTagWriteE2E:
    """SAF-29870 reqs 1/3/4 — live, self-cleaning tag write + bulk + get-tags E2E.

    Every mutating test restores state in a finally block (add→verify→remove), so the suite is
    idempotent, order-independent, and leaves no residue on the console. On consoles with an empty
    /content/v3 store the mutating tests skip via the `writable_move_ids` fixture; the read-only and
    guard tests below still run everywhere.
    """

    def setup_method(self):
        clear_playbook_cache()

    # ---- req 3: read tags on an attack (works even on empty-write-store consoles) ---------- #

    def test_get_tags_on_attack_e2e(self):
        """get_playbook_attack_tags returns a well-formed custom-tag list for a real attack."""
        attack_id = sb_get_playbook_attacks(console=E2E_CONSOLE, page_number=0)['attacks_in_page'][0]['id']
        result = sb_get_playbook_attack_tags(console=E2E_CONSOLE, attack_id=attack_id)

        assert result['attack_id'] == attack_id
        assert isinstance(result['tags'], list)
        assert 'hint_to_agent' in result

    # ---- req 1: single add / remove / rename round-trips (self-cleaning) ------------------- #

    def test_add_read_remove_tag_roundtrip_e2e(self, writable_move_ids):
        """Add a tag → verify via get-tags → remove it → verify removal (state restored)."""
        attack_id = writable_move_ids[0]
        tag = _unique_tag("single")
        try:
            add_result = sb_add_playbook_attack_tag(console=E2E_CONSOLE, attack_id=attack_id, tag_value=tag)
            assert add_result['success'] is True and add_result['action'] == 'added'
            assert tag in _current_tags(E2E_CONSOLE, attack_id)
        finally:
            sb_remove_playbook_attack_tag(console=E2E_CONSOLE, attack_id=attack_id, tag_value=tag)
        assert tag not in _current_tags(E2E_CONSOLE, attack_id)

    def test_rename_tag_roundtrip_e2e(self, writable_move_ids):
        """Add old tag → rename to new → verify swap → remove new (state restored)."""
        attack_id = writable_move_ids[0]
        old_tag = _unique_tag("old")
        new_tag = _unique_tag("new")
        try:
            sb_add_playbook_attack_tag(console=E2E_CONSOLE, attack_id=attack_id, tag_value=old_tag)
            rename_result = sb_rename_playbook_attack_tag(
                console=E2E_CONSOLE, attack_id=attack_id, old_value=old_tag, new_value=new_tag)
            assert rename_result['action'] == 'renamed'
            tags = _current_tags(E2E_CONSOLE, attack_id)
            assert new_tag in tags and old_tag not in tags
        finally:
            _cleanup_tags(E2E_CONSOLE, [attack_id], [old_tag, new_tag])
        final_tags = _current_tags(E2E_CONSOLE, attack_id)
        assert old_tag not in final_tags and new_tag not in final_tags

    # ---- req 4: bulk (many tags on many attacks) round-trips (self-cleaning) --------------- #

    def test_bulk_add_remove_roundtrip_e2e(self, writable_move_ids):
        """Bulk-add N tags on N attacks → verify each → bulk-remove → verify removal."""
        tag_a = _unique_tag("bulkA")
        tag_b = _unique_tag("bulkB")
        tags = [tag_a, tag_b]
        try:
            add_result = sb_bulk_add_playbook_attack_tags(
                console=E2E_CONSOLE, attack_ids=writable_move_ids, tag_values=tags)
            assert add_result['success'] is True and add_result['action'] == 'bulk_added'
            for attack_id in writable_move_ids:
                current = _current_tags(E2E_CONSOLE, attack_id)
                assert tag_a in current and tag_b in current
        finally:
            sb_bulk_remove_playbook_attack_tags(
                console=E2E_CONSOLE, attack_ids=writable_move_ids, tag_values=tags)
        for attack_id in writable_move_ids:
            current = _current_tags(E2E_CONSOLE, attack_id)
            assert tag_a not in current and tag_b not in current

    def test_bulk_rename_roundtrip_e2e(self, writable_move_ids):
        """Bulk-add a tag on N attacks → bulk-rename it → verify swap → bulk-remove (restored)."""
        old_tag = _unique_tag("bulkOld")
        new_tag = _unique_tag("bulkNew")
        try:
            sb_bulk_add_playbook_attack_tags(
                console=E2E_CONSOLE, attack_ids=writable_move_ids, tag_values=[old_tag])
            rename_result = sb_bulk_rename_playbook_attack_tag(
                console=E2E_CONSOLE, attack_ids=writable_move_ids, old_value=old_tag, new_value=new_tag)
            assert rename_result['action'] == 'bulk_renamed'
            for attack_id in writable_move_ids:
                current = _current_tags(E2E_CONSOLE, attack_id)
                assert new_tag in current and old_tag not in current
        finally:
            _cleanup_tags(E2E_CONSOLE, writable_move_ids, [old_tag, new_tag])
        for attack_id in writable_move_ids:
            current = _current_tags(E2E_CONSOLE, attack_id)
            assert old_tag not in current and new_tag not in current

    # ---- req 4 NFR: guardrail caps + input validation (no live writes; always run) --------- #

    def test_bulk_attack_id_cap_enforced_e2e(self):
        """More than MAX_BULK_ATTACK_IDS attack ids is refused before any API call."""
        too_many = ",".join(str(i) for i in range(MAX_BULK_ATTACK_IDS + 1))
        with pytest.raises(ValueError, match="max"):
            sb_bulk_add_playbook_attack_tags(console=E2E_CONSOLE, attack_ids=too_many, tag_values="x")

    def test_bulk_tag_value_cap_enforced_e2e(self):
        """More than MAX_BULK_TAG_VALUES tag values is refused before any API call."""
        too_many = ",".join(f"t{i}" for i in range(MAX_BULK_TAG_VALUES + 1))
        with pytest.raises(ValueError, match="max"):
            sb_bulk_add_playbook_attack_tags(console=E2E_CONSOLE, attack_ids="1", tag_values=too_many)

    def test_add_empty_tag_rejected_e2e(self):
        """An empty tag value is rejected before any API call."""
        with pytest.raises(ValueError):
            sb_add_playbook_attack_tag(console=E2E_CONSOLE, attack_id=1, tag_value="  ")

    def test_rename_noop_rejected_e2e(self):
        """A no-op rename (old == new) is rejected before any API call."""
        with pytest.raises(ValueError, match="differ"):
            sb_rename_playbook_attack_tag(
                console=E2E_CONSOLE, attack_id=1, old_value="same", new_value="same")