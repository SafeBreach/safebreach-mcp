"""
DateTime Utilities for SafeBreach MCP

Provides datetime conversion utilities shared across all MCP servers.
"""

from datetime import datetime, timezone as dt_timezone
from typing import Dict, Any
import zoneinfo

def convert_datetime_to_epoch(datetime_str: str) -> Dict[str, Any]:
    """
    Convert ISO format datetime string to Unix epoch timestamp in milliseconds.

    Args:
        datetime_str: ISO format datetime string (e.g., '2024-01-15T10:30:00Z', '2024-01-15T10:30:00+00:00')

    Returns:
        Dict containing the epoch timestamp in milliseconds and parsed datetime information.
        The milliseconds format matches SafeBreach API expectations for date filtering.
    """
    try:
        # Handle different ISO datetime formats
        if datetime_str.endswith('Z'):
            # Replace Z with +00:00 for proper parsing
            datetime_str = datetime_str[:-1] + '+00:00'

        # Parse the datetime string
        dt = datetime.fromisoformat(datetime_str)

        # Convert to epoch timestamp in milliseconds (SafeBreach API format)
        epoch_timestamp_ms = int(dt.timestamp() * 1000)

        return {
            "epoch_timestamp": epoch_timestamp_ms,
            "unit": "milliseconds",
            "original_datetime": datetime_str,
            "parsed_datetime": dt.isoformat(),
            "human_readable": dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "timezone": str(dt.tzinfo) if dt.tzinfo else "No timezone info"
        }
    except ValueError as e:
        return {
            "error": f"Invalid datetime format: {str(e)}",
            "expected_format": "ISO format like '2024-01-15T10:30:00Z' or '2024-01-15T10:30:00+00:00'",
            "provided_datetime": datetime_str
        }
    except (TypeError, AttributeError) as e:
        return {
            "error": f"Datetime processing error: {str(e)}",
            "provided_datetime": datetime_str
        }

def convert_epoch_to_datetime(epoch_timestamp: int, timezone: str = "UTC") -> Dict[str, Any]:
    """
    Convert Unix epoch timestamp to ISO format datetime string.

    Args:
        epoch_timestamp: Unix timestamp as integer. Accepts both milliseconds (SafeBreach API format)
                        and seconds. Timestamps > 10^12 are auto-detected as milliseconds.
        timezone: Timezone for output (default: 'UTC').
                 Supports IANA timezone names (e.g., 'America/New_York', 'Europe/London')
                 or 'UTC' for UTC timezone.

    Returns:
        Dict containing the ISO datetime string and formatted information
    """
    try:
        # Validate timezone parameter first
        if timezone == "UTC":
            tz = dt_timezone.utc
        else:
            try:
                # Try to get the timezone using zoneinfo (IANA timezone database)
                tz = zoneinfo.ZoneInfo(timezone)
            except zoneinfo.ZoneInfoNotFoundError:
                # Invalid timezone name
                return {
                    "error": f"Invalid timezone '{timezone}'. Please use IANA timezone names like 'America/New_York', 'Europe/London', or 'UTC'.",
                    "provided_timezone": timezone,
                    "provided_timestamp": epoch_timestamp,
                    "examples": ["UTC", "America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Tokyo"]
                }

        # Auto-detect milliseconds vs seconds
        # Timestamps after year 2001 in milliseconds are > 10^12
        # Timestamps in seconds won't exceed 10^12 until year 33658
        original_timestamp = epoch_timestamp
        input_unit = "milliseconds"
        if epoch_timestamp > 10**12:
            # Input is in milliseconds, convert to seconds for datetime
            epoch_timestamp_seconds = epoch_timestamp / 1000
            input_unit = "milliseconds"
        else:
            # Input is in seconds
            epoch_timestamp_seconds = epoch_timestamp
            input_unit = "seconds"

        # Convert epoch to datetime with proper timezone
        dt = datetime.fromtimestamp(epoch_timestamp_seconds, tz=tz)
        
        # Format ISO datetime string
        iso_datetime = dt.isoformat()
        
        # Replace timezone info with Z for UTC for consistency
        if timezone == "UTC":
            iso_datetime = iso_datetime.replace('+00:00', 'Z')
            if not iso_datetime.endswith('Z'):
                iso_datetime += 'Z'
        
        # Get timezone abbreviation and offset information
        timezone_abbr = dt.strftime('%Z')  # e.g., 'EST', 'PDT', 'UTC'
        timezone_offset = dt.strftime('%z')  # e.g., '-0500', '+0000'
        
        # Format offset for human readability (e.g., '-05:00')
        if len(timezone_offset) == 5:
            formatted_offset = f"{timezone_offset[:3]}:{timezone_offset[3:]}"
        else:
            formatted_offset = timezone_offset
        
        return {
            "iso_datetime": iso_datetime,
            "human_readable": dt.strftime("%Y-%m-%d %H:%M:%S %Z") if timezone != "UTC" else dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "epoch_timestamp": original_timestamp,
            "input_unit": input_unit,
            "timezone": timezone,
            "timezone_abbreviation": timezone_abbr,
            "timezone_offset": formatted_offset,
            "date_only": dt.strftime("%Y-%m-%d"),
            "time_only": dt.strftime("%H:%M:%S")
        }
    except (ValueError, OSError) as e:
        return {
            "error": f"Invalid epoch timestamp: {str(e)}",
            "provided_timestamp": epoch_timestamp,
            "expected_format": "Unix timestamp as integer (milliseconds or seconds since 1970-01-01)"
        }
    except (TypeError, AttributeError) as e:
        return {
            "error": f"Timestamp processing error: {str(e)}",
            "provided_timestamp": epoch_timestamp
        }