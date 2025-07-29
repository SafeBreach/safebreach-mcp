"""
Tests for SafeBreach Utilities Server

This module tests the utilities server and datetime conversion functions.
"""

import pytest
from datetime import datetime
from safebreach_mcp_core.datetime_utils import convert_datetime_to_epoch, convert_epoch_to_datetime

class TestDateTimeUtils:
    """Test suite for datetime utility functions."""
    
    def test_convert_datetime_to_epoch_success(self):
        """Test successful datetime to epoch conversion."""
        # Test with Z timezone
        result = convert_datetime_to_epoch("2024-01-15T10:30:00Z")
        assert "epoch_timestamp" in result
        assert "original_datetime" in result
        assert "parsed_datetime" in result
        assert "human_readable" in result
        assert "timezone" in result
        assert isinstance(result["epoch_timestamp"], int)
        
        # Test with +00:00 timezone
        result = convert_datetime_to_epoch("2024-01-15T10:30:00+00:00")
        assert "epoch_timestamp" in result
        assert isinstance(result["epoch_timestamp"], int)
        
        # Test with different timezone
        result = convert_datetime_to_epoch("2024-01-15T10:30:00-05:00")
        assert "epoch_timestamp" in result
        assert isinstance(result["epoch_timestamp"], int)
    
    def test_convert_datetime_to_epoch_invalid_format(self):
        """Test datetime to epoch conversion with invalid format."""
        result = convert_datetime_to_epoch("invalid-datetime")
        assert "error" in result
        assert "Invalid datetime format" in result["error"]
        assert "expected_format" in result
        assert result["provided_datetime"] == "invalid-datetime"
    
    def test_convert_datetime_to_epoch_type_error(self):
        """Test datetime to epoch conversion with type error."""
        result = convert_datetime_to_epoch(None)
        assert "error" in result
        assert "Datetime processing error" in result["error"]
    
    def test_convert_epoch_to_datetime_success(self):
        """Test successful epoch to datetime conversion."""
        # Test with UTC timezone (default)
        timestamp = 1705312200  # 2024-01-15T10:30:00Z
        result = convert_epoch_to_datetime(timestamp)
        assert "iso_datetime" in result
        assert "human_readable" in result
        assert "epoch_timestamp" in result
        assert "timezone" in result
        assert "date_only" in result
        assert "time_only" in result
        assert result["epoch_timestamp"] == timestamp
        assert result["timezone"] == "UTC"
        assert result["iso_datetime"].endswith("Z")
        
        # Test with custom timezone
        result = convert_epoch_to_datetime(timestamp, timezone="EST")
        assert result["timezone"] == "EST"
        assert not result["iso_datetime"].endswith("Z")
    
    def test_convert_epoch_to_datetime_invalid_timestamp(self):
        """Test epoch to datetime conversion with invalid timestamp."""
        # Test with negative timestamp (might be invalid on some systems)
        result = convert_epoch_to_datetime(-999999999999)
        # Result depends on system, but should handle gracefully
        assert "error" in result or "iso_datetime" in result
        
        # Test with extremely large timestamp
        result = convert_epoch_to_datetime(999999999999999)
        assert "error" in result or "iso_datetime" in result
    
    def test_convert_epoch_to_datetime_type_error(self):
        """Test epoch to datetime conversion with type error."""
        result = convert_epoch_to_datetime("invalid")
        assert "error" in result
        assert "Timestamp processing error" in result["error"] or "Invalid epoch timestamp" in result["error"]
    
    def test_round_trip_conversion(self):
        """Test round-trip conversion from datetime to epoch and back."""
        original_datetime = "2024-01-15T10:30:00Z"
        
        # Convert to epoch
        epoch_result = convert_datetime_to_epoch(original_datetime)
        assert "epoch_timestamp" in epoch_result
        
        # Convert back to datetime
        datetime_result = convert_epoch_to_datetime(epoch_result["epoch_timestamp"])
        assert "iso_datetime" in datetime_result
        
        # Should be approximately the same (allowing for precision loss)
        assert datetime_result["iso_datetime"].startswith("2024-01-15T10:30:00")
    
    def test_datetime_parsing_edge_cases(self):
        """Test datetime parsing with various edge cases."""
        # Test leap year
        result = convert_datetime_to_epoch("2024-02-29T12:00:00Z")
        assert "epoch_timestamp" in result
        
        # Test end of year
        result = convert_datetime_to_epoch("2023-12-31T23:59:59Z")
        assert "epoch_timestamp" in result
        
        # Test beginning of year
        result = convert_datetime_to_epoch("2024-01-01T00:00:00Z")
        assert "epoch_timestamp" in result
    
    def test_timezone_handling(self):
        """Test timezone handling in conversions."""
        # Test different timezone formats
        timezones = [
            "2024-01-15T10:30:00Z",
            "2024-01-15T10:30:00+00:00",
            "2024-01-15T10:30:00-05:00",
            "2024-01-15T10:30:00+05:30"
        ]
        
        for tz in timezones:
            result = convert_datetime_to_epoch(tz)
            assert "epoch_timestamp" in result
            assert isinstance(result["epoch_timestamp"], int)
    
    def test_epoch_conversion_precision(self):
        """Test epoch conversion precision."""
        # Test with a known timestamp for consistency
        test_timestamp = 1640995200  # 2022-01-01 00:00:00 UTC
        
        # Convert to datetime
        back_result = convert_epoch_to_datetime(test_timestamp)
        assert "iso_datetime" in back_result
        assert back_result["epoch_timestamp"] == test_timestamp
        
        # Convert back to epoch
        iso_datetime = back_result["iso_datetime"]
        forward_result = convert_datetime_to_epoch(iso_datetime)
        assert "epoch_timestamp" in forward_result
        
        # Should be the same timestamp
        assert forward_result["epoch_timestamp"] == test_timestamp