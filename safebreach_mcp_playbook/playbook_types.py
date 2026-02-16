"""
SafeBreach Playbook Data Types

This module provides data transformation functions for SafeBreach playbook operations.
It handles mapping between SafeBreach API response format and MCP tool response format.
"""

from typing import Dict, Any, List, Optional


def _transform_tags(tags_data: Any) -> List[str]:
    """
    Transform SafeBreach tags structure into a simple list of strings.
    
    Handles both formats:
    1. Complex nested format:
    [
        {
            "id": 14,
            "name": "sector",
            "values": [
                {"id": 1, "value": "Banking", "displayName": "Banking"},
                {"id": 2, "value": "Education", "displayName": "Education"}
            ]
        }
    ]
    -> ["sector:Banking", "sector:Education"]
    
    2. Simple format (for backward compatibility with tests):
    ["network", "dns"] -> ["network", "dns"]
    
    Args:
        tags_data: Raw tags data from SafeBreach API
        
    Returns:
        List of formatted tag strings
    """
    if not tags_data or not isinstance(tags_data, list):
        return []
    
    formatted_tags = []
    
    for tag_item in tags_data:
        if isinstance(tag_item, str):
            # Simple format - just use the string directly
            formatted_tags.append(tag_item)
        elif isinstance(tag_item, dict):
            # Complex nested format
            tag_name = tag_item.get('name', 'unknown')
            values = tag_item.get('values', [])
            
            if isinstance(values, list):
                for value_obj in values:
                    if isinstance(value_obj, dict):
                        display_name = value_obj.get('displayName') or value_obj.get('value', 'unknown')
                        formatted_tags.append(f"{tag_name}:{display_name}")
                    elif isinstance(value_obj, str):
                        formatted_tags.append(f"{tag_name}:{value_obj}")
            elif isinstance(values, str):
                formatted_tags.append(f"{tag_name}:{values}")
    
    return formatted_tags


def _extract_mitre_data(tags_data: Any) -> Dict[str, Any]:
    """
    Extract MITRE ATT&CK data from the tags array.

    Looks for tag items with names: MITRE_Tactic, MITRE_Technique, MITRE_Sub_Technique.
    Constructs ATT&CK URLs from technique IDs.

    Args:
        tags_data: Raw tags list from SafeBreach API

    Returns:
        Dict with keys: mitre_tactics, mitre_techniques, mitre_sub_techniques (each a list)
    """
    result = {
        'mitre_tactics': [],
        'mitre_techniques': [],
        'mitre_sub_techniques': []
    }

    if not tags_data or not isinstance(tags_data, list):
        return result

    for tag_item in tags_data:
        if not isinstance(tag_item, dict):
            continue

        tag_name = tag_item.get('name', '')
        values = tag_item.get('values', [])

        if not isinstance(values, list):
            continue

        if tag_name == 'MITRE_Tactic':
            for val in values:
                if isinstance(val, dict):
                    name = val.get('displayName') or val.get('value', '')
                    if name:
                        result['mitre_tactics'].append({'name': name})

        elif tag_name == 'MITRE_Technique':
            for val in values:
                if isinstance(val, dict):
                    tech_id = val.get('value', '')
                    display_name = val.get('displayName', '')
                    if tech_id:
                        url = f"https://attack.mitre.org/techniques/{tech_id}/"
                        result['mitre_techniques'].append({
                            'id': tech_id,
                            'display_name': display_name,
                            'url': url
                        })

        elif tag_name == 'MITRE_Sub_Technique':
            for val in values:
                if isinstance(val, dict):
                    tech_id = val.get('value', '')
                    display_name = val.get('displayName', '')
                    if tech_id:
                        # Sub-technique IDs use '.' (e.g., T1021.001) -> URL uses '/' (T1021/001)
                        url_path = tech_id.replace('.', '/')
                        url = f"https://attack.mitre.org/techniques/{url_path}/"
                        result['mitre_sub_techniques'].append({
                            'id': tech_id,
                            'display_name': display_name,
                            'url': url
                        })

    return result


def get_reduced_playbook_attack_mapping() -> Dict[str, str]:
    """
    Get mapping for reduced playbook attack objects.
    
    Returns:
        Dict mapping output fields to source fields
    """
    return {
        'name': 'name',
        'id': 'id',
        'description': 'description', 
        'modifiedDate': 'modifiedDate',
        'publishedDate': 'publishedDate'
    }


def get_full_playbook_attack_mapping() -> Dict[str, str]:
    """
    Get mapping for full playbook attack objects.
    
    Returns:
        Dict mapping output fields to source fields  
    """
    reduced_mapping = get_reduced_playbook_attack_mapping()
    full_mapping = {
        **reduced_mapping,
        'fix_suggestions': 'metadata.fix_suggestions',
        'tags': 'tags',
        'params': 'content.params'
    }
    return full_mapping


def transform_reduced_playbook_attack(attack_data: Dict[str, Any],
                                      include_mitre_techniques: bool = False) -> Dict[str, Any]:
    """
    Transform a playbook attack to reduced format.

    Args:
        attack_data: Raw attack data from SafeBreach API
        include_mitre_techniques: Whether to include MITRE ATT&CK data

    Returns:
        Transformed attack data in reduced format
    """
    mapping = get_reduced_playbook_attack_mapping()
    result = {}

    for output_key, source_key in mapping.items():
        if '.' in source_key:
            # Handle nested keys like 'metadata.fix_suggestions'
            keys = source_key.split('.')
            value = attack_data
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = None
                    break
            result[output_key] = value
        else:
            result[output_key] = attack_data.get(source_key)

    if include_mitre_techniques:
        mitre_data = _extract_mitre_data(attack_data.get('tags', []))
        result.update(mitre_data)

    return result


def transform_full_playbook_attack(attack_data: Dict[str, Any],
                                   include_fix_suggestions: bool = True,
                                   include_tags: bool = True,
                                   include_parameters: bool = True,
                                   include_mitre_techniques: bool = False) -> Dict[str, Any]:
    """
    Transform a playbook attack to full format with verbosity options.

    Args:
        attack_data: Raw attack data from SafeBreach API
        include_fix_suggestions: Whether to include fix suggestions
        include_tags: Whether to include tags
        include_parameters: Whether to include parameters
        include_mitre_techniques: Whether to include MITRE ATT&CK data

    Returns:
        Transformed attack data in full format
    """
    # Start with reduced format (with MITRE if requested)
    result = transform_reduced_playbook_attack(attack_data, include_mitre_techniques=include_mitre_techniques)
    
    # Add optional fields based on verbosity settings
    if include_fix_suggestions:
        fix_suggestions = None
        if 'metadata' in attack_data and isinstance(attack_data['metadata'], dict):
            fix_suggestions = attack_data['metadata'].get('fix_suggestions')
        result['fix_suggestions'] = fix_suggestions
    
    if include_tags:
        raw_tags = attack_data.get('tags')
        result['tags'] = _transform_tags(raw_tags)
    
    if include_parameters:
        params = None
        if 'content' in attack_data and isinstance(attack_data['content'], dict):
            params = attack_data['content'].get('params')
        result['params'] = params
    
    return result


def filter_attacks_by_criteria(attacks: List[Dict[str, Any]], 
                               name_filter: Optional[str] = None,
                               description_filter: Optional[str] = None,
                               id_min: Optional[int] = None,
                               id_max: Optional[int] = None,
                               modified_date_start: Optional[str] = None,
                               modified_date_end: Optional[str] = None,
                               published_date_start: Optional[str] = None,
                               published_date_end: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Filter attacks based on various criteria.
    
    Args:
        attacks: List of attack objects
        name_filter: Partial match on name (case-insensitive)
        description_filter: Partial match on description (case-insensitive)
        id_min: Minimum ID value (inclusive)
        id_max: Maximum ID value (inclusive)
        modified_date_start: Start date for modified date range (ISO format)
        modified_date_end: End date for modified date range (ISO format)
        published_date_start: Start date for published date range (ISO format)
        published_date_end: End date for published date range (ISO format)
        
    Returns:
        Filtered list of attacks
    """
    filtered_attacks = attacks.copy()
    
    # Filter by name (partial, case-insensitive)
    if name_filter:
        name_filter_lower = name_filter.lower()
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('name') and name_filter_lower in attack['name'].lower()
        ]
    
    # Filter by description (partial, case-insensitive)
    if description_filter:
        description_filter_lower = description_filter.lower()
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('description') and description_filter_lower in attack['description'].lower()
        ]
    
    # Filter by ID range
    if id_min is not None:
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('id') is not None and attack['id'] >= id_min
        ]
    
    if id_max is not None:
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('id') is not None and attack['id'] <= id_max
        ]
    
    # Filter by modified date range
    if modified_date_start:
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('modifiedDate') and attack['modifiedDate'] >= modified_date_start
        ]
    
    if modified_date_end:
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('modifiedDate') and attack['modifiedDate'] <= modified_date_end
        ]
    
    # Filter by published date range
    if published_date_start:
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('publishedDate') and attack['publishedDate'] >= published_date_start
        ]
    
    if published_date_end:
        filtered_attacks = [
            attack for attack in filtered_attacks
            if attack.get('publishedDate') and attack['publishedDate'] <= published_date_end
        ]
    
    return filtered_attacks


def paginate_attacks(attacks: List[Dict[str, Any]], 
                     page_number: int = 0, 
                     page_size: int = 10) -> Dict[str, Any]:
    """
    Paginate a list of attacks.
    
    Args:
        attacks: List of attack objects
        page_number: Page number (0-based)
        page_size: Number of items per page
        
    Returns:
        Dict containing paginated results and metadata
    """
    total_attacks = len(attacks)
    total_pages = (total_attacks + page_size - 1) // page_size  # Ceiling division
    
    # Validate page number
    if page_number < 0 or (total_pages > 0 and page_number >= total_pages):
        return {
            'page_number': page_number,
            'total_pages': total_pages,
            'total_attacks': total_attacks,
            'attacks_in_page': [],
            'error': f'Invalid page_number {page_number}. Available pages range from 0 to {total_pages - 1} (total {total_pages} pages)'
        }
    
    # Calculate slice indices
    start_idx = page_number * page_size
    end_idx = min(start_idx + page_size, total_attacks)
    
    attacks_in_page = attacks[start_idx:end_idx]
    
    return {
        'page_number': page_number,
        'total_pages': total_pages,
        'total_attacks': total_attacks,
        'attacks_in_page': attacks_in_page,
        'hint_to_agent': f'You can scan next page by calling with page_number={page_number + 1}' if page_number + 1 < total_pages else None
    }