"""
SafeBreach Config Types

This module provides data type mappings and transformations for SafeBreach configuration data,
specifically for simulator entities and related configuration objects.
"""

from typing import Dict, List, Any, Optional

# Mapping for OS version information - EXACT copy from original
reduced_simulator_os_version_mapping = {
    "type": "TYPE",
    "version": "VERSION",
    "release": "RELEASE",
    "architecture": "Arch",
    "domain": "DOMAIN"
}

# Mapping for OS information - EXACT copy from original
reduced_simulator_os_information_mapping = {
        "manufacturer": "Manufacturer",
        "model": "Model",
        "host_name": "Name",
        "status": "Status",
        "isDomainController": "IsDomainController"
}


def map_reduced_entity(entity, mapping):
    """
    Maps the keys of the entity to the new keys defined in the mapping.
    EXACT copy from original safebreach_types.py
    """
    return {new_key: entity[old_key] for new_key, old_key in mapping.items() if old_key in entity}


def get_minimal_simulator_mapping(simulator_entity, assets_map=None):
    """
    Returns a reduced simulator entity with only the relevant fields.
    """
    minimal_os_version = map_reduced_entity(simulator_entity['nodeInfo']['MACHINE_INFO']['OS'], reduced_simulator_os_version_mapping)

    # Role flags — what this simulator can act as
    roles = {}
    for role_key in ['isInfiltration', 'isExfiltration', 'isAWSAttacker',
                     'isAzureAttacker', 'isGCPAttacker', 'isWebApplicationAttacker']:
        if simulator_entity.get(role_key):
            roles[role_key] = True

    # Resolve asset IDs to names
    asset_ids = simulator_entity.get('assets', [])
    resolved_assets = None
    if asset_ids and assets_map:
        resolved_assets = [
            assets_map[aid] for aid in asset_ids
            if aid in assets_map
        ]
    elif asset_ids:
        resolved_assets = [{"id": aid} for aid in asset_ids]

    # Simulation users (impersonated users)
    sim_users_raw = simulator_entity.get('simulationUsers', [])
    simulation_users = [
        {"name": u.get("name", ""), "username": u.get("username", "")}
        for u in sim_users_raw if isinstance(u, dict)
    ] if sim_users_raw else None

    minimal_simulator_entity = {
        'labels': simulator_entity['labels'],
        'isEnabled': simulator_entity['isEnabled'],
        'id': simulator_entity['id'],
        'name': simulator_entity['name'],
        'isConnected': simulator_entity['isConnected'],
        'isCritical': simulator_entity['isCritical'],
        'externalIp': simulator_entity['externalIp'],
        'internalIp': simulator_entity['internalIp'],
        'version': simulator_entity['version'],
        'OS': minimal_os_version,
        'roles': roles if roles else None,
        'isProxySupported': simulator_entity.get('isProxySupported', False),
        'assets': resolved_assets,
        'simulationUsers': simulation_users,
    }

    return minimal_simulator_entity


def get_full_simulator_mapping(simulator_entity):
    """
    Returns a full simulator entity with only the relevant fields.
    EXACT copy from original safebreach_types.py
    """
    full_os_version = get_minimal_simulator_mapping(simulator_entity)
    
    # Safely get installed applications, handle missing keys
    try:
        installed_software = simulator_entity['nodeInfo']['MACHINE_INFO']['INSTALLED_SOFTWARE']
        full_os_version["installed_applications"] = installed_software
    except KeyError:
        full_os_version["installed_applications"] = []
    
    return full_os_version


# --- Scenario Transform Functions ---


def _has_real_filter_criteria(filter_dict: Dict[str, Any]) -> bool:
    """Check if a filter dict has at least one key with non-empty values."""
    if not filter_dict:
        return False
    for value in filter_dict.values():
        if isinstance(value, dict):
            vals = value.get('values', [])
            if vals:
                return True
        elif value:
            return True
    return False


def compute_is_ready_to_run(scenario: Dict[str, Any]) -> bool:
    """
    Determine if a scenario is ready to run.

    A scenario is ready when ALL steps have BOTH targetFilter AND attackerFilter
    with at least one key containing non-empty values arrays.
    """
    steps = scenario.get('steps', [])
    if not steps:
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        target = step.get('targetFilter', {})
        attacker = step.get('attackerFilter', {})
        if not _has_real_filter_criteria(target) or not _has_real_filter_criteria(attacker):
            return False
    return True


def _truncate_description(description: Optional[str]) -> Optional[str]:
    """Truncate description to 200 chars with ellipsis if longer."""
    if description and len(description) > 200:
        return description[:200] + "..."
    return description


def _compute_total_attack_count(steps: List[Dict[str, Any]]) -> Optional[int]:
    """Compute total attack count across all scenario steps.

    Returns the sum of playbook IDs across steps. If any step uses criteria-based
    attack selection (no explicit playbook IDs), returns None to indicate
    the count is indeterminate at listing time.
    """
    if not steps:
        return 0
    total = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        attacks_filter = step.get('attacksFilter', {})
        if not isinstance(attacks_filter, dict):
            continue
        playbook_values = attacks_filter.get('playbook', {}).get('values', [])
        if playbook_values:
            total += len(playbook_values)
        else:
            # Step uses criteria-based selection — count is indeterminate
            return None
    return total


def get_reduced_scenario_mapping(
    scenario: Dict[str, Any],
    categories_map: Dict[int, str]
) -> Dict[str, Any]:
    """Transform a full OOB scenario object into a reduced representation for list view.

    Returns a dict with source_type='oob'. For custom plans use get_reduced_plan_mapping.
    """
    category_names = [
        categories_map[cat_id]
        for cat_id in scenario.get('categories', [])
        if cat_id in categories_map
    ]

    return {
        "id": str(scenario.get("id")),
        "source_type": "oob",
        "name": scenario.get("name"),
        "description": _truncate_description(scenario.get('description')),
        "createdBy": scenario.get("createdBy"),
        "recommended": scenario.get("recommended", False),
        "category_names": category_names,
        "tags": scenario.get("tags") or [],
        # SAF-34228: `or []` not `.get(k, [])` — the default applies only to a MISSING key, so a
        # record with "steps": null yields None and len() raises, failing the whole listing.
        "step_count": len(scenario.get("steps") or []),
        "total_attack_count": _compute_total_attack_count(scenario.get("steps") or []),
        "is_ready_to_run": compute_is_ready_to_run(scenario),
        "createdAt": scenario.get("createdAt"),
        "updatedAt": scenario.get("updatedAt"),
        "userId": None,
        "originalScenarioId": None,
    }


def get_reduced_plan_mapping(
    plan: Dict[str, Any],
    users_map: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """Transform a full custom plan object into a reduced representation for list view.

    Returns a dict with source_type='custom'. Plans come from the
    /api/config/v2/accounts/{id}/plans endpoint and have a different schema than OOB scenarios.
    """
    user_id = plan.get("userId")
    created_by = None
    if user_id and users_map:
        created_by = users_map.get(user_id)

    return {
        "id": str(plan.get("id")),
        "source_type": "custom",
        "name": plan.get("name"),
        "description": _truncate_description(plan.get('description')),
        "createdBy": created_by,
        "recommended": False,  # Custom plans don't have the recommended concept
        "category_names": [],  # Custom plans don't have categories
        "tags": plan.get("tags") or [],
        # SAF-34228: see get_reduced_scenario_mapping — null-safe, not just missing-safe.
        "step_count": len(plan.get("steps") or []),
        "total_attack_count": _compute_total_attack_count(plan.get("steps") or []),
        "is_ready_to_run": compute_is_ready_to_run(plan),
        "createdAt": plan.get("createdAt"),
        "updatedAt": plan.get("updatedAt"),
        "userId": plan.get("userId"),
        "originalScenarioId": plan.get("originalScenarioId"),
    }


def filter_scenarios_by_criteria(
    scenarios: List[Dict[str, Any]],
    name_filter: Optional[str] = None,
    creator_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    recommended_filter: Optional[bool] = None,
    tag_filter: Optional[str] = None,
    ready_to_run_filter: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Apply filters to a list of reduced scenario dicts using AND logic."""
    filtered = scenarios.copy()

    if name_filter:
        name_lower = name_filter.lower()
        filtered = [s for s in filtered if name_lower in s.get('name', '').lower()]

    if creator_filter:
        if creator_filter.lower() == 'safebreach':
            filtered = [s for s in filtered if s.get('source_type') == 'oob']
        elif creator_filter.lower() == 'custom':
            filtered = [s for s in filtered if s.get('source_type') == 'custom']

    if category_filter:
        cat_lower = category_filter.lower()
        filtered = [
            s for s in filtered
            if any(cat_lower in cn.lower() for cn in s.get('category_names', []))
        ]

    if recommended_filter is not None:
        filtered = [s for s in filtered if s.get('recommended') == recommended_filter]

    if tag_filter:
        tag_lower = tag_filter.lower()
        filtered = [
            s for s in filtered
            if s.get('tags') and any(tag_lower in t.lower() for t in s['tags'])
        ]

    if ready_to_run_filter is not None:
        filtered = [
            s for s in filtered
            if s.get('is_ready_to_run') == ready_to_run_filter
        ]

    return filtered


def apply_scenario_ordering(
    scenarios: List[Dict[str, Any]],
    order_by: str = "name",
    order_direction: str = "asc",
) -> List[Dict[str, Any]]:
    """Sort scenarios by the specified field and direction."""
    reverse = order_direction.lower() == 'desc'

    def sort_key(s):
        if order_by == 'name':
            return s.get('name', '').lower()
        elif order_by == 'step_count':
            return s.get('step_count', 0)
        elif order_by == 'createdAt':
            return s.get('createdAt', '')
        elif order_by == 'updatedAt':
            return s.get('updatedAt', '')
        return s.get('name', '').lower()

    return sorted(scenarios, key=sort_key, reverse=reverse)


def paginate_scenarios(
    scenarios: List[Dict[str, Any]],
    page_number: int = 0,
    page_size: int = 10,
    ready_to_run_filter_applied: bool = False,
) -> Dict[str, Any]:
    """Paginate a list of scenarios."""
    total_scenarios = len(scenarios)
    total_pages = (total_scenarios + page_size - 1) // page_size if total_scenarios > 0 else 0

    if page_number < 0 or (total_pages > 0 and page_number >= total_pages):
        return {
            'page_number': page_number,
            'total_pages': total_pages,
            'total_scenarios': total_scenarios,
            'scenarios_in_page': [],
            'error': f'Invalid page_number {page_number}. '
                     f'Available pages range from 0 to {total_pages - 1} (total {total_pages} pages)'
        }

    start_idx = page_number * page_size
    end_idx = min(start_idx + page_size, total_scenarios)
    page_scenarios = scenarios[start_idx:end_idx]

    hints = []
    if page_number + 1 < total_pages:
        hints.append(f'You can scan next page by calling with page_number={page_number + 1}')
    if not ready_to_run_filter_applied:
        ready_total = sum(1 for s in scenarios if s.get('is_ready_to_run'))
        ready_shown = sum(1 for s in page_scenarios if s.get('is_ready_to_run'))
        if ready_total > ready_shown:
            hints.append(
                f'{ready_total} of {total_scenarios} scenarios are ready to run as-is '
                f'(simulators already assigned). You can run the others too — for a '
                f'scenario that is not ready, run_scenario returns a diagnostic and you '
                f'supply per-step simulator selection (step_overrides) to run it. To list '
                f'only the ready-to-run ones, call get_scenarios with ready_to_run_filter=True.'
            )
    has_indeterminate = any(
        s.get('total_attack_count') is None for s in page_scenarios
    )
    if has_indeterminate:
        hints.append(
            'Some scenarios have criteria-based attack selection, so their '
            'total_attack_count is unavailable at listing time. Use run_scenario '
            'with evaluate=True to determine the exact attack count for those scenarios.'
        )

    return {
        'page_number': page_number,
        'total_pages': total_pages,
        'total_scenarios': total_scenarios,
        'scenarios_in_page': page_scenarios,
        'hint_to_agent': ' | '.join(hints) if hints else None,
    }


# --- Scenario Detail Transform Functions ---


def _extract_filter_values(filter_dict: Dict[str, Any], key: str) -> Optional[List]:
    """Extract values list from a nested filter dict, e.g. targetFilter['os']['values']."""
    entry = filter_dict.get(key, {})
    if isinstance(entry, dict):
        vals = entry.get('values', [])
        return vals if vals else None
    return None


def _simplify_step(step: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a raw step (OOB or custom) into a simplified LLM-readable format."""
    attacks_filter = step.get('attacksFilter', {})
    target_filter = step.get('targetFilter', {})
    attacker_filter = step.get('attackerFilter', {})

    # Determine attack selection mode
    playbook_ids = _extract_filter_values(attacks_filter, 'playbook')
    if playbook_ids:
        attack_selection = {
            "mode": "playbook_ids",
            "playbook_ids": playbook_ids,
        }
    else:
        # Criteria mode — extract tags and attack types
        attack_types = _extract_filter_values(attacks_filter, 'attackType')
        attack_tags = {}
        tags_dict = attacks_filter.get('tags', {})
        if isinstance(tags_dict, dict):
            for tag_key, tag_val in tags_dict.items():
                if isinstance(tag_val, dict):
                    vals = tag_val.get('values', [])
                    if vals:
                        attack_tags[tag_key] = vals
        attack_selection = {
            "mode": "criteria",
        }
        if attack_types:
            attack_selection["attack_types"] = attack_types
        if attack_tags:
            attack_selection["attack_tags"] = attack_tags
        if not attack_types and not attack_tags:
            attack_selection["note"] = "broad match — criteria resolved at runtime by the platform"

    # Target criteria (only include non-empty entries)
    target_criteria = {}
    for key in ('os', 'role', 'simulators'):
        vals = _extract_filter_values(target_filter, key)
        if vals:
            target_criteria[key] = vals
    if not target_criteria:
        target_criteria = None

    # Attacker criteria
    attacker_criteria = {}
    for key in ('os', 'role', 'simulators'):
        vals = _extract_filter_values(attacker_filter, key)
        if vals:
            attacker_criteria[key] = vals
    if not attacker_criteria:
        attacker_criteria = None

    return {
        "name": step.get("name"),
        "attack_selection": attack_selection,
        "target_criteria": target_criteria,
        "attacker_criteria": attacker_criteria,
    }


def _resolve_step_order_from_dag(
    steps: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Walk the actions/edges DAG and return steps in execution order.

    Skips 'wait' actions. Returns the steps list in traversal order.
    If the graph can't be walked (missing data), falls back to steps array order.
    """
    if not actions or not edges:
        return steps

    # Build action ID → action map
    action_map = {a['id']: a for a in actions}

    # Build uuid → step map
    step_by_uuid = {s['uuid']: s for s in steps if 'uuid' in s}

    # Find entry: edge with no 'from' or from=0
    entry_edge = None
    for e in edges:
        if 'from' not in e or e.get('from') == 0:
            entry_edge = e
            break
    if not entry_edge:
        return steps  # Fallback

    # Build adjacency: from → to
    adjacency = {}
    for e in edges:
        f = e.get('from', 0)
        adjacency[f] = e['to']

    # Walk from entry
    ordered_steps = []
    current_id = entry_edge['to']
    visited = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        action = action_map.get(current_id)
        if not action:
            break
        if action.get('type') == 'multiAttack':
            uuid = action.get('data', {}).get('uuid')
            if uuid and uuid in step_by_uuid:
                ordered_steps.append(step_by_uuid[uuid])
        current_id = adjacency.get(current_id)

    return ordered_steps if ordered_steps else steps


def get_scenario_detail_view(
    scenario: Dict[str, Any],
    categories_map: Dict[int, str],
    source_type: str,
    users_map: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    """Transform a full scenario/plan into a simplified LLM-readable detail view.

    Strips execution mechanics (actions, edges, phases) and normalizes steps
    into a unified format regardless of source type.
    """
    # Resolve steps in execution order
    raw_steps = scenario.get('steps', [])
    actions = scenario.get('actions')
    edges = scenario.get('edges')

    if actions and edges:
        ordered_steps = _resolve_step_order_from_dag(raw_steps, actions, edges)
    else:
        ordered_steps = raw_steps

    simplified_steps = [_simplify_step(s) for s in ordered_steps]

    # Detect wait actions
    has_wait_steps = False
    if actions:
        has_wait_steps = any(a.get('type') == 'wait' for a in actions)

    # Resolve categories
    category_names = []
    if source_type == 'oob':
        category_names = [
            categories_map[cat_id]
            for cat_id in scenario.get('categories', [])
            if cat_id in categories_map
        ]

    return {
        "id": str(scenario.get("id")),
        "source_type": source_type,
        "name": scenario.get("name"),
        "description": scenario.get("description"),
        "category_names": category_names,
        "tags": scenario.get("tags") or [],
        "recommended": scenario.get("recommended", False) if source_type == 'oob' else False,
        "createdBy": (
            scenario.get("createdBy") if source_type == 'oob'
            else (users_map or {}).get(scenario.get("userId")) if users_map
            else None
        ),
        "createdAt": scenario.get("createdAt"),
        "updatedAt": scenario.get("updatedAt"),
        "originalScenarioId": scenario.get("originalScenarioId"),
        "userId": scenario.get("userId"),
        "step_count": len(simplified_steps),
        "is_ready_to_run": compute_is_ready_to_run(scenario),
        "steps": simplified_steps,
        "has_wait_steps": has_wait_steps,
    }


# =============================================================================
# Integration-discovery transforms & helpers (SAF-32798)
# =============================================================================

# Canonical integration-category taxonomy — the backend's own set (GET /config/categories).
# Kept here so tool docstrings can advertise the real, filterable values.
CATEGORY_TAXONOMY = [
    "custom", "siem", "security_control", "ti", "workflow",
    "file_provider", "deployment", "secret_provider", "vulnerability_management",
]

# Capability-flag → functional-category map. The raw `category` field is an *origin*
# label (notably "custom" for user-created connectors), so it can hide a connector's real
# function; the per-type capability flags are authoritative for that function. Mapping is
# 1:1 in the live data — no type carries more than one core capability flag. This mirrors
# how the console UI derives a connector's categories from capability probes.
_CAPABILITY_CATEGORY = {
    "isTi": "ti",
    "isTiV2": "ti",
    "isVm": "vulnerability_management",
    "isPam": "secret_provider",
    "isFileProvider": "file_provider",
    "isSendSimResult": "workflow",
    "isSecEvents": "security_control",
}


def derive_categories(raw_def: Dict[str, Any]) -> List[str]:
    """Derive a connector type's full category membership: the raw `category` label unioned
    with every capability-flag-implied category. This resolves the `custom` bucket — e.g.
    a `custom` connector that is `isTiV2` derives `["custom", "ti"]` — so category filtering
    matches the connector's real function, not just its origin label. Order follows
    CATEGORY_TAXONOMY for stable output; unknown raw labels are appended last."""
    if not isinstance(raw_def, dict):
        return []
    cats = set()
    raw = raw_def.get("category")
    if raw:
        cats.add(raw)
    for flag, category in _CAPABILITY_CATEGORY.items():
        if raw_def.get(flag):
            cats.add(category)
    ordered = [c for c in CATEGORY_TAXONOMY if c in cats]
    ordered += sorted(c for c in cats if c not in CATEGORY_TAXONOMY)
    return ordered


def categories_for_type(catalog: Dict[str, Any], type_key: Optional[str]) -> List[str]:
    """Derived category membership for an installed connector, joined from the catalog by
    type. Empty when the type is absent from the catalog (conservative — never guesses)."""
    type_def = catalog.get(type_key) if isinstance(catalog, dict) else None
    return derive_categories(type_def) if isinstance(type_def, dict) else []


def get_integration_catalog_entry(type_key: str, raw_def: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw catalog type-def (from /config/integrations, keyed by type) to the
    public catalog entry. Allow-list only — internal fields (fields[], featureFlag,
    guideLink, raw is* flags) are never exposed.

    `category` is the raw origin label; `categories` is the derived functional membership
    (see derive_categories) and is what `category_filter` matches against."""
    return {
        "type": type_key,
        "name": raw_def.get("displayName") or type_key,
        "description": raw_def.get("description"),
        "category": raw_def.get("category"),
        "categories": derive_categories(raw_def),
        "vendor": raw_def.get("vendor"),
        "product": raw_def.get("product"),
    }


def _partial_ci_match(value: Optional[str], term: Optional[str]) -> bool:
    """True when `term` is a case-insensitive substring of `value` (or term is falsy)."""
    if not term:
        return True
    return term.lower() in (value or "").lower()


def _partial_ci_match_any(values: Optional[List[str]], term: Optional[str]) -> bool:
    """True when `term` is a case-insensitive substring of any value in `values`
    (or term is falsy). Used for the derived `categories` list."""
    if not term:
        return True
    return any(_partial_ci_match(v, term) for v in (values or []))


def filter_integration_catalog(
    entries: List[Dict[str, Any]],
    name_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    vendor_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter catalog entries by partial/case-insensitive string filters. `category_filter`
    matches against the derived `categories` membership (so e.g. 'ti' also matches a `custom`
    connector that is TI-capable)."""
    def keep(e: Dict[str, Any]) -> bool:
        if not _partial_ci_match(e.get("name"), name_filter):
            return False
        if not _partial_ci_match_any(e.get("categories"), category_filter):
            return False
        if not _partial_ci_match(e.get("vendor"), vendor_filter):
            return False
        return True

    return [e for e in entries if keep(e)]


def apply_integration_ordering(
    entries: List[Dict[str, Any]],
    order_by: str = "name",
    order_direction: str = "asc",
) -> List[Dict[str, Any]]:
    """Order integration entries by a field, case-insensitively for strings.

    Works for catalog (name/type/category/vendor) and installed/TI (name/type/id/enabled)."""
    reverse = order_direction == "desc"

    def key(e: Dict[str, Any]):
        v = e.get(order_by)
        # (is-missing, normalized-value) keeps None values grouped and types homogeneous per field
        if v is None:
            return (1, "")
        if isinstance(v, str):
            return (0, v.lower())
        return (0, v)

    return sorted(entries, key=key, reverse=reverse)


def paginate_integration_list(
    items: List[Dict[str, Any]],
    page_number: int,
    page_size: int,
    noun: str,
) -> Dict[str, Any]:
    """Generic pagination for the integration tools. `noun` sets the response keys:
    `total_<noun>` and `<noun>_in_page` (e.g. noun='integrations')."""
    total = len(items)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    result: Dict[str, Any] = {
        "page_number": page_number,
        "total_pages": total_pages,
        f"total_{noun}": total,
    }

    if page_number < 0 or (total_pages > 0 and page_number >= total_pages):
        result[f"{noun}_in_page"] = []
        result["error"] = (
            f"Invalid page_number {page_number}. "
            f"Available pages range from 0 to {max(total_pages - 1, 0)} (total {total_pages} pages)"
        )
        return result

    start = page_number * page_size
    end = min(start + page_size, total)
    result[f"{noun}_in_page"] = items[start:end]

    if total == 0:
        result["hint_to_agent"] = (
            f"No {noun} matched. Try removing or broadening the filters."
        )
    elif page_number + 1 < total_pages:
        result["hint_to_agent"] = (
            f"You can scan the next page by calling with page_number={page_number + 1}"
        )

    return result


def get_minimal_installed_integration(raw: Dict[str, Any], catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Project a raw installed connector to the slim public shape — never secrets.

    Allow-list `id/type/name/enabled`; `enabled` defaults to False when absent. When a
    `catalog` is supplied, the connector is enriched with its `category` (raw origin label)
    and derived `categories` membership, joined from the catalog by type — the installed
    payload itself carries no category, so it must come from the catalog."""
    type_key = raw.get("type")
    entry = {
        "id": raw.get("id"),
        "type": type_key,
        "name": raw.get("name"),
        "enabled": bool(raw.get("enabled", False)),
    }
    if catalog is not None:
        type_def = catalog.get(type_key) if isinstance(catalog, dict) else None
        entry["category"] = type_def.get("category") if isinstance(type_def, dict) else None
        entry["categories"] = categories_for_type(catalog, type_key)
    return entry


def filter_installed_integrations(
    entries: List[Dict[str, Any]],
    name_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    enabled_filter: Optional[bool] = None,
    category_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter installed connectors by partial/case-insensitive name/type, boolean enabled,
    and `category_filter` (matched against the derived `categories` membership)."""
    def keep(e: Dict[str, Any]) -> bool:
        if not _partial_ci_match(e.get("name"), name_filter):
            return False
        if not _partial_ci_match(e.get("type"), type_filter):
            return False
        if enabled_filter is not None and bool(e.get("enabled")) != enabled_filter:
            return False
        if not _partial_ci_match_any(e.get("categories"), category_filter):
            return False
        return True

    return [e for e in entries if keep(e)]


# Redaction constants 
REDACTED_PLACEHOLDER = "@enc:SENSITIVE_FIELD"
ALWAYS_REDACTED_FIELDS = ["proxyPass", "headers"]

# Conservative fail-safe set for connector types absent from the catalog, so an unknown
# type can never bypass schema-driven masking. Field names drawn from the live pentest01
# connector schemas (SAF-32798 research).
_DEFAULT_SENSITIVE_FIELDS = {
    "password", "token", "secret", "apiToken", "apiSecret", "apiKey", "clientSecret",
    "secretId", "privateKey", "keyPassword", "pfxPassword", "clientKeyPassword",
    "uidTokenCurrent", "uidTokenNext", "proxyPass",
}


def _schema_sensitive_fields(catalog: Dict[str, Any], connector_type: Optional[str]):
    """Return the set of schema-`sensitive` field keys for a type, or None when the type
    is absent from the catalog (signals the caller to use the fail-safe default set)."""
    type_def = catalog.get(connector_type) if isinstance(catalog, dict) else None
    if not isinstance(type_def, dict):
        return None
    fields = type_def.get("fields") or []
    return {f.get("key") for f in fields if isinstance(f, dict) and f.get("sensitive") and f.get("key")}


def redact_sensitive_fields(connector: Dict[str, Any], catalog: Dict[str, Any]):
    """Return `(redacted_copy, redacted_field_names)` for a connector config.

    A single recursive pass masks, at EVERY dict depth:
    1. any key whose name is in the unified sensitive set — the union of the type's
       schema-`sensitive` fields, a conservative fail-safe default set, and the
       always-redacted names (`headers`, `proxyPass`). Unioning (rather than either/or)
       ensures a partially-flagged schema can never drop the default protections, and
       recursing ensures a nested `headers`/secret is masked, not just a top-level one.
    2. any `$PAM:`/`@enc:` vault-reference string value — defense-in-depth for a secret
       the key-name set misses.
    The input is not mutated.
    """
    sensitive = (_schema_sensitive_fields(catalog, connector.get("type")) or set()) \
        | _DEFAULT_SENSITIVE_FIELDS | set(ALWAYS_REDACTED_FIELDS)

    redacted_keys: set = set()

    def _redact(value: Any) -> Any:
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k in sensitive:
                    out[k] = REDACTED_PLACEHOLDER
                    redacted_keys.add(k)
                else:
                    masked = _redact(v)
                    if isinstance(v, str) and masked == REDACTED_PLACEHOLDER and v != REDACTED_PLACEHOLDER:
                        redacted_keys.add(k)
                    out[k] = masked
            return out
        if isinstance(value, list):
            return [_redact(v) for v in value]
        if isinstance(value, str) and (value.startswith("$PAM:") or value.startswith("@enc:")):
            return REDACTED_PLACEHOLDER
        return value

    return _redact(connector), sorted(redacted_keys)


def get_installed_integration_detail_view(connector: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
    """Full config of a single installed connector, with sensitive fields redacted, plus a
    machine-readable `redacted_fields` list of the field names that were masked (so an agent
    need not scan values for the placeholder)."""
    redacted, redacted_fields = redact_sensitive_fields(connector, catalog)
    return {"integration": redacted, "redacted_fields": redacted_fields}