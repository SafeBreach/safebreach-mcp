"""
Tests for SafeBreach Playbook Functions

This module tests the core business logic functions for playbook operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_playbook.playbook_functions import (
    sb_get_playbook_attacks,
    sb_get_playbook_attack_details,
    _get_all_attacks_from_cache_or_api,
    clear_playbook_cache,
    playbook_cache
)


# Test fixtures
@pytest.fixture
def sample_attack_data():
    """Sample attack data in SafeBreach API format."""
    return [
        {
            "id": 1027,
            "name": "DNS queries of malicious URLs",
            "description": "**Goal**\n\n1. Verify whether the target simulator can resolve the IP address of the known malicious domain.",
            "modifiedDate": "2024-10-07T07:28:05.000Z",
            "publishedDate": "2019-05-29T15:18:44.000Z",
            "metadata": {
                "fix_suggestions": [
                    {
                        "title": "Harden Intrusion Prevention System (IPS) security configuration",
                        "content": "Ensure that the network Intrusion Prevention System (IPS) is deployed on the network"
                    }
                ]
            },
            "tags": ["network", "dns"],
            "content": {
                "params": [
                    {
                        "id": 1,
                        "name": "port",
                        "type": "PORT",
                        "displayName": "Port",
                        "description": "The port to use in the protocol",
                        "values": [{"id": 1, "value": "53", "displayValue": "53"}]
                    }
                ]
            }
        },
        {
            "id": 2048,
            "name": "File transfer via HTTP",
            "description": "Test file transfer capabilities over HTTP protocol.",
            "modifiedDate": "2024-01-15T10:30:00.000Z",
            "publishedDate": "2020-03-10T12:00:00.000Z",
            "metadata": {
                "fix_suggestions": []
            },
            "tags": ["file", "http"],
            "content": {
                "params": []
            }
        }
    ]


@pytest.fixture
def mock_console_environments():
    """Mock SafeBreach environments."""
    return {
        'test-console': {
            'url': 'test-console.safebreach.com',
            'account': '1234567890'
        }
    }


class TestGetAllAttacksFromCacheOrApi:
    """Test the _get_all_attacks_from_cache_or_api function."""

    @pytest.fixture(autouse=True)
    def set_auth_context(self, mcp_request_auth):
        with mcp_request_auth({"x-apitoken": "test-token"}):
            yield
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_playbook_cache()
    
    def teardown_method(self):
        """Clear cache after each test."""
        clear_playbook_cache()
    
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    def test_invalid_console(self, mock_base_url):
        """Test error handling for invalid console name."""
        mock_base_url.side_effect = ValueError("Environment 'invalid-console' not found. Available environments: ['valid-console1', 'valid-console2']")
        
        with pytest.raises(ValueError) as exc_info:
            _get_all_attacks_from_cache_or_api('invalid-console')
        
        # In single-tenant mode, error message is about missing environment variable
        # In multi-tenant mode, it would be about console not found
        assert "not found" in str(exc_info.value) or "Environment variable" in str(exc_info.value)
    
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    def test_api_call_success(self, mock_base_url, mock_requests_get, sample_attack_data):
        """Test successful API call."""
        # Setup mocks
        mock_base_url.return_value = 'https://test-console.safebreach.com'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': sample_attack_data}
        mock_requests_get.return_value = mock_response
        
        # Call function
        result = _get_all_attacks_from_cache_or_api('test-console')
        
        # Verify results
        assert result == sample_attack_data
        assert len(result) == 2
        assert result[0]['id'] == 1027
        assert result[1]['id'] == 2048
        
        # Verify API call was made correctly
        mock_requests_get.assert_called_once()
        call_args = mock_requests_get.call_args
        assert 'https://test-console.safebreach.com/api/kb/vLatest/moves?details=true' in call_args[0]
        assert call_args[1]['headers']['x-apitoken'] == 'test-token'
        assert call_args[1]['timeout'] == 120
    
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    def test_api_call_error(self, mock_base_url, mock_requests_get):
        """Test API call error handling."""
        # Setup mocks
        mock_base_url.return_value = 'https://test-console.safebreach.com'
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_requests_get.return_value = mock_response
        
        # Call function and verify error
        with pytest.raises(ValueError) as exc_info:
            _get_all_attacks_from_cache_or_api('test-console')
        
        assert "API call failed with status 500" in str(exc_info.value)
    
    @patch('safebreach_mcp_playbook.playbook_functions.is_caching_enabled', return_value=True)
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    @patch('safebreach_mcp_playbook.playbook_functions.playbook_cache')
    def test_cache_hit(self, mock_cache, mock_base_url, mock_requests_get, mock_cache_enabled, sample_attack_data):
        """Test cache hit scenario when caching is enabled."""
        # Setup mocks - these shouldn't be called due to cache hit
        mock_base_url.return_value = 'https://test-console.safebreach.com'

        # Configure SafeBreachCache mock to return data on .get()
        mock_cache.get = Mock(return_value=sample_attack_data)

        # Call function
        result = _get_all_attacks_from_cache_or_api('test-console')

        # Verify results
        assert result == sample_attack_data

        # Verify no API call was made (cache hit)
        mock_requests_get.assert_not_called()
    
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    def test_cache_expired(self, mock_base_url, mock_requests_get, sample_attack_data):
        """Test expired cache scenario."""
        # Setup mocks
        mock_base_url.return_value = 'https://test-console.safebreach.com'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': sample_attack_data}
        mock_requests_get.return_value = mock_response
        
        # Cache is empty (simulates expired/missing - TTLCache handles real expiry internally)

        # Call function
        result = _get_all_attacks_from_cache_or_api('test-console')

        # Verify results
        assert result == sample_attack_data

        # Verify API call was made due to cache miss
        mock_requests_get.assert_called_once()


class TestGetPlaybookAttacks:
    """Test the sb_get_playbook_attacks function."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_playbook_cache()
    
    def teardown_method(self):
        """Clear cache after each test."""
        clear_playbook_cache()
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_basic_success(self, mock_get_all_attacks, sample_attack_data):
        """Test basic successful call."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks('test-console')
        
        # Verify structure
        assert 'page_number' in result
        assert 'total_pages' in result
        assert 'total_attacks' in result
        assert 'attacks_in_page' in result
        assert 'applied_filters' in result
        
        # Verify content
        assert result['page_number'] == 0
        assert result['total_attacks'] == 2
        assert len(result['attacks_in_page']) == 2
        assert result['attacks_in_page'][0]['id'] == 1027
        assert result['attacks_in_page'][1]['id'] == 2048
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_name_filter(self, mock_get_all_attacks, sample_attack_data):
        """Test name filtering."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks(console='test-console', name_filter='DNS')
        
        # Should only return the DNS attack
        assert result['total_attacks'] == 1
        assert len(result['attacks_in_page']) == 1
        assert result['attacks_in_page'][0]['name'] == 'DNS queries of malicious URLs'
        assert result['applied_filters']['name_filter'] == 'DNS'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_description_filter(self, mock_get_all_attacks, sample_attack_data):
        """Test description filtering."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks(console='test-console', description_filter='HTTP')
        
        # Should only return the HTTP attack
        assert result['total_attacks'] == 1
        assert len(result['attacks_in_page']) == 1
        assert result['attacks_in_page'][0]['name'] == 'File transfer via HTTP'
        assert result['applied_filters']['description_filter'] == 'HTTP'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_id_range_filter(self, mock_get_all_attacks, sample_attack_data):
        """Test ID range filtering."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks(console='test-console', id_min=2000, id_max=3000)
        
        # Should only return attack with ID 2048
        assert result['total_attacks'] == 1
        assert len(result['attacks_in_page']) == 1
        assert result['attacks_in_page'][0]['id'] == 2048
        assert result['applied_filters']['id_min'] == 2000
        assert result['applied_filters']['id_max'] == 3000
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_date_range_filter(self, mock_get_all_attacks, sample_attack_data):
        """Test date range filtering."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks(
            'test-console', 
            modified_date_start='2024-01-01T00:00:00.000Z',
            modified_date_end='2024-06-01T00:00:00.000Z'
        )
        
        # Should only return the HTTP attack (modified in 2024-01-15)
        assert result['total_attacks'] == 1
        assert len(result['attacks_in_page']) == 1
        assert result['attacks_in_page'][0]['id'] == 2048
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_pagination(self, mock_get_all_attacks):
        """Test pagination functionality."""
        # Create 25 sample attacks for pagination testing
        large_attack_list = []
        for i in range(25):
            large_attack_list.append({
                "id": i + 1,
                "name": f"Attack {i + 1}",
                "description": f"Description for attack {i + 1}",
                "modifiedDate": "2024-01-01T00:00:00.000Z",
                "publishedDate": "2024-01-01T00:00:00.000Z"
            })
        
        mock_get_all_attacks.return_value = large_attack_list
        
        # Test first page
        result = sb_get_playbook_attacks(console='test-console', page_number=0)
        assert result['page_number'] == 0
        assert result['total_pages'] == 3  # 25 attacks / 10 per page = 3 pages
        assert result['total_attacks'] == 25
        assert len(result['attacks_in_page']) == 10
        assert result['attacks_in_page'][0]['id'] == 1
        assert result['attacks_in_page'][9]['id'] == 10
        
        # Test second page
        result = sb_get_playbook_attacks(console='test-console', page_number=1)
        assert result['page_number'] == 1
        assert len(result['attacks_in_page']) == 10
        assert result['attacks_in_page'][0]['id'] == 11
        assert result['attacks_in_page'][9]['id'] == 20
        
        # Test last page
        result = sb_get_playbook_attacks(console='test-console', page_number=2)
        assert result['page_number'] == 2
        assert len(result['attacks_in_page']) == 5  # Last page has only 5 items
        assert result['attacks_in_page'][0]['id'] == 21
        assert result['attacks_in_page'][4]['id'] == 25
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_invalid_page_number(self, mock_get_all_attacks, sample_attack_data):
        """Test invalid page number handling."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks(console='test-console', page_number=10)
        
        # Should return error information
        assert 'error' in result
        assert 'Invalid page_number 10' in result['error']
        assert result['total_attacks'] == 2
        assert result['attacks_in_page'] == []
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_combined_filters(self, mock_get_all_attacks, sample_attack_data):
        """Test combining multiple filters."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks(
            'test-console',
            name_filter='DNS',
            id_min=1000,
            id_max=2000
        )
        
        # Should return DNS attack that matches ID range
        assert result['total_attacks'] == 1
        assert result['attacks_in_page'][0]['name'] == 'DNS queries of malicious URLs'
        assert result['applied_filters']['name_filter'] == 'DNS'
        assert result['applied_filters']['id_min'] == 1000
        assert result['applied_filters']['id_max'] == 2000
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_no_matches(self, mock_get_all_attacks, sample_attack_data):
        """Test when filters return no matches."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks(console='test-console', name_filter='NonExistentAttack')
        
        # Should return empty results
        assert result['total_attacks'] == 0
        assert result['attacks_in_page'] == []
        assert result['applied_filters']['name_filter'] == 'NonExistentAttack'


class TestGetPlaybookAttackDetails:
    """Test the sb_get_playbook_attack_details function."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_playbook_cache()
    
    def teardown_method(self):
        """Clear cache after each test."""
        clear_playbook_cache()
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_basic_success(self, mock_get_all_attacks, sample_attack_data):
        """Test basic successful call."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details(1027, 'test-console')
        
        # Verify basic fields
        assert result['id'] == 1027
        assert result['name'] == 'DNS queries of malicious URLs'
        assert result['description'] == sample_attack_data[0]['description']
        assert result['modifiedDate'] == '2024-10-07T07:28:05.000Z'
        assert result['publishedDate'] == '2019-05-29T15:18:44.000Z'
        
        # Verify optional fields are not included by default
        assert result.get('fix_suggestions') is None
        assert result.get('tags') is None
        assert result.get('params') is None
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_with_fix_suggestions(self, mock_get_all_attacks, sample_attack_data):
        """Test including fix suggestions."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details(1027, 'test-console', include_fix_suggestions=True)
        
        # Verify fix suggestions are included
        assert result['fix_suggestions'] is not None
        assert len(result['fix_suggestions']) == 1
        assert result['fix_suggestions'][0]['title'] == 'Harden Intrusion Prevention System (IPS) security configuration'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_with_tags(self, mock_get_all_attacks, sample_attack_data):
        """Test including tags."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details(1027, 'test-console', include_tags=True)
        
        # Verify tags are included
        assert result['tags'] == ['network', 'dns']
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_with_parameters(self, mock_get_all_attacks, sample_attack_data):
        """Test including parameters."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details(1027, 'test-console', include_parameters=True)
        
        # Verify parameters are included
        assert result['params'] is not None
        assert len(result['params']) == 1
        assert result['params'][0]['name'] == 'port'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_all_verbosity_options(self, mock_get_all_attacks, sample_attack_data):
        """Test including all verbosity options."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details(
            1027, 
            'test-console', 
            include_fix_suggestions=True,
            include_tags=True,
            include_parameters=True
        )
        
        # Verify all optional fields are included
        assert result['fix_suggestions'] is not None
        assert result['tags'] is not None
        assert result['params'] is not None
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_attack_not_found(self, mock_get_all_attacks, sample_attack_data):
        """Test error handling when attack ID is not found."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attack_details(9999, 'test-console')
        
        assert "Attack with ID 9999 not found" in str(exc_info.value)
        assert "Available IDs include:" in str(exc_info.value)


class TestCacheFunctionality:
    """Test cache-related functionality."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_playbook_cache()
    
    def teardown_method(self):
        """Clear cache after each test."""
        clear_playbook_cache()
    
    def test_clear_cache(self):
        """Test cache clearing functionality."""
        # Ensure we start with a completely empty cache
        playbook_cache.clear()
        assert len(playbook_cache) == 0

        # Add something to cache
        playbook_cache.set('test_key', 'test')
        assert len(playbook_cache) == 1

        # Clear cache using the function
        clear_playbook_cache()
        assert len(playbook_cache) == 0


# MITRE-specific fixtures and tests

@pytest.fixture
def sample_attack_data_with_mitre():
    """Sample attack data with MITRE tags in real API structure."""
    return [
        {
            "id": 1027,
            "name": "DNS queries of malicious URLs",
            "description": "Verify DNS resolution of malicious domains.",
            "modifiedDate": "2024-10-07T07:28:05.000Z",
            "publishedDate": "2019-05-29T15:18:44.000Z",
            "metadata": {"fix_suggestions": []},
            "tags": [
                {"id": 1, "name": "category",
                 "values": [{"id": 1, "value": "network", "displayName": "Network"}]},
                {"id": 10, "name": "MITRE_Tactic",
                 "values": [{"id": 1, "sort": 1, "value": "Discovery", "displayName": "Discovery"}]},
                {"id": 11, "name": "MITRE_Technique",
                 "values": [{"id": 1, "sort": 1, "value": "T1046",
                              "displayName": "(T1046) Network Service Discovery"}]}
            ],
            "content": {"params": []}
        },
        {
            "id": 2048,
            "name": "Remote Desktop lateral movement",
            "description": "Attempt RDP connection.",
            "modifiedDate": "2024-01-15T10:30:00.000Z",
            "publishedDate": "2020-03-10T12:00:00.000Z",
            "metadata": {"fix_suggestions": []},
            "tags": [
                {"id": 10, "name": "MITRE_Tactic",
                 "values": [{"id": 2, "sort": 1, "value": "Lateral Movement",
                              "displayName": "Lateral Movement"}]},
                {"id": 11, "name": "MITRE_Technique",
                 "values": [{"id": 2, "sort": 1, "value": "T1021",
                              "displayName": "(T1021) Remote Services"}]},
                {"id": 12, "name": "MITRE_Sub_Technique",
                 "values": [{"id": 1, "sort": 1, "value": "T1021.001",
                              "displayName": "(T1021.001) Remote Desktop Protocol"}]}
            ],
            "content": {"params": []}
        }
    ]


class TestMitreGetPlaybookAttacks:
    """Test MITRE functionality in sb_get_playbook_attacks."""

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_mitre_inclusion(self, mock_get_all, sample_attack_data_with_mitre):
        """Test include_mitre_techniques=True returns MITRE data."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attacks('test-console', include_mitre_techniques=True)

        attacks = result['attacks_in_page']
        assert len(attacks) == 2

        # First attack should have MITRE data
        assert 'mitre_tactics' in attacks[0]
        assert 'mitre_techniques' in attacks[0]
        assert attacks[0]['mitre_techniques'][0]['id'] == 'T1046'

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_mitre_technique_filter(self, mock_get_all, sample_attack_data_with_mitre):
        """Test mitre_technique_filter filters correctly."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attacks('test-console', mitre_technique_filter="T1046")

        assert result['total_attacks'] == 1
        assert result['attacks_in_page'][0]['id'] == 1027

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_mitre_tactic_filter(self, mock_get_all, sample_attack_data_with_mitre):
        """Test mitre_tactic_filter filters correctly."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attacks('test-console', mitre_tactic_filter="Discovery")

        assert result['total_attacks'] == 1
        assert result['attacks_in_page'][0]['id'] == 1027

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_mitre_auto_enable_with_filter(self, mock_get_all, sample_attack_data_with_mitre):
        """Test MITRE auto-enabled when filter is used without include_mitre_techniques."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attacks(
            'test-console',
            include_mitre_techniques=False,
            mitre_technique_filter="T1046"
        )

        # MITRE data should be present (auto-enabled for filtering)
        assert 'mitre_techniques' in result['attacks_in_page'][0]
        assert result['attacks_in_page'][0]['mitre_techniques'][0]['id'] == 'T1046'

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_mitre_filter_in_applied_filters(self, mock_get_all, sample_attack_data_with_mitre):
        """Test MITRE filter values appear in applied_filters metadata."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attacks(
            'test-console',
            mitre_technique_filter="T1046",
            mitre_tactic_filter="Discovery"
        )

        assert result['applied_filters']['mitre_technique_filter'] == 'T1046'
        assert result['applied_filters']['mitre_tactic_filter'] == 'Discovery'

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_mitre_tactic_filter_by_id(self, mock_get_all, sample_attack_data_with_mitre):
        """Test mitre_tactic_filter with tactic ID (TA0007) resolves to Discovery."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attacks('test-console', mitre_tactic_filter="TA0007")

        assert result['total_attacks'] == 1
        assert result['attacks_in_page'][0]['id'] == 1027


class TestMitreGetPlaybookAttackDetails:
    """Test MITRE functionality in sb_get_playbook_attack_details."""

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_with_mitre_techniques(self, mock_get_all, sample_attack_data_with_mitre):
        """Test include_mitre_techniques=True returns MITRE data."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attack_details(1027, 'test-console', include_mitre_techniques=True)

        assert 'mitre_tactics' in result
        assert 'mitre_techniques' in result
        assert result['mitre_tactics'][0]['name'] == 'Discovery'
        assert result['mitre_techniques'][0]['id'] == 'T1046'

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_without_mitre_techniques(self, mock_get_all, sample_attack_data_with_mitre):
        """Test default (False) does not include MITRE data."""
        mock_get_all.return_value = sample_attack_data_with_mitre

        result = sb_get_playbook_attack_details(1027, 'test-console')

        assert 'mitre_tactics' not in result
        assert 'mitre_techniques' not in result


# Platform-specific fixtures and tests

@pytest.fixture
def sample_attack_data_with_platform():
    """Sample attack data with platform info in content.nodes structure."""
    return [
        {
            "id": 1001,
            "name": "Windows registry manipulation",
            "description": "Modify Windows registry for persistence.",
            "modifiedDate": "2024-05-20T16:45:12.000Z",
            "publishedDate": "2021-07-15T11:30:00.000Z",
            "metadata": {"fix_suggestions": []},
            "tags": [],
            "content": {
                "params": [],
                "nodes": {
                    "gold": {
                        "isSource": False,
                        "isDestination": False,
                        "constraints": {"os": "WINDOWS", "framework": "3.100.0"}
                    }
                }
            }
        },
        {
            "id": 1002,
            "name": "HTTP file transfer exfiltration",
            "description": "Transfer file over HTTP from Linux attacker.",
            "modifiedDate": "2024-01-15T10:30:00.000Z",
            "publishedDate": "2020-03-10T12:00:00.000Z",
            "metadata": {"fix_suggestions": []},
            "tags": [],
            "content": {
                "params": [],
                "nodes": {
                    "green": {
                        "isSource": True,
                        "isDestination": False,
                        "constraints": {"os": "LINUX"}
                    },
                    "red": {
                        "isSource": False,
                        "isDestination": True,
                        "constraints": {"os": "WINDOWS"}
                    }
                }
            }
        },
        {
            "id": 1003,
            "name": "ARP scanning of local subnet",
            "description": "Discover hosts on network via ARP.",
            "modifiedDate": "2024-10-07T07:28:05.000Z",
            "publishedDate": "2019-05-29T15:18:44.000Z",
            "metadata": {"fix_suggestions": []},
            "tags": [],
            "content": {
                "params": [],
                "nodes": {
                    "gold": {
                        "isSource": False,
                        "isDestination": False,
                        "constraints": {"framework": "3.146.0"}
                    }
                }
            }
        }
    ]


class TestPlatformGetPlaybookAttacks:
    """Test platform functionality in sb_get_playbook_attacks."""

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_platform_fields_always_present(self, mock_get_all, sample_attack_data_with_platform):
        """Platform fields should always be present in response."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks('test-console')

        for attack in result['attacks_in_page']:
            assert 'attacker_platform' in attack
            assert 'target_platform' in attack

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_platform_extraction_values(self, mock_get_all, sample_attack_data_with_platform):
        """Platform values extracted correctly from node data."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks('test-console')
        attacks = {a['id']: a for a in result['attacks_in_page']}

        # Attack 1001: gold node (host) — target=WINDOWS, attacker=None (no nodes for attacker)
        assert attacks[1001]['target_platform'] == 'WINDOWS'
        assert attacks[1001]['attacker_platform'] is None

        # Attack 1002: green/red — attacker=LINUX, target=WINDOWS
        assert attacks[1002]['attacker_platform'] == 'LINUX'
        assert attacks[1002]['target_platform'] == 'WINDOWS'

        # Attack 1003: gold node no OS — target=ANY, attacker=None
        assert attacks[1003]['attacker_platform'] is None
        assert attacks[1003]['target_platform'] == 'ANY'

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_target_platform_filter_strict(self, mock_get_all, sample_attack_data_with_platform):
        """Strict filter: only WINDOWS matches, ANY excluded."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks('test-console', target_platform_filter="WINDOWS")

        ids = [a['id'] for a in result['attacks_in_page']]
        # 1001: target=WINDOWS (match), 1002: target=WINDOWS (match), 1003: target=ANY (excluded)
        assert set(ids) == {1001, 1002}

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_target_platform_filter_with_any(self, mock_get_all, sample_attack_data_with_platform):
        """Filter WINDOWS,ANY includes WINDOWS + ANY platform attacks."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks('test-console', target_platform_filter="WINDOWS,ANY")

        ids = [a['id'] for a in result['attacks_in_page']]
        assert set(ids) == {1001, 1002, 1003}

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_attacker_platform_filter_strict(self, mock_get_all, sample_attack_data_with_platform):
        """Strict filter on attacker: only LINUX matches."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks('test-console', attacker_platform_filter="LINUX")

        ids = [a['id'] for a in result['attacks_in_page']]
        # Only 1002 has attacker=LINUX; 1001,1003 have attacker=None (excluded)
        assert set(ids) == {1002}

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_platform_filter_combined_with_name(self, mock_get_all, sample_attack_data_with_platform):
        """Platform + name filter combination."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks(
            'test-console', target_platform_filter="WINDOWS", name_filter="registry"
        )

        ids = [a['id'] for a in result['attacks_in_page']]
        assert ids == [1001]

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_platform_filter_applied_filters_metadata(self, mock_get_all, sample_attack_data_with_platform):
        """Platform filters appear in applied_filters metadata."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks(
            'test-console',
            attacker_platform_filter="LINUX",
            target_platform_filter="WINDOWS"
        )

        assert result['applied_filters']['attacker_platform_filter'] == 'LINUX'
        assert result['applied_filters']['target_platform_filter'] == 'WINDOWS'

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_platform_filter_nonexistent_returns_empty(self, mock_get_all, sample_attack_data_with_platform):
        """Nonexistent platform returns no results (strict)."""
        mock_get_all.return_value = sample_attack_data_with_platform

        result = sb_get_playbook_attacks('test-console', target_platform_filter="NONEXISTENT")

        assert result['total_attacks'] == 0

def _raw_attack(attack_id, name, is_alm, tactic=None):
    """Build a raw API-shaped move, optionally ALM-tagged and/or tactic-tagged."""
    tags = []
    if is_alm:
        tags.append({"id": 44, "name": "ALM",
                     "values": [{"id": 1, "value": "1", "displayName": "1"}]})
    if tactic:
        tags.append({"id": 3, "name": "MITRE_Tactic",
                     "values": [{"id": 9, "value": tactic, "displayName": tactic}]})
    return {
        "id": attack_id,
        "name": name,
        "description": f"description of {name}",
        "modifiedDate": "2024-10-07T07:28:05.000Z",
        "publishedDate": "2019-05-29T15:18:44.000Z",
        "tags": tags,
        "content": {},
    }


@pytest.fixture
def mixed_scope_raw_attacks():
    """3 Validate + 2 Propagate — asymmetric so a collapsed count cannot coincidentally match."""
    return [
        _raw_attack(101, 'validate one', False),
        _raw_attack(102, 'validate two', False),
        _raw_attack(201, 'propagate one', True),
        _raw_attack(103, 'validate three', False),
        _raw_attack(202, 'propagate two', True),
    ]


@pytest.fixture
def credential_access_raw_attacks():
    """The reporter's shape: both catalogs carry the requested tactic."""
    return [
        _raw_attack(301, 'validate cred one', False, tactic='Credential Access'),
        _raw_attack(302, 'validate cred two', False, tactic='Credential Access'),
        _raw_attack(401, 'propagate cred one', True, tactic='Credential Access'),
        _raw_attack(303, 'validate other', False, tactic='Discovery'),
        _raw_attack(402, 'propagate other', True, tactic='Discovery'),
    ]


class TestTestTypeGetPlaybookAttacks:
    """T-11 through T-19 — scope default, validation, ordering, disclosure."""

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_default_scope_is_validate(self, mock_get_all, mixed_scope_raw_attacks):
        """T-11: omitting test_type excludes Propagate without the caller doing anything."""
        mock_get_all.return_value = mixed_scope_raw_attacks

        result = sb_get_playbook_attacks('test-console')

        returned_ids = [a['id'] for a in result['attacks_in_page']]
        assert returned_ids == [101, 102, 103]
        assert result['total_attacks'] == 3

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_total_reflects_scope_not_catalog(self, mock_get_all):
        """T-12: scope is applied BEFORE pagination, so the total and page count follow the scope."""
        attacks = [_raw_attack(i, f'validate {i}', False) for i in range(12)]
        attacks += [_raw_attack(900 + i, f'propagate {i}', True) for i in range(9)]
        mock_get_all.return_value = attacks

        result = sb_get_playbook_attacks('test-console')

        assert result['total_attacks'] == 12
        assert result['total_pages'] == 2
        assert all(not a['is_propagate'] for a in result['attacks_in_page'])

        all_scope = sb_get_playbook_attacks('test-console', test_type='all')
        assert all_scope['total_attacks'] == 21
        assert all_scope['total_pages'] == 3

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_invalid_test_type_raises_naming_valid_values(self, mock_get_all, mixed_scope_raw_attacks):
        """T-13: an unusable value fails loudly with a message an agent can recover from."""
        mock_get_all.return_value = mixed_scope_raw_attacks

        with pytest.raises(ValueError) as exc:
            sb_get_playbook_attacks('test-console', test_type='bogus')

        message = str(exc.value)
        assert 'bogus' in message
        for valid in ('validate', 'propagate', 'all'):
            assert valid in message

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_applied_filters_echoes_scope(self, mock_get_all, mixed_scope_raw_attacks):
        """T-14: the scope in force is disclosed, including on a defaulted call."""
        mock_get_all.return_value = mixed_scope_raw_attacks

        defaulted = sb_get_playbook_attacks('test-console')
        assert defaulted['applied_filters']['test_type'] == 'validate'

        for scope in ('validate', 'propagate', 'all'):
            result = sb_get_playbook_attacks('test-console', test_type=scope)
            assert result['applied_filters']['test_type'] == scope

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_default_call_discloses_excluded_count(self, mock_get_all, mixed_scope_raw_attacks):
        """T-15: the default is safe AND honest — the inversion of the reported complaint."""
        mock_get_all.return_value = mixed_scope_raw_attacks

        result = sb_get_playbook_attacks('test-console')

        hint = result['hint_to_agent']
        assert hint
        assert '2' in hint
        assert 'Propagate' in hint
        assert "test_type='all'" in hint

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_no_hint_when_nothing_excluded(self, mock_get_all):
        """T-16: a Validate-only console gets no confusing '0 excluded' line."""
        mock_get_all.return_value = [_raw_attack(1, 'validate only', False)]

        result = sb_get_playbook_attacks('test-console')

        assert not result['hint_to_agent'] or 'Propagate' not in result['hint_to_agent']

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_next_page_hint_is_preserved(self, mock_get_all):
        """T-17: the new disclosure composes with the paginator's hint instead of replacing it."""
        attacks = [_raw_attack(i, f'validate {i}', False) for i in range(25)]
        attacks += [_raw_attack(900 + i, f'propagate {i}', True) for i in range(3)]
        mock_get_all.return_value = attacks

        result = sb_get_playbook_attacks('test-console', page_number=0)

        hint = result['hint_to_agent']
        assert 'page_number' in hint
        assert 'Propagate' in hint
        assert 'page_number=1 111' not in hint
        assert '. 3 Propagate' in hint

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_excluded_count_is_after_other_criteria(self, mock_get_all, credential_access_raw_attacks):
        """T-18: the excluded count describes what THIS query dropped, not the whole catalog."""
        mock_get_all.return_value = credential_access_raw_attacks

        result = sb_get_playbook_attacks('test-console', mitre_tactic_filter='Credential Access')

        assert '1' in result['hint_to_agent']
        assert '2 Propagate' not in result['hint_to_agent']

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_reported_defect_repro(self, mock_get_all, credential_access_raw_attacks):
        """T-19: repro-regression for the reported defect — red before the fix, green after."""
        mock_get_all.return_value = credential_access_raw_attacks

        result = sb_get_playbook_attacks('test-console', mitre_tactic_filter='Credential Access')

        returned_ids = sorted(a['id'] for a in result['attacks_in_page'])
        assert returned_ids == [301, 302]
        assert result['total_attacks'] == 2
        assert 401 not in returned_ids

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_propagate_scope_returns_only_propagate(self, mock_get_all, mixed_scope_raw_attacks):
        """T-11 (cont.): an explicit Propagate request is never mixed."""
        mock_get_all.return_value = mixed_scope_raw_attacks

        result = sb_get_playbook_attacks('test-console', test_type='propagate')

        assert sorted(a['id'] for a in result['attacks_in_page']) == [201, 202]
        assert result['total_attacks'] == 2

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_all_scope_returns_per_catalog_counts(self, mock_get_all, mixed_scope_raw_attacks):
        """T-19 (cont.): 'all' returns the split the renderer needs, without recounting."""
        mock_get_all.return_value = mixed_scope_raw_attacks

        result = sb_get_playbook_attacks('test-console', test_type='all')

        assert result['total_attacks'] == 5
        assert result['validate_count'] == 3
        assert result['propagate_count'] == 2
        assert result['validate_count'] + result['propagate_count'] == result['total_attacks']


def _draft_raw_attack(attack_id, name, status=None, is_alm=False):
    """Raw move with an explicit publication status."""
    a = _raw_attack(attack_id, name, is_alm)
    if status is not None:
        a['status'] = status
    return a


@pytest.fixture
def draft_mix_raw_attacks():
    """2 published + 1 statusless (legacy OOB) + 2 drafts, one of which is also Propagate."""
    return [
        _draft_raw_attack(101, 'published one', status='published'),
        _draft_raw_attack(102, 'legacy no status'),
        _draft_raw_attack(103, 'published two', status='published'),
        _draft_raw_attack(901, 'draft one', status='draft'),
        _draft_raw_attack(902, 'draft propagate', status='draft', is_alm=True),
    ]


class TestDraftExclusion:
    """Draft moves are hidden by the Playbook UI, so Helm must hide them by default (SAF-34553)."""

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_drafts_excluded_by_default(self, mock_get_all, draft_mix_raw_attacks):
        """The default answer counts only what the Playbook UI shows."""
        mock_get_all.return_value = draft_mix_raw_attacks

        result = sb_get_playbook_attacks('test-console')

        assert sorted(a['id'] for a in result['attacks_in_page']) == [101, 102, 103]
        assert result['total_attacks'] == 3

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_statusless_moves_are_not_treated_as_drafts(self, mock_get_all, draft_mix_raw_attacks):
        """OOB moves carry no status field at all — they must stay visible."""
        mock_get_all.return_value = draft_mix_raw_attacks

        result = sb_get_playbook_attacks('test-console')

        assert 102 in [a['id'] for a in result['attacks_in_page']]

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_include_drafts_brings_them_back(self, mock_get_all, draft_mix_raw_attacks):
        """An author asking for their drafts can still reach them."""
        mock_get_all.return_value = draft_mix_raw_attacks

        result = sb_get_playbook_attacks('test-console', include_drafts=True)

        assert 901 in [a['id'] for a in result['attacks_in_page']]
        assert result['total_attacks'] == 4

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_draft_exclusion_is_disclosed(self, mock_get_all, draft_mix_raw_attacks):
        """Silently dropping drafts would repeat the very defect this ticket fixes."""
        mock_get_all.return_value = draft_mix_raw_attacks

        result = sb_get_playbook_attacks('test-console')

        hint = result['hint_to_agent']
        assert 'draft' in hint.lower()
        assert 'include_drafts=True' in hint

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_no_draft_hint_when_none_excluded(self, mock_get_all):
        """No noise on a console with no drafts."""
        mock_get_all.return_value = [_draft_raw_attack(1, 'published', status='published')]

        result = sb_get_playbook_attacks('test-console')

        assert not result['hint_to_agent'] or 'draft' not in result['hint_to_agent'].lower()

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_scope_counts_exclude_drafts(self, mock_get_all, draft_mix_raw_attacks):
        """The per-catalog split must describe visible attacks, or it won't match the UI."""
        mock_get_all.return_value = draft_mix_raw_attacks

        result = sb_get_playbook_attacks('test-console', test_type='all')

        assert result['validate_count'] == 3
        assert result['propagate_count'] == 0
        assert result['total_attacks'] == 3

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_drafts_and_propagate_are_independent(self, mock_get_all, draft_mix_raw_attacks):
        """The draft Propagate attack appears only when both gates are opened."""
        mock_get_all.return_value = draft_mix_raw_attacks

        both = sb_get_playbook_attacks('test-console', test_type='all', include_drafts=True)
        assert 902 in [a['id'] for a in both['attacks_in_page']]

        propagate_only = sb_get_playbook_attacks('test-console', test_type='propagate')
        assert propagate_only['total_attacks'] == 0

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_applied_filters_records_draft_handling(self, mock_get_all, draft_mix_raw_attacks):
        """The active draft gate is disclosed like every other filter."""
        mock_get_all.return_value = draft_mix_raw_attacks

        assert sb_get_playbook_attacks('test-console')['applied_filters']['include_drafts'] is False
        assert sb_get_playbook_attacks(
            'test-console', include_drafts=True)['applied_filters']['include_drafts'] is True


class TestDraftCountIsScopeAware:
    """The hidden-draft count must describe the REQUESTED scope, not the whole filtered set.

    Found by a live sanity run: with test_type='propagate' the tool claimed 15 drafts were hidden
    when all 15 were Validate and none were in scope. Same ordering trap T-18 guards for the
    Propagate count, made in the mirror direction.
    """

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    def _dataset(self):
        """3 published validate, 2 published propagate, 2 validate drafts, 0 propagate drafts."""
        return [
            _draft_raw_attack(101, 'validate a', status='published'),
            _draft_raw_attack(102, 'validate b', status='published'),
            _draft_raw_attack(103, 'validate c', status='published'),
            _draft_raw_attack(201, 'propagate a', status='published', is_alm=True),
            _draft_raw_attack(202, 'propagate b', status='published', is_alm=True),
            _draft_raw_attack(901, 'validate draft a', status='draft'),
            _draft_raw_attack(902, 'validate draft b', status='draft'),
        ]

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_propagate_scope_reports_no_hidden_drafts(self, mock_get_all):
        """No Propagate draft exists, so a Propagate-scoped answer must not claim drafts were hidden."""
        mock_get_all.return_value = self._dataset()

        result = sb_get_playbook_attacks('test-console', test_type='propagate')

        assert result['total_attacks'] == 2
        hint = result['hint_to_agent'] or ''
        assert 'draft' not in hint.lower(), (
            f"claimed drafts were hidden from the propagate scope, but none were: {hint}"
        )

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_validate_scope_reports_its_own_drafts(self, mock_get_all):
        """The Validate scope holds both drafts, so it must report exactly 2."""
        mock_get_all.return_value = self._dataset()

        result = sb_get_playbook_attacks('test-console')

        assert result['total_attacks'] == 3
        hint = result['hint_to_agent']
        assert '2 unpublished draft' in hint

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_all_scope_reports_every_hidden_draft(self, mock_get_all):
        """Scope 'all' spans both catalogs, so it reports every draft it hid."""
        mock_get_all.return_value = self._dataset()

        result = sb_get_playbook_attacks('test-console', test_type='all')

        assert result['total_attacks'] == 5
        assert '2 unpublished draft' in result['hint_to_agent']

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_propagate_drafts_are_counted_under_propagate_scope(self, mock_get_all):
        """Mirror case: a Propagate draft must be reported under the Propagate scope only."""
        data = self._dataset()
        data.append(_draft_raw_attack(903, 'propagate draft', status='draft', is_alm=True))
        mock_get_all.return_value = data

        propagate = sb_get_playbook_attacks('test-console', test_type='propagate')
        assert '1 unpublished draft' in propagate['hint_to_agent']

        validate = sb_get_playbook_attacks('test-console')
        assert '2 unpublished draft' in validate['hint_to_agent']

    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_split_counts_stay_consistent_with_the_total(self, mock_get_all):
        """validate_count + propagate_count must always equal total_attacks, drafts or not."""
        data = self._dataset()
        data.append(_draft_raw_attack(903, 'propagate draft', status='draft', is_alm=True))
        mock_get_all.return_value = data

        without = sb_get_playbook_attacks('test-console', test_type='all')
        assert without['validate_count'] + without['propagate_count'] == without['total_attacks'] == 5

        with_drafts = sb_get_playbook_attacks('test-console', test_type='all', include_drafts=True)
        assert (with_drafts['validate_count'] + with_drafts['propagate_count']
                == with_drafts['total_attacks'] == 8)
