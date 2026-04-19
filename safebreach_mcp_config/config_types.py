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


def get_minimal_simulator_mapping(simulator_entity):
    """
    Returns a reduced simulator entity with only the relevant fields.
    EXACT copy from original safebreach_types.py
    """
    minimal_os_version = map_reduced_entity(simulator_entity['nodeInfo']['MACHINE_INFO']['OS'], reduced_simulator_os_version_mapping)
    # Role flags — what this simulator can act as
    roles = {}
    for role_key in ['isInfiltration', 'isExfiltration', 'isAWSAttacker',
                     'isAzureAttacker', 'isGCPAttacker', 'isWebApplicationAttacker']:
        if simulator_entity.get(role_key):
            roles[role_key] = True

    minimal_simulator_entity = {'labels': simulator_entity['labels'],
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
        "step_count": len(scenario.get("steps", [])),
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
        "step_count": len(plan.get("steps", [])),
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

    return {
        'page_number': page_number,
        'total_pages': total_pages,
        'total_scenarios': total_scenarios,
        'scenarios_in_page': scenarios[start_idx:end_idx],
        'hint_to_agent': f'You can scan next page by calling with page_number={page_number + 1}'
                         if page_number + 1 < total_pages else None,
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