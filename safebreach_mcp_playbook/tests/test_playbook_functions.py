"""
Tests for SafeBreach Playbook Functions

This module tests the core business logic functions for playbook operations.
"""

import pytest
import time
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
        
        assert "not found" in str(exc_info.value)
        assert "invalid-console" in str(exc_info.value)
    
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_secret_for_console')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    def test_api_call_success(self, mock_base_url, mock_get_secret, mock_requests_get, sample_attack_data):
        """Test successful API call."""
        # Setup mocks
        mock_base_url.return_value = 'https://test-console.safebreach.com'
        mock_get_secret.return_value = 'test-api-token'
        
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
        assert call_args[1]['headers']['x-apitoken'] == 'test-api-token'
        assert call_args[1]['timeout'] == 120
    
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_secret_for_console')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    def test_api_call_error(self, mock_base_url, mock_get_secret, mock_requests_get):
        """Test API call error handling."""
        # Setup mocks
        mock_base_url.return_value = 'https://test-console.safebreach.com'
        mock_get_secret.return_value = 'test-api-token'
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_requests_get.return_value = mock_response
        
        # Call function and verify error
        with pytest.raises(ValueError) as exc_info:
            _get_all_attacks_from_cache_or_api('test-console')
        
        assert "API call failed with status 500" in str(exc_info.value)
    
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_secret_for_console')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    @patch('safebreach_mcp_playbook.playbook_functions.playbook_cache')
    def test_cache_hit(self, mock_cache, mock_base_url, mock_get_secret, mock_requests_get, sample_attack_data):
        """Test cache hit scenario."""
        # Setup mocks - these shouldn't be called due to cache hit
        mock_base_url.return_value = 'https://test-console.safebreach.com'
        mock_get_secret.return_value = "test-token"
        
        # Setup cache mock to simulate cache hit
        cache_key = "attacks_test-console"
        current_timestamp = time.time()
        cache_data = {
            cache_key: {
                'data': sample_attack_data,
                'timestamp': current_timestamp
            }
        }
        
        # Configure cache mock behaviors
        mock_cache.__contains__ = Mock(side_effect=lambda key: key in cache_data)
        mock_cache.__getitem__ = Mock(side_effect=lambda key: cache_data[key])
        mock_cache.get = Mock(side_effect=lambda key, default=None: cache_data.get(key, default))
        
        # Call function
        result = _get_all_attacks_from_cache_or_api('test-console')
        
        # Verify results
        assert result == sample_attack_data
        
        # Verify no API call was made (cache hit)
        mock_requests_get.assert_not_called()
        mock_get_secret.assert_not_called()
    
    @patch('safebreach_mcp_playbook.playbook_functions.requests.get')
    @patch('safebreach_mcp_playbook.playbook_functions.get_secret_for_console')
    @patch('safebreach_mcp_playbook.playbook_functions.get_api_base_url')
    def test_cache_expired(self, mock_base_url, mock_get_secret, mock_requests_get, sample_attack_data):
        """Test expired cache scenario."""
        # Setup mocks
        mock_base_url.return_value = 'https://test-console.safebreach.com'
        mock_get_secret.return_value = 'test-api-token'
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': sample_attack_data}
        mock_requests_get.return_value = mock_response
        
        # Pre-populate cache with expired timestamp
        cache_key = "attacks_test-console"
        playbook_cache[cache_key] = {
            'data': [],
            'timestamp': time.time() - 7200  # 2 hours ago (expired)
        }
        
        # Call function
        result = _get_all_attacks_from_cache_or_api('test-console')
        
        # Verify results
        assert result == sample_attack_data
        
        # Verify API call was made due to cache expiration
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
        
        result = sb_get_playbook_attacks('test-console', name_filter='DNS')
        
        # Should only return the DNS attack
        assert result['total_attacks'] == 1
        assert len(result['attacks_in_page']) == 1
        assert result['attacks_in_page'][0]['name'] == 'DNS queries of malicious URLs'
        assert result['applied_filters']['name_filter'] == 'DNS'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_description_filter(self, mock_get_all_attacks, sample_attack_data):
        """Test description filtering."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks('test-console', description_filter='HTTP')
        
        # Should only return the HTTP attack
        assert result['total_attacks'] == 1
        assert len(result['attacks_in_page']) == 1
        assert result['attacks_in_page'][0]['name'] == 'File transfer via HTTP'
        assert result['applied_filters']['description_filter'] == 'HTTP'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_id_range_filter(self, mock_get_all_attacks, sample_attack_data):
        """Test ID range filtering."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks('test-console', id_min=2000, id_max=3000)
        
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
        result = sb_get_playbook_attacks('test-console', page_number=0)
        assert result['page_number'] == 0
        assert result['total_pages'] == 3  # 25 attacks / 10 per page = 3 pages
        assert result['total_attacks'] == 25
        assert len(result['attacks_in_page']) == 10
        assert result['attacks_in_page'][0]['id'] == 1
        assert result['attacks_in_page'][9]['id'] == 10
        
        # Test second page
        result = sb_get_playbook_attacks('test-console', page_number=1)
        assert result['page_number'] == 1
        assert len(result['attacks_in_page']) == 10
        assert result['attacks_in_page'][0]['id'] == 11
        assert result['attacks_in_page'][9]['id'] == 20
        
        # Test last page
        result = sb_get_playbook_attacks('test-console', page_number=2)
        assert result['page_number'] == 2
        assert len(result['attacks_in_page']) == 5  # Last page has only 5 items
        assert result['attacks_in_page'][0]['id'] == 21
        assert result['attacks_in_page'][4]['id'] == 25
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_invalid_page_number(self, mock_get_all_attacks, sample_attack_data):
        """Test invalid page number handling."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attacks('test-console', page_number=10)
        
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
        
        result = sb_get_playbook_attacks('test-console', name_filter='NonExistentAttack')
        
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
        
        result = sb_get_playbook_attack_details('test-console', 1027)
        
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
        
        result = sb_get_playbook_attack_details('test-console', 1027, include_fix_suggestions=True)
        
        # Verify fix suggestions are included
        assert result['fix_suggestions'] is not None
        assert len(result['fix_suggestions']) == 1
        assert result['fix_suggestions'][0]['title'] == 'Harden Intrusion Prevention System (IPS) security configuration'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_with_tags(self, mock_get_all_attacks, sample_attack_data):
        """Test including tags."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details('test-console', 1027, include_tags=True)
        
        # Verify tags are included
        assert result['tags'] == ['network', 'dns']
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_with_parameters(self, mock_get_all_attacks, sample_attack_data):
        """Test including parameters."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details('test-console', 1027, include_parameters=True)
        
        # Verify parameters are included
        assert result['params'] is not None
        assert len(result['params']) == 1
        assert result['params'][0]['name'] == 'port'
    
    @patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api')
    def test_all_verbosity_options(self, mock_get_all_attacks, sample_attack_data):
        """Test including all verbosity options."""
        mock_get_all_attacks.return_value = sample_attack_data
        
        result = sb_get_playbook_attack_details(
            'test-console', 
            1027, 
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
            sb_get_playbook_attack_details('test-console', 9999)
        
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
        assert len(playbook_cache) == 0, f"Cache should be empty at start but has: {list(playbook_cache.keys())}"
        
        # Add something to cache
        playbook_cache['test_key'] = {'data': 'test', 'timestamp': time.time()}
        assert len(playbook_cache) == 1, f"Cache should have 1 item but has: {len(playbook_cache)} items: {list(playbook_cache.keys())}"
        
        # Clear cache using the function
        clear_playbook_cache()
        assert len(playbook_cache) == 0, f"Cache should be empty after clear but has: {list(playbook_cache.keys())}"