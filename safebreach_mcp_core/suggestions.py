"""
SafeBreach Execution History Suggestions Helper

Generic, cached helper for fetching execution history suggestions
from the SafeBreach data API. Any MCP server can use this to discover
valid values for data-plane collections (e.g., security_product names).
"""

import logging
import requests
from typing import List

from .safebreach_cache import SafeBreachCache
from .cache_config import is_caching_enabled
from .secret_utils import get_secret_for_console
from .environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)

suggestions_cache = SafeBreachCache(name="suggestions", maxsize=10, ttl=1800)


def get_suggestions_for_collection(
    console: str,
    collection_name: str,
) -> List[str]:
    """Fetch valid values for a specific data-plane collection.

    Returns a list of string keys from the executionsHistorySuggestions API
    for the requested collection. Results are cached with TTL.

    Args:
        console: SafeBreach console name
        collection_name: Name of the collection (e.g., "security_product")

    Returns:
        List of valid string values for the collection

    Raises:
        ValueError: If collection_name not found in API response
    """
    raise NotImplementedError("TDD stub — implement after tests are written")
