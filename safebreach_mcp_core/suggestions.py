"""
SafeBreach Execution History Suggestions Helper

Generic, cached helper for fetching execution history suggestions
from the SafeBreach data API. Any MCP server can use this to discover
valid values for data-plane collections (e.g., security_product names).
"""

import logging
import requests
from typing import List, Dict, Any

from .safebreach_cache import SafeBreachCache
from .cache_config import is_caching_enabled
from .secret_utils import get_auth_headers_for_console
from .token_context import get_cache_user_suffix
from .environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)

suggestions_cache = SafeBreachCache(name="suggestions", maxsize=10, ttl=1800)


def _fetch_suggestions_entries(
    console: str,
    collection_name: str,
) -> List[Dict[str, Any]]:
    """Fetch raw suggestion entries (key + doc_count) for a collection.

    Returns cached entries if available.  Each entry is
    ``{"key": "...", "doc_count": N}``.
    """
    cache_key = f"{console}_{collection_name}{get_cache_user_suffix()}"
    if is_caching_enabled("data"):
        cached = suggestions_cache.get(cache_key)
        if cached is not None:
            logger.info("Suggestions cache hit: %s", cache_key)
            return cached

    base_url = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)

    api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistorySuggestions"
    headers = {
        "Content-Type": "application/json",
        **get_auth_headers_for_console(console),
    }

    logger.info("Fetching suggestions from API for console '%s'", console)
    response = requests.get(api_url, headers=headers, timeout=120)

    if response.status_code == 401:
        raise ValueError(
            f"Authentication failed (401) for console '{console}'. "
            "Check API token configuration."
        )

    response.raise_for_status()

    data = response.json()
    completion = data.get("completion", {})

    if collection_name not in completion:
        available = sorted(completion.keys())
        raise ValueError(
            f"Collection '{collection_name}' not found in suggestions response. "
            f"Available collections: {available}"
        )

    entries = [
        item for item in completion[collection_name]
        if isinstance(item.get("key"), str)
    ]

    if is_caching_enabled("data"):
        suggestions_cache.set(cache_key, entries)
        logger.info("Cached suggestions for %s: %d entries", cache_key, len(entries))

    return entries


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
    entries = _fetch_suggestions_entries(console, collection_name)
    return [e["key"] for e in entries]
