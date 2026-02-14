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
        assert "unit" in result
        assert result["unit"] == "milliseconds"
        assert isinstance(result["epoch_timestamp"], int)
        # Verify it's in milliseconds (should be > 10^12 for dates after 2001)
        assert result["epoch_timestamp"] > 10**12

        # Test with +00:00 timezone
        result = convert_datetime_to_epoch("2024-01-15T10:30:00+00:00")
        assert "epoch_timestamp" in result
        assert isinstance(result["epoch_timestamp"], int)
        assert result["epoch_timestamp"] > 10**12

        # Test with different timezone
        result = convert_datetime_to_epoch("2024-01-15T10:30:00-05:00")
        assert "epoch_timestamp" in result
        assert isinstance(result["epoch_timestamp"], int)
        assert result["epoch_timestamp"] > 10**12
    
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
        # Test with UTC timezone (default) - using seconds (auto-detected)
        timestamp_seconds = 1705314600  # 2024-01-15T10:30:00Z in seconds
        result = convert_epoch_to_datetime(timestamp_seconds)
        assert "iso_datetime" in result
        assert "human_readable" in result
        assert "epoch_timestamp" in result
        assert "input_unit" in result
        assert "timezone" in result
        assert "date_only" in result
        assert "time_only" in result
        assert result["epoch_timestamp"] == timestamp_seconds
        assert result["input_unit"] == "seconds"
        assert result["timezone"] == "UTC"
        assert result["iso_datetime"].endswith("Z")

        # Test with milliseconds input (SafeBreach API format)
        timestamp_ms = 1705314600000  # 2024-01-15T10:30:00Z in milliseconds
        result = convert_epoch_to_datetime(timestamp_ms)
        assert result["epoch_timestamp"] == timestamp_ms
        assert result["input_unit"] == "milliseconds"
        assert result["iso_datetime"].endswith("Z")
        assert "2024-01-15T10:30:00" in result["iso_datetime"]

        # Test with custom timezone
        result = convert_epoch_to_datetime(timestamp_seconds, timezone="EST")
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

        # Convert to epoch (returns milliseconds)
        epoch_result = convert_datetime_to_epoch(original_datetime)
        assert "epoch_timestamp" in epoch_result
        assert epoch_result["unit"] == "milliseconds"

        # Convert back to datetime (auto-detects milliseconds)
        datetime_result = convert_epoch_to_datetime(epoch_result["epoch_timestamp"])
        assert "iso_datetime" in datetime_result
        assert datetime_result["input_unit"] == "milliseconds"

        # Should be exactly the same datetime
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
    
    def test_timezone_conversion_america_new_york(self):
        """Test timezone conversion with America/New_York timezone."""
        # Test January (EST) - should be UTC-5
        timestamp_jan = 1640995200  # 2022-01-01 00:00:00 UTC
        result = convert_epoch_to_datetime(timestamp_jan, "America/New_York")
        
        assert result["timezone"] == "America/New_York"
        assert result["timezone_abbreviation"] == "EST"
        assert result["timezone_offset"] == "-05:00"
        assert "2021-12-31T19:00:00-05:00" == result["iso_datetime"]
        assert "EST" in result["human_readable"]
        assert "2021-12-31 19:00:00 EST" == result["human_readable"]
        
        # Test July (EDT) - should be UTC-4
        timestamp_july = 1657584000  # 2022-07-12 00:00:00 UTC 
        result = convert_epoch_to_datetime(timestamp_july, "America/New_York")
        
        assert result["timezone"] == "America/New_York"
        assert result["timezone_abbreviation"] == "EDT"
        assert result["timezone_offset"] == "-04:00"
        assert "2022-07-11T20:00:00-04:00" == result["iso_datetime"]
        assert "EDT" in result["human_readable"]
    
    def test_timezone_conversion_europe_london(self):
        """Test timezone conversion with Europe/London timezone."""
        # Test January (GMT) - should be UTC+0
        timestamp_jan = 1640995200  # 2022-01-01 00:00:00 UTC
        result = convert_epoch_to_datetime(timestamp_jan, "Europe/London")
        
        assert result["timezone"] == "Europe/London"
        assert result["timezone_abbreviation"] == "GMT"
        assert result["timezone_offset"] == "+00:00"
        assert "2022-01-01T00:00:00+00:00" == result["iso_datetime"]
        
        # Test July (BST) - should be UTC+1
        timestamp_july = 1657584000  # 2022-07-12 00:00:00 UTC
        result = convert_epoch_to_datetime(timestamp_july, "Europe/London")
        
        assert result["timezone"] == "Europe/London"
        assert result["timezone_abbreviation"] == "BST"
        assert result["timezone_offset"] == "+01:00"
        assert "2022-07-12T01:00:00+01:00" == result["iso_datetime"]
    
    def test_timezone_conversion_invalid_timezone(self):
        """Test timezone conversion with invalid timezone names."""
        timestamp = 1640995200  # 2022-01-01 00:00:00 UTC
        
        # Test various invalid timezone names
        invalid_timezones = [
            "Invalid/Timezone",
            "BadTimeZone", 
            "America/InvalidCity",
            "NonExistent/Zone",
            "FakeZone/Fake"  # This should definitely be invalid
        ]
        
        for invalid_tz in invalid_timezones:
            result = convert_epoch_to_datetime(timestamp, invalid_tz)
            assert "error" in result
            assert f"Invalid timezone '{invalid_tz}'" in result["error"]
            assert "provided_timezone" in result
            assert result["provided_timezone"] == invalid_tz
            assert "examples" in result
            assert "America/New_York" in result["examples"]
    
    def test_timezone_conversion_utc_special_case(self):
        """Test that UTC timezone works correctly."""
        timestamp = 1640995200  # 2022-01-01 00:00:00 UTC (in seconds)
        result = convert_epoch_to_datetime(timestamp, "UTC")

        assert result["timezone"] == "UTC"
        assert result["timezone_abbreviation"] == "UTC"
        assert result["timezone_offset"] == "+00:00"
        assert result["iso_datetime"].endswith("Z")
        assert "2022-01-01T00:00:00Z" == result["iso_datetime"]
        assert "UTC" in result["human_readable"]
        assert result["input_unit"] == "seconds"

        # Test with milliseconds input
        timestamp_ms = 1640995200000  # Same in milliseconds
        result_ms = convert_epoch_to_datetime(timestamp_ms, "UTC")
        assert result_ms["input_unit"] == "milliseconds"
        assert result_ms["iso_datetime"] == result["iso_datetime"]
    
    def test_epoch_conversion_precision(self):
        """Test epoch conversion precision."""
        # Test with a known timestamp in seconds for consistency
        test_timestamp_seconds = 1640995200  # 2022-01-01 00:00:00 UTC
        test_timestamp_ms = 1640995200000  # Same in milliseconds

        # Convert seconds to datetime (auto-detected as seconds)
        back_result = convert_epoch_to_datetime(test_timestamp_seconds)
        assert "iso_datetime" in back_result
        assert back_result["epoch_timestamp"] == test_timestamp_seconds
        assert back_result["input_unit"] == "seconds"

        # Convert back to epoch (returns milliseconds now)
        iso_datetime = back_result["iso_datetime"]
        forward_result = convert_datetime_to_epoch(iso_datetime)
        assert "epoch_timestamp" in forward_result
        assert forward_result["unit"] == "milliseconds"

        # Should be the same timestamp but in milliseconds
        assert forward_result["epoch_timestamp"] == test_timestamp_ms

        # Test with milliseconds input
        back_result_ms = convert_epoch_to_datetime(test_timestamp_ms)
        assert back_result_ms["input_unit"] == "milliseconds"
        assert back_result_ms["iso_datetime"] == back_result["iso_datetime"]