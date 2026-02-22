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
from safebreach_mcp_playbook.playbook_functions import (
    sb_get_playbook_attacks,
    sb_get_playbook_attack_details,
    clear_playbook_cache
)
from safebreach_mcp_core.cache_config import is_caching_enabled


# Skip E2E tests if not in proper environment
E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'demo-console')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


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
            
            assert "not found" in str(exc_info.value).lower()
            
            # Test invalid attack ID
            with pytest.raises(ValueError) as exc_info:
                sb_get_playbook_attack_details(999999999, console=E2E_CONSOLE)
            
            assert "not found" in str(exc_info.value).lower()
            
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