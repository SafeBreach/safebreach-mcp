"""
SafeBreach Playbook Functions

This module provides functions for SafeBreach playbook operations,
specifically for accessing playbook attack data and details.
"""

import logging
from typing import Dict, List, Optional, Any

import requests
from safebreach_mcp_core.cache_config import is_caching_enabled
from safebreach_mcp_core.safebreach_cache import SafeBreachCache
from safebreach_mcp_core.secret_utils import get_secret_for_console, get_auth_headers_for_console, check_rbac_response
from safebreach_mcp_core.token_context import get_cache_user_suffix
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from safebreach_mcp_core.rate_limiter import rate_limiter, get_caller_identity
from .playbook_types import (
    transform_reduced_playbook_attack,
    transform_full_playbook_attack,
    filter_attacks_by_criteria,
    paginate_attacks,
    _extract_custom_tag_values
)

logger = logging.getLogger(__name__)

# Bounded cache for playbook data: max 5 consoles, 30-minute TTL
playbook_cache = SafeBreachCache(name="playbook_attacks", maxsize=5, ttl=1800)

# Configuration constants
PAGE_SIZE = 10


def _get_all_attacks_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """
    Get all attacks for a console from cache or API.

    Args:
        console: SafeBreach console name

    Returns:
        List of all attacks for the console

    Raises:
        ValueError: If console is not found or API call fails
    """

    # Check cache first (only if caching is enabled)
    cache_key = f"attacks_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("playbook"):
        cached = playbook_cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for console %s playbook attacks", console)
            return cached

    # Cache miss - fetch from API
    logger.info("Cache miss for console %s playbook attacks - fetching from API", console)

    try:
        # Get environment info
        base_url = get_api_base_url(console, 'playbook')

        # Make API call
        headers = {
            "Content-Type": "application/json",
            **get_auth_headers_for_console(console)
        }

        url = f"{base_url}/api/kb/vLatest/moves?details=true"
        logger.info(f"Making API call to {url}")
        response = requests.get(url, headers=headers, timeout=120)

        if response.status_code != 200:
            raise ValueError(f"API call failed with status {response.status_code}: {response.text}")

        response_data = response.json()

        if 'data' not in response_data:
            raise ValueError("API response missing 'data' field")

        attacks_data = response_data['data']

        # Cache the results (only if caching is enabled)
        if is_caching_enabled("playbook"):
            playbook_cache.set(cache_key, attacks_data)
            logger.info("Successfully cached %d attacks for console %s", len(attacks_data), console)
        return attacks_data

    except requests.RequestException as e:
        logger.error("Network error fetching playbook attacks for console %s: %s", console, e)
        raise ValueError(f"Failed to fetch playbook attacks: {str(e)}") from e
    except Exception as e:
        logger.error("Error fetching playbook attacks for console %s: %s", console, e)
        raise ValueError(f"Failed to fetch playbook attacks: {str(e)}") from e


def sb_get_playbook_attacks(
    console: str = "default",
    page_number: int = 0,
    name_filter: Optional[str] = None,
    description_filter: Optional[str] = None,
    id_min: Optional[int] = None,
    id_max: Optional[int] = None,
    modified_date_start: Optional[str] = None,
    modified_date_end: Optional[str] = None,
    published_date_start: Optional[str] = None,
    published_date_end: Optional[str] = None,
    include_mitre_techniques: bool = False,
    mitre_technique_filter: Optional[str] = None,
    mitre_tactic_filter: Optional[str] = None,
    attacker_platform_filter: Optional[str] = None,
    target_platform_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get filtered and paginated playbook attacks.

    Args:
        console: SafeBreach console name
        page_number: Page number (0-based)
        name_filter: Partial match on attack name (case-insensitive)
        description_filter: Partial match on attack description (case-insensitive)
        id_min: Minimum attack ID (inclusive)
        id_max: Maximum attack ID (inclusive)
        modified_date_start: Start date for modified date range (ISO format)
        modified_date_end: End date for modified date range (ISO format)
        published_date_start: Start date for published date range (ISO format)
        published_date_end: End date for published date range (ISO format)
        include_mitre_techniques: Whether to include MITRE ATT&CK data
        mitre_technique_filter: Comma-separated technique IDs/names (OR, case-insensitive partial)
        mitre_tactic_filter: Comma-separated tactic names (OR, case-insensitive partial)
        attacker_platform_filter: Comma-separated platform values (OR, case-insensitive partial). None passes through.
        target_platform_filter: Comma-separated platform values (OR, case-insensitive partial). None passes through.

    Returns:
        Dict containing paginated attacks and metadata

    Raises:
        ValueError: If console is not found or parameters are invalid
    """
    # Validate ID range - id_min should be less than or equal to id_max
    if id_min is not None and id_max is not None and id_min > id_max:
        raise ValueError(f"Invalid ID range: id_min ({id_min}) must be less than or equal to id_max ({id_max})")
    
    # Validate page_number parameter
    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")
    
    # Validate date ranges - start dates should be before end dates
    if modified_date_start is not None and modified_date_end is not None and modified_date_start > modified_date_end:
        raise ValueError(f"Invalid modified date range: modified_date_start ({modified_date_start}) must be before or equal to modified_date_end ({modified_date_end})")
    
    if published_date_start is not None and published_date_end is not None and published_date_start > published_date_end:
        raise ValueError(f"Invalid published date range: published_date_start ({published_date_start}) must be before or equal to published_date_end ({published_date_end})")
    
    try:
        # Get all attacks from cache or API
        all_attacks = _get_all_attacks_from_cache_or_api(console)

        # Auto-enable MITRE when filters need it
        needs_mitre = include_mitre_techniques or bool(mitre_technique_filter) or bool(mitre_tactic_filter)

        # Transform to reduced format
        reduced_attacks = [
            transform_reduced_playbook_attack(attack, include_mitre_techniques=needs_mitre)
            for attack in all_attacks
        ]

        # Apply filters
        filtered_attacks = filter_attacks_by_criteria(
            reduced_attacks,
            name_filter=name_filter,
            description_filter=description_filter,
            id_min=id_min,
            id_max=id_max,
            modified_date_start=modified_date_start,
            modified_date_end=modified_date_end,
            published_date_start=published_date_start,
            published_date_end=published_date_end,
            mitre_technique_filter=mitre_technique_filter,
            mitre_tactic_filter=mitre_tactic_filter,
            attacker_platform_filter=attacker_platform_filter,
            target_platform_filter=target_platform_filter
        )

        # Paginate results
        paginated_result = paginate_attacks(filtered_attacks, page_number, PAGE_SIZE)

        # Add applied filters info
        applied_filters = {}
        if name_filter:
            applied_filters['name_filter'] = name_filter
        if description_filter:
            applied_filters['description_filter'] = description_filter
        if id_min is not None:
            applied_filters['id_min'] = id_min
        if id_max is not None:
            applied_filters['id_max'] = id_max
        if modified_date_start:
            applied_filters['modified_date_start'] = modified_date_start
        if modified_date_end:
            applied_filters['modified_date_end'] = modified_date_end
        if published_date_start:
            applied_filters['published_date_start'] = published_date_start
        if published_date_end:
            applied_filters['published_date_end'] = published_date_end
        if mitre_technique_filter:
            applied_filters['mitre_technique_filter'] = mitre_technique_filter
        if mitre_tactic_filter:
            applied_filters['mitre_tactic_filter'] = mitre_tactic_filter
        if attacker_platform_filter:
            applied_filters['attacker_platform_filter'] = attacker_platform_filter
        if target_platform_filter:
            applied_filters['target_platform_filter'] = target_platform_filter

        paginated_result['applied_filters'] = applied_filters

        return paginated_result

    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected error in sb_get_playbook_attacks: %s", e)
        raise ValueError(f"Failed to get playbook attacks: {str(e)}") from e


def sb_get_playbook_attack_details(
    attack_id: int,
    console: str = "default",
    include_fix_suggestions: bool = False,
    include_tags: bool = False,
    include_parameters: bool = False,
    include_mitre_techniques: bool = False
) -> Dict[str, Any]:
    """
    Get detailed information for a specific playbook attack.

    Args:
        console: SafeBreach console name
        attack_id: Attack ID to get details for
        include_fix_suggestions: Whether to include fix suggestions
        include_tags: Whether to include tags
        include_parameters: Whether to include parameters
        include_mitre_techniques: Whether to include MITRE ATT&CK data

    Returns:
        Dict containing detailed attack information

    Raises:
        ValueError: If console or attack is not found
    """
    try:
        # Get all attacks from cache or API
        all_attacks = _get_all_attacks_from_cache_or_api(console)

        # Find the specific attack
        attack_data = None
        for attack in all_attacks:
            if attack.get('id') == attack_id:
                attack_data = attack
                break

        if attack_data is None:
            # Get available IDs for error message
            available_ids = [str(attack.get('id', 'unknown')) for attack in all_attacks[:10]]
            if len(all_attacks) > 10:
                available_ids.append('...')
            raise ValueError(
                f"Attack with ID {attack_id} not found. "
                f"Available IDs include: {', '.join(available_ids)}"
            )

        # Transform to full format with verbosity options
        detailed_attack = transform_full_playbook_attack(
            attack_data,
            include_fix_suggestions=include_fix_suggestions,
            include_tags=include_tags,
            include_parameters=include_parameters,
            include_mitre_techniques=include_mitre_techniques
        )

        return detailed_attack

    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected error in sb_get_playbook_attack_details: %s", e)
        raise ValueError(f"Failed to get attack details: {str(e)}") from e


def sb_get_playbook_attacks_by_tags(
    console: str = "default",
    tags: Optional[str] = None,
    page_number: int = 0
) -> Dict[str, Any]:
    """
    Get playbook attacks filtered by one or more custom tags.

    Args:
        console: SafeBreach console name
        tags: Comma-separated tag values (OR logic, case-insensitive exact match per tag token)
        page_number: Page number (0-based)

    Returns:
        Dict containing paginated attacks (each carrying its `tags` list) and metadata

    Raises:
        ValueError: If no tags are provided, page_number is negative, or the API call fails
    """
    # Validate tags - at least one non-empty tag is required (single-purpose tool)
    if not tags or not [v for v in tags.split(',') if v.strip()]:
        raise ValueError("At least one tag must be provided in 'tags' (comma-separated).")

    # Validate page_number parameter
    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")

    try:
        # Get all attacks from cache or API
        all_attacks = _get_all_attacks_from_cache_or_api(console)

        # Transform to reduced format, exposing the normalized tags for filtering
        reduced_attacks = [
            transform_reduced_playbook_attack(attack, include_tags=True)
            for attack in all_attacks
        ]

        # Apply the tag filter
        filtered_attacks = filter_attacks_by_criteria(reduced_attacks, tag_filter=tags)

        # Paginate results
        paginated_result = paginate_attacks(filtered_attacks, page_number, PAGE_SIZE)
        paginated_result['applied_filters'] = {'tags': tags}

        return paginated_result

    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected error in sb_get_playbook_attacks_by_tags: %s", e)
        raise ValueError(f"Failed to get playbook attacks by tags: {str(e)}") from e


def _build_move_tags_request(console: str, attack_id: int):
    """Build the (url, headers, account_id) for a single-move tags write request."""
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    url = f"{base_url}/api/content/v3/accounts/{account_id}/moves/{attack_id}/tags"
    headers = {
        "Content-Type": "application/json",
        **get_auth_headers_for_console(console)
    }
    return url, headers


def sb_add_playbook_attack_tag(
    console: str = "default",
    attack_id: int = None,
    tag_value: str = None
) -> Dict[str, Any]:
    """
    Add a custom tag to a single playbook attack (move).

    Args:
        console: SafeBreach console name
        attack_id: Playbook attack (move) ID
        tag_value: Single tag value to add

    Returns:
        Dict with the action result and a hint_to_agent

    Raises:
        ValueError: If tag_value is empty/missing
        PermissionError / HTTPError: If the backend rejects the write
    """
    if not tag_value or not str(tag_value).strip():
        raise ValueError("A non-empty 'tag_value' is required.")

    url, headers = _build_move_tags_request(console, attack_id)
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "add_playbook_attack_tag")

    response = requests.post(url, headers=headers, json={"values": [tag_value]}, timeout=120)
    check_rbac_response(response)

    clear_playbook_cache()
    rate_limiter.record_action(caller_id, "add_playbook_attack_tag")

    return {
        "success": True,
        "attack_id": attack_id,
        "tag_value": tag_value,
        "action": "added",
        "hint_to_agent": f"Tag '{tag_value}' added to playbook attack {attack_id}."
    }


def sb_remove_playbook_attack_tag(
    console: str = "default",
    attack_id: int = None,
    tag_value: str = None
) -> Dict[str, Any]:
    """
    Remove a custom tag from a single playbook attack (move).

    Args:
        console: SafeBreach console name
        attack_id: Playbook attack (move) ID
        tag_value: Single tag value to remove

    Returns:
        Dict with the action result and a hint_to_agent

    Raises:
        ValueError: If tag_value is empty/missing
        PermissionError / HTTPError: If the backend rejects the write
    """
    if not tag_value or not str(tag_value).strip():
        raise ValueError("A non-empty 'tag_value' is required.")

    url, headers = _build_move_tags_request(console, attack_id)
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "remove_playbook_attack_tag")

    response = requests.delete(url, headers=headers, params={"values": tag_value}, timeout=120)
    check_rbac_response(response)

    clear_playbook_cache()
    rate_limiter.record_action(caller_id, "remove_playbook_attack_tag")

    return {
        "success": True,
        "attack_id": attack_id,
        "tag_value": tag_value,
        "action": "removed",
        "hint_to_agent": f"Tag '{tag_value}' removed from playbook attack {attack_id}."
    }


def sb_rename_playbook_attack_tag(
    console: str = "default",
    attack_id: int = None,
    old_value: str = None,
    new_value: str = None
) -> Dict[str, Any]:
    """
    Rename a custom tag on a single playbook attack (move).

    Args:
        console: SafeBreach console name
        attack_id: Playbook attack (move) ID
        old_value: Existing tag value
        new_value: New tag value

    Returns:
        Dict with the action result and a hint_to_agent

    Raises:
        ValueError: If either value is empty/missing, or if old_value == new_value (no-op)
        PermissionError / HTTPError: If the backend rejects the write
    """
    if not old_value or not str(old_value).strip():
        raise ValueError("A non-empty 'old_value' is required.")
    if not new_value or not str(new_value).strip():
        raise ValueError("A non-empty 'new_value' is required.")
    if old_value == new_value:
        raise ValueError("'old_value' and 'new_value' must differ (no-op rename).")

    url, headers = _build_move_tags_request(console, attack_id)
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "rename_playbook_attack_tag")

    response = requests.put(url, headers=headers, json={"oldValue": old_value, "newValue": new_value}, timeout=120)
    check_rbac_response(response)

    clear_playbook_cache()
    rate_limiter.record_action(caller_id, "rename_playbook_attack_tag")

    return {
        "success": True,
        "attack_id": attack_id,
        "old_value": old_value,
        "new_value": new_value,
        "action": "renamed",
        "hint_to_agent": f"Tag '{old_value}' renamed to '{new_value}' on playbook attack {attack_id}."
    }


def sb_get_playbook_attack_tags(
    console: str = "default",
    attack_id: int = None
) -> Dict[str, Any]:
    """
    Retrieve the custom tags on a single playbook attack (SAF-29870 req 3).

    Args:
        console: SafeBreach console name
        attack_id: Playbook attack (move) ID

    Returns:
        Dict with the attack id and its list of custom tag values

    Raises:
        ValueError: If attack_id is missing or the attack is not found
    """
    if attack_id is None:
        raise ValueError("'attack_id' is required.")

    all_attacks = _get_all_attacks_from_cache_or_api(console)
    match = next((a for a in all_attacks if a.get('id') == attack_id), None)
    if match is None:
        raise ValueError(f"Attack with ID {attack_id} not found.")

    tags = _extract_custom_tag_values(match.get('tags', []))
    return {
        "attack_id": attack_id,
        "tags": tags,
        "hint_to_agent": (f"Attack {attack_id} has {len(tags)} custom tag(s)."
                          if tags else f"Attack {attack_id} has no custom tags.")
    }


# ---- Bulk tag operations (SAF-29870 req 4) -------------------------------- #
# Guardrails (non-functional req): hard caps so a bulk op cannot overload/crash the console or Helm.
MAX_BULK_ATTACK_IDS = 50
MAX_BULK_TAG_VALUES = 20


def _parse_bulk_attack_ids(attack_ids) -> List[int]:
    """Parse+validate attack ids (comma-separated string or list) into a capped list of ints."""
    if attack_ids is None:
        raw = []
    elif isinstance(attack_ids, (list, tuple)):
        raw = list(attack_ids)
    else:
        raw = [x.strip() for x in str(attack_ids).split(',') if str(x).strip()]

    ids = []
    for x in raw:
        try:
            ids.append(int(x))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid attack id '{x}' — attack ids must be integers.") from e

    if not ids:
        raise ValueError("At least one attack id must be provided.")
    if len(ids) > MAX_BULK_ATTACK_IDS:
        raise ValueError(
            f"Too many attack ids ({len(ids)}); max {MAX_BULK_ATTACK_IDS} per bulk call (guardrail).")
    return ids


def _parse_bulk_tag_values(tag_values) -> List[str]:
    """Parse+validate tag values (comma-separated string or list) into a capped list of strings."""
    if tag_values is None:
        vals = []
    elif isinstance(tag_values, (list, tuple)):
        vals = [str(v).strip() for v in tag_values if str(v).strip()]
    else:
        vals = [v.strip() for v in str(tag_values).split(',') if v.strip()]

    if not vals:
        raise ValueError("At least one tag value must be provided.")
    if len(vals) > MAX_BULK_TAG_VALUES:
        raise ValueError(
            f"Too many tag values ({len(vals)}); max {MAX_BULK_TAG_VALUES} per bulk call (guardrail).")
    return vals


def _bulk_tags_request(console: str):
    """Build the (url, headers) for the bulk move-tags endpoint."""
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    url = f"{base_url}/api/content/v3/accounts/{account_id}/moves/tags"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}
    return url, headers


def _bulk_result_summary(response, attack_ids: List[int], action: str, **extra) -> Dict[str, Any]:
    """
    Summarize a bulk response. The backend returns per-move results (fulfilled / {status:'rejected'})
    nested as {"data": {"results": [...]}} (with fallbacks for a bare list or top-level {"results": [...]}).
    """
    try:
        data = response.json()
    except Exception:  # noqa: BLE001 - defensive; some backends return empty body
        data = None

    results = None
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        inner = data.get('data')
        if isinstance(inner, dict) and isinstance(inner.get('results'), list):
            results = inner['results']
        elif isinstance(data.get('results'), list):
            results = data['results']

    failures = []
    succeeded = None
    if isinstance(results, list):
        failures = [r for r in results if isinstance(r, dict) and r.get('status') == 'rejected']
        succeeded = len(results) - len(failures)

    out = {
        "success": True,
        "action": action,
        "attack_ids": attack_ids,
        "succeeded": succeeded,
        "failed_count": len(failures),
        "failures": failures,
        "hint_to_agent": (f"{action}: {succeeded} succeeded, {len(failures)} failed."
                          if succeeded is not None else f"{action} submitted for {len(attack_ids)} attack(s).")
    }
    out.update(extra)
    return out


def sb_bulk_add_playbook_attack_tags(
    console: str = "default",
    attack_ids=None,
    tag_values=None
) -> Dict[str, Any]:
    """Add one or more custom tags to one or more playbook attacks (bulk). Covers all three modes."""
    ids = _parse_bulk_attack_ids(attack_ids)
    vals = _parse_bulk_tag_values(tag_values)

    url, headers = _bulk_tags_request(console)
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "bulk_add_playbook_attack_tags")

    response = requests.post(url, headers=headers, json={"moveIds": ids, "values": vals}, timeout=120)
    check_rbac_response(response)

    clear_playbook_cache()
    rate_limiter.record_action(caller_id, "bulk_add_playbook_attack_tags")
    return _bulk_result_summary(response, ids, "bulk_added", tag_values=vals)


def sb_bulk_remove_playbook_attack_tags(
    console: str = "default",
    attack_ids=None,
    tag_values=None
) -> Dict[str, Any]:
    """Remove one or more custom tags from one or more playbook attacks (bulk)."""
    ids = _parse_bulk_attack_ids(attack_ids)
    vals = _parse_bulk_tag_values(tag_values)

    url, headers = _bulk_tags_request(console)
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "bulk_remove_playbook_attack_tags")

    # collectionFormat=pipes for both query arrays
    params = {"moveIds": "|".join(str(i) for i in ids), "values": "|".join(vals)}
    response = requests.delete(url, headers=headers, params=params, timeout=120)
    check_rbac_response(response)

    clear_playbook_cache()
    rate_limiter.record_action(caller_id, "bulk_remove_playbook_attack_tags")
    return _bulk_result_summary(response, ids, "bulk_removed", tag_values=vals)


def sb_bulk_rename_playbook_attack_tag(
    console: str = "default",
    attack_ids=None,
    old_value: str = None,
    new_value: str = None
) -> Dict[str, Any]:
    """Rename a custom tag (old_value -> new_value) across one or more playbook attacks (bulk)."""
    ids = _parse_bulk_attack_ids(attack_ids)
    if not old_value or not str(old_value).strip():
        raise ValueError("A non-empty 'old_value' is required.")
    if not new_value or not str(new_value).strip():
        raise ValueError("A non-empty 'new_value' is required.")
    if old_value == new_value:
        raise ValueError("'old_value' and 'new_value' must differ (no-op rename).")

    url, headers = _bulk_tags_request(console)
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "bulk_rename_playbook_attack_tag")

    response = requests.put(url, headers=headers,
                            json={"moveIds": ids, "oldValue": old_value, "newValue": new_value}, timeout=120)
    check_rbac_response(response)

    clear_playbook_cache()
    rate_limiter.record_action(caller_id, "bulk_rename_playbook_attack_tag")
    return _bulk_result_summary(response, ids, "bulk_renamed", old_value=old_value, new_value=new_value)


def clear_playbook_cache():
    """Clear all playbook caches. Useful for testing."""
    playbook_cache.clear()
    logger.info("Playbook cache cleared")

