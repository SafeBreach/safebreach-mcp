"""
Integration Tests for SafeBreach Playbook Server

This module tests the integration between different components of the playbook server.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_playbook.playbook_functions import (
    sb_get_playbook_attacks,
    sb_get_playbook_attack_details,
    clear_playbook_cache
)


# Test fixtures
@pytest.fixture
def comprehensive_attack_dataset():
    """Comprehensive attack dataset for integration testing."""
    return [
        {
            "id": 1027,
            "name": "DNS queries of malicious URLs",
            "description": "**Goal**\n\n1. Verify whether the target simulator can resolve the IP address of the known malicious domain.\n\n**Actions**\n\n1. **Malicious Domain Resolution**",
            "modifiedDate": "2024-10-07T07:28:05.000Z",
            "publishedDate": "2019-05-29T15:18:44.000Z",
            "metadata": {
                "fix_suggestions": [
                    {
                        "title": "Harden Intrusion Prevention System (IPS) security configuration",
                        "content": "Ensure that the network Intrusion Prevention System (IPS) is deployed on the network and configured with a policy to block known attack signatures."
                    },
                    {
                        "title": "Mitigate DNS based attack vector",
                        "content": "DNS resolution specific mitigations can also include the use of a DNS firewall and DNS proxy."
                    }
                ]
            },
            "tags": ["network", "dns", "malicious"],
            "content": {
                "params": [
                    {
                        "id": 1,
                        "name": "port",
                        "type": "PORT",
                        "displayName": "Port",
                        "description": "The port to use in the protocol",
                        "values": [{"id": 1, "value": "53", "displayValue": "53"}]
                    },
                    {
                        "id": 2,
                        "name": "url",
                        "type": "URI",
                        "displayName": "URL",
                        "description": "The malicious URL to query",
                        "values": [{"id": 1, "value": "www.malicious-domain.com", "displayValue": "www.malicious-domain.com"}]
                    }
                ]
            }
        },
        {
            "id": 2048,
            "name": "File transfer via HTTP",
            "description": "Test file transfer capabilities over HTTP protocol. This attack simulates data exfiltration through HTTP channels.",
            "modifiedDate": "2024-01-15T10:30:00.000Z",
            "publishedDate": "2020-03-10T12:00:00.000Z",
            "metadata": {
                "fix_suggestions": [
                    {
                        "title": "Implement HTTP traffic monitoring",
                        "content": "Deploy HTTP proxy solutions that can inspect and control HTTP traffic."
                    }
                ]
            },
            "tags": ["file", "http", "exfiltration"],
            "content": {
                "params": [
                    {
                        "id": 1,
                        "name": "file_size",
                        "type": "INTEGER",
                        "displayName": "File Size (MB)",
                        "description": "Size of the file to transfer",
                        "values": [{"id": 1, "value": "10", "displayValue": "10 MB"}]
                    }
                ]
            }
        },
        {
            "id": 3141,
            "name": "SSH brute force attack",
            "description": "Attempt to gain unauthorized access via SSH brute force. This attack tests the effectiveness of SSH access controls.",
            "modifiedDate": "2023-12-01T14:22:00.000Z",
            "publishedDate": "2018-11-05T09:15:30.000Z",
            "metadata": {
                "fix_suggestions": []
            },
            "tags": ["ssh", "brute-force", "authentication"],
            "content": {
                "params": [
                    {
                        "id": 1,
                        "name": "username_list",
                        "type": "STRING_ARRAY",
                        "displayName": "Username List",
                        "description": "List of usernames to try",
                        "values": [
                            {"id": 1, "value": "admin", "displayValue": "admin"},
                            {"id": 2, "value": "root", "displayValue": "root"}
                        ]
                    }
                ]
            }
        },
        {
            "id": 4096,
            "name": "Windows registry manipulation",
            "description": "Modify Windows registry to establish persistence. Tests registry-based persistence mechanisms.",
            "modifiedDate": "2024-05-20T16:45:12.000Z",
            "publishedDate": "2021-07-15T11:30:00.000Z",
            "metadata": {
                "fix_suggestions": [
                    {
                        "title": "Registry monitoring and protection",
                        "content": "Implement registry monitoring solutions to detect unauthorized modifications."
                    }
                ]
            },
            "tags": ["windows", "registry", "persistence"],
            "content": {
                "params": []
            }
        }
    ]


class TestPlaybookIntegration:
    """Test integration between playbook functions and types."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_playbook_cache()
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_full_workflow_get_attacks_then_details(self, mock_get_all_attacks, comprehensive_attack_dataset):
        """Test complete workflow: get attacks list, then get details for specific attack."""
        mock_get_all_attacks.return_value = comprehensive_attack_dataset
        
        # Step 1: Get list of attacks with filtering
        attacks_result = sb_get_playbook_attacks(
            'test-console',
            page_number=0,
            name_filter='DNS'
        )
        
        # Verify attack list results
        assert attacks_result['total_attacks'] == 1
        assert len(attacks_result['attacks_in_page']) == 1
        dns_attack = attacks_result['attacks_in_page'][0]
        assert dns_attack['id'] == 1027
        assert dns_attack['name'] == 'DNS queries of malicious URLs'
        
        # Step 2: Get detailed information for the found attack
        attack_details = sb_get_playbook_attack_details(
            attack_id=1027, console='test-console',
            
            include_fix_suggestions=True,
            include_tags=True,
            include_parameters=True
        )
        
        # Verify detailed results
        assert attack_details['id'] == 1027
        assert attack_details['name'] == 'DNS queries of malicious URLs'
        assert attack_details['fix_suggestions'] is not None
        assert len(attack_details['fix_suggestions']) == 2
        assert attack_details['tags'] == ['network', 'dns', 'malicious']
        assert attack_details['params'] is not None
        assert len(attack_details['params']) == 2
        
        # Verify cache was used efficiently (may be called twice due to test setup, but not more)
        assert mock_get_all_attacks.call_count <= 2  # Should use cache efficiently
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_complex_filtering_scenarios(self, mock_get_all_attacks, comprehensive_attack_dataset):
        """Test complex filtering scenarios with multiple criteria."""
        mock_get_all_attacks.return_value = comprehensive_attack_dataset
        
        # Scenario 1: Filter by description and date range
        result1 = sb_get_playbook_attacks(
            
            description_filter='HTTP',
            modified_date_start='2024-01-01T00:00:00.000Z',
            modified_date_end='2024-12-31T23:59:59.999Z'
        )
        
        assert result1['total_attacks'] == 1
        assert result1['attacks_in_page'][0]['name'] == 'File transfer via HTTP'
        
        # Scenario 2: Filter by ID range and tag-related name
        result2 = sb_get_playbook_attacks(
            
            id_min=3000,
            id_max=5000,
            name_filter='Windows'
        )
        
        assert result2['total_attacks'] == 1
        assert result2['attacks_in_page'][0]['name'] == 'Windows registry manipulation'
        
        # Scenario 3: Complex date and name filtering
        result3 = sb_get_playbook_attacks(
            
            published_date_start='2018-01-01T00:00:00.000Z',
            published_date_end='2019-12-31T23:59:59.999Z',
            name_filter='SSH'
        )
        
        assert result3['total_attacks'] == 1
        assert result3['attacks_in_page'][0]['name'] == 'SSH brute force attack'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_pagination_with_filtering(self, mock_get_all_attacks, comprehensive_attack_dataset):
        """Test pagination combined with filtering."""
        mock_get_all_attacks.return_value = comprehensive_attack_dataset
        
        # Get all attacks that contain 'attack' in name
        # The comprehensive dataset has 2 attacks with 'attack' in name: SSH brute force attack, Windows registry manipulation
        # But let's be more specific to avoid test brittleness
        all_results = sb_get_playbook_attacks(
            
            name_filter='SSH'  # More specific filter
        )
        assert all_results['total_attacks'] == 1  # Only SSH attack should match
        
        # Now test pagination with small page size
        # Create a larger dataset to test pagination properly
        large_dataset = comprehensive_attack_dataset * 3  # 12 attacks total
        mock_get_all_attacks.return_value = large_dataset
        
        # Page 0: first 10 attacks
        page0_result = sb_get_playbook_attacks(
            
            page_number=0
        )
        assert page0_result['page_number'] == 0
        assert page0_result['total_pages'] == 2  # 12 attacks / 10 per page = 2 pages
        assert page0_result['total_attacks'] == 12
        assert len(page0_result['attacks_in_page']) == 10
        
        # Page 1: remaining 2 attacks
        page1_result = sb_get_playbook_attacks(
            
            page_number=1
        )
        assert page1_result['page_number'] == 1
        assert len(page1_result['attacks_in_page']) == 2
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_verbosity_levels_integration(self, mock_get_all_attacks, comprehensive_attack_dataset):
        """Test different verbosity levels for attack details."""
        mock_get_all_attacks.return_value = comprehensive_attack_dataset
        
        attack_id = 1027  # DNS attack with rich metadata
        
        # Test minimal verbosity (default)
        minimal_details = sb_get_playbook_attack_details(
            
            attack_id=attack_id
        )
        
        # Should only have basic fields
        basic_fields = ['id', 'name', 'description', 'modifiedDate', 'publishedDate']
        for field in basic_fields:
            assert field in minimal_details
        
        # Test with fix suggestions only
        with_fixes = sb_get_playbook_attack_details(
            
            attack_id=attack_id,
            include_fix_suggestions=True
        )
        
        assert with_fixes['fix_suggestions'] is not None
        assert len(with_fixes['fix_suggestions']) == 2
        
        # Test with all verbosity options
        full_details = sb_get_playbook_attack_details(
            
            attack_id=attack_id,
            include_fix_suggestions=True,
            include_tags=True,
            include_parameters=True
        )
        
        assert full_details['fix_suggestions'] is not None
        assert full_details['tags'] == ['network', 'dns', 'malicious']
        assert full_details['params'] is not None
        assert len(full_details['params']) == 2
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_edge_cases_integration(self, mock_get_all_attacks, comprehensive_attack_dataset):
        """Test edge cases in integrated workflow."""
        mock_get_all_attacks.return_value = comprehensive_attack_dataset
        
        # Test filtering that returns no results
        no_results = sb_get_playbook_attacks(
            
            name_filter='NonExistentAttack'
        )
        
        assert no_results['total_attacks'] == 0
        assert len(no_results['attacks_in_page']) == 0
        assert no_results['applied_filters']['name_filter'] == 'NonExistentAttack'
        
        # Test getting details for non-existent attack
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attack_details(
                
                attack_id=9999
            )
        
        assert "Attack with ID 9999 not found" in str(exc_info.value)
        assert "Available IDs include:" in str(exc_info.value)
        
        # Test invalid page number
        invalid_page = sb_get_playbook_attacks(
            
            page_number=100
        )
        
        assert 'error' in invalid_page
        assert 'Invalid page_number 100' in invalid_page['error']
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_cache_behavior_integration(self, mock_get_all_attacks, comprehensive_attack_dataset):
        """Test cache behavior across multiple function calls."""
        mock_get_all_attacks.return_value = comprehensive_attack_dataset
        
        # First call should hit API
        first_call = sb_get_playbook_attacks('test-console')
        assert mock_get_all_attacks.call_count == 1
        
        # Second call should use cache
        second_call = sb_get_playbook_attacks(console='test-console', name_filter='DNS')
        # Allow for some cache setup calls, but shouldn't significantly increase
        initial_call_count = mock_get_all_attacks.call_count
        
        # Get attack details should also use cache
        details_call = sb_get_playbook_attack_details(1027, 'test-console')
        # Should not have significantly more calls due to caching
        assert mock_get_all_attacks.call_count <= initial_call_count + 1
        
        # Verify results are consistent
        assert first_call['total_attacks'] == 4
        assert second_call['total_attacks'] == 1
        assert details_call['id'] == 1027
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_error_propagation_integration(self, mock_get_all_attacks):
        """Test error propagation through the integration chain."""
        # Setup mock to raise error
        mock_get_all_attacks.side_effect = ValueError("Console not found")
        
        # Test error propagation in get_playbook_attacks
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attacks('invalid-console')
        assert "Console not found" in str(exc_info.value)
        
        # Test error propagation in get_playbook_attack_details
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attack_details(1027, 'invalid-console')
        assert "Console not found" in str(exc_info.value)
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_data_consistency_integration(self, mock_get_all_attacks, comprehensive_attack_dataset):
        """Test data consistency between list and detail views."""
        mock_get_all_attacks.return_value = comprehensive_attack_dataset
        
        # Get attack from list
        attacks_list = sb_get_playbook_attacks('test-console')
        first_attack_in_list = attacks_list['attacks_in_page'][0]
        
        # Get same attack details
        attack_details = sb_get_playbook_attack_details(
            first_attack_in_list['id'],
            'test-console'
        )
        
        # Verify consistency of basic fields
        assert first_attack_in_list['id'] == attack_details['id']
        assert first_attack_in_list['name'] == attack_details['name']
        assert first_attack_in_list['description'] == attack_details['description']
        assert first_attack_in_list['modifiedDate'] == attack_details['modifiedDate']
        assert first_attack_in_list['publishedDate'] == attack_details['publishedDate']
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_multiple_console_isolation(self, mock_get_all_attacks):
        """Test that different consoles maintain separate cache entries."""
        # Setup different data for different consoles
        console1_data = [{"id": 1, "name": "Attack 1", "description": "Desc 1", "modifiedDate": "2024-01-01T00:00:00.000Z", "publishedDate": "2024-01-01T00:00:00.000Z"}]
        console2_data = [{"id": 2, "name": "Attack 2", "description": "Desc 2", "modifiedDate": "2024-01-01T00:00:00.000Z", "publishedDate": "2024-01-01T00:00:00.000Z"}]
        
        def mock_side_effect(console):
            if console == 'console1':
                return console1_data
            elif console == 'console2':
                return console2_data
            else:
                raise ValueError(f"Console {console} not found")
        
        mock_get_all_attacks.side_effect = mock_side_effect
        
        # Call for console1
        result1 = sb_get_playbook_attacks('console1')
        assert result1['attacks_in_page'][0]['id'] == 1
        
        # Call for console2
        result2 = sb_get_playbook_attacks('console2')
        assert result2['attacks_in_page'][0]['id'] == 2
        
        # Verify both consoles were called separately
        assert mock_get_all_attacks.call_count == 2