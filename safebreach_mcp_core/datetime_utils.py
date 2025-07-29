"""
DateTime Utilities for SafeBreach MCP

Provides datetime conversion utilities shared across all MCP servers.
"""

from datetime import datetime
from typing import Dict, Any

def convert_datetime_to_epoch(datetime_str: str) -> Dict[str, Any]:
    """
    Convert ISO format datetime string to Unix epoch timestamp.
    
    Args:
        datetime_str: ISO format datetime string (e.g., '2024-01-15T10:30:00Z', '2024-01-15T10:30:00+00:00')
    
    Returns:
        Dict containing the epoch timestamp and parsed datetime information
    """
    try:
        # Handle different ISO datetime formats
        if datetime_str.endswith('Z'):
            # Replace Z with +00:00 for proper parsing
            datetime_str = datetime_str[:-1] + '+00:00'
        
        # Parse the datetime string
        dt = datetime.fromisoformat(datetime_str)
        
        # Convert to epoch timestamp
        epoch_timestamp = int(dt.timestamp())
        
        return {
            "epoch_timestamp": epoch_timestamp,
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
        epoch_timestamp: Unix timestamp as integer
        timezone: Timezone for output (default: 'UTC')
    
    Returns:
        Dict containing the ISO datetime string and formatted information
    """
    try:
        # Convert epoch to datetime
        dt = datetime.fromtimestamp(epoch_timestamp, tz=datetime.now().astimezone().tzinfo if timezone != "UTC" else None)
        
        # If UTC is requested, convert to UTC
        if timezone == "UTC":
            from datetime import timezone as tz
            dt = datetime.fromtimestamp(epoch_timestamp, tz.utc)
        
        iso_datetime = dt.isoformat()
        # Replace timezone info with Z for UTC
        if timezone == "UTC":
            iso_datetime = iso_datetime.replace('+00:00', 'Z')
            if not iso_datetime.endswith('Z'):
                iso_datetime += 'Z'
        
        return {
            "iso_datetime": iso_datetime,
            "human_readable": dt.strftime("%Y-%m-%d %H:%M:%S %Z") if timezone != "UTC" else dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "epoch_timestamp": epoch_timestamp,
            "timezone": timezone,
            "date_only": dt.strftime("%Y-%m-%d"),
            "time_only": dt.strftime("%H:%M:%S")
        }
    except (ValueError, OSError) as e:
        return {
            "error": f"Invalid epoch timestamp: {str(e)}",
            "provided_timestamp": epoch_timestamp,
            "expected_format": "Unix timestamp as integer (seconds since 1970-01-01)"
        }
    except (TypeError, AttributeError) as e:
        return {
            "error": f"Timestamp processing error: {str(e)}",
            "provided_timestamp": epoch_timestamp
        }