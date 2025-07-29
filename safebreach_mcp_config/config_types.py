"""
SafeBreach Config Types

This module provides data type mappings and transformations for SafeBreach configuration data,
specifically for simulator entities and related configuration objects.
"""

from typing import Dict, Any, Optional

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