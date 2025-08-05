"""
Test QA bug fixes for playbook functions
"""

import pytest
from unittest.mock import patch
from safebreach_mcp_playbook.playbook_functions import sb_get_playbook_attacks


class TestPlaybookQAFixes:
    """Test QA bug fixes for playbook functions."""
    
    def test_sb_get_playbook_attacks_id_range_validation(self):
        """Test ID range validation in get_playbook_attacks (Bug #10)."""
        
        # Test valid range (should not raise exception)
        with patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api') as mock_get_attacks:
            mock_get_attacks.return_value = []
            try:
                result = sb_get_playbook_attacks("demo-console", id_min=100, id_max=200)
                # Should succeed - no exception expected
            except ValueError:
                pytest.fail("Valid ID range should not raise ValueError")
        
        # Test invalid range (min > max)
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attacks("demo-console", id_min=200, id_max=100)
        assert "Invalid ID range" in str(exc_info.value)
        assert "id_min (200) must be less than or equal to id_max (100)" in str(exc_info.value)
    
    def test_sb_get_playbook_attacks_date_range_validation(self):
        """Test date range validation in get_playbook_attacks (Bug #9)."""
        
        # Test valid modified date range (should not raise exception)
        with patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api') as mock_get_attacks:
            mock_get_attacks.return_value = []
            try:
                result = sb_get_playbook_attacks("demo-console", modified_date_start="2022-01-01", modified_date_end="2022-12-31")
                # Should succeed - no exception expected
            except ValueError:
                pytest.fail("Valid modified date range should not raise ValueError")
        
        # Test invalid modified date range (start > end)
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attacks("demo-console", modified_date_start="2022-12-31", modified_date_end="2022-01-01")
        assert "Invalid modified date range" in str(exc_info.value)
        assert "modified_date_start (2022-12-31) must be before or equal to modified_date_end (2022-01-01)" in str(exc_info.value)
        
        # Test valid published date range (should not raise exception)
        with patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api') as mock_get_attacks:
            mock_get_attacks.return_value = []
            try:
                result = sb_get_playbook_attacks("demo-console", published_date_start="2022-01-01", published_date_end="2022-12-31")
                # Should succeed - no exception expected
            except ValueError:
                pytest.fail("Valid published date range should not raise ValueError")
        
        # Test invalid published date range (start > end)
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attacks("demo-console", published_date_start="2022-12-31", published_date_end="2022-01-01")
        assert "Invalid published date range" in str(exc_info.value)
        assert "published_date_start (2022-12-31) must be before or equal to published_date_end (2022-01-01)" in str(exc_info.value)
    
    def test_sb_get_playbook_attacks_page_number_validation(self):
        """Test page number validation in get_playbook_attacks."""
        
        # Test valid page number (should not raise exception)
        with patch('safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api') as mock_get_attacks:
            mock_get_attacks.return_value = []
            try:
                result = sb_get_playbook_attacks("demo-console", page_number=0)
                # Should succeed - no exception expected
            except ValueError:
                pytest.fail("Valid page number should not raise ValueError")
        
        # Test invalid page number (negative)
        with pytest.raises(ValueError) as exc_info:
            sb_get_playbook_attacks("demo-console", page_number=-1)
        assert "Invalid page_number parameter" in str(exc_info.value)
        assert "Page number must be non-negative" in str(exc_info.value)