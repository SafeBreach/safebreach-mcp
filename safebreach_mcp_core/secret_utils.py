'''
SafeBreach Secret Management Utilities

This file implements a secret accessor using a pluggable provider interface.
Supports multiple secret storage backends through the SecretProvider interface.
'''

import logging
from typing import Optional, Dict, Any
import os
from .secret_providers import SecretProviderFactory, SecretProvider
from .environments_metadata import safebreach_envs

logger = logging.getLogger(__name__)

# Global cache for provider instances
_provider_cache: Dict[str, SecretProvider] = {}

def get_secret_for_console(console: str) -> str:
    """
    Get the API token for a specific SafeBreach console using the configured secret provider.
    If the environment variable mcp_in_console is set, the function returns the value of that variable.
    When the MCP server is hosted in a console the API token is not validated.
    
    Args:
        console: The console name (e.g., 'demo-console', 'prod-console')
        
    Returns:
        The API token for the console
        
    Raises:
        ValueError: If the console is not found in environments metadata
        Exception: If the secret cannot be retrieved
    """
    # Check if the MCP server is running in a console environment
    mcp_in_console = os.getenv('mcp_in_console')
    if mcp_in_console:
        logger.info("Running in console environment, returning mcp_in_console value")
        return mcp_in_console
    
    if console not in safebreach_envs:
        raise ValueError(f"Console '{console}' not found in environments metadata. "
                        f"Available consoles: {list(safebreach_envs.keys())}")
    
    env_config = safebreach_envs[console]
    
    # Get secret configuration, with fallback to default AWS SSM pattern
    secret_config = env_config.get('secret_config', {
        'provider': 'aws_ssm',
        'parameter_name': f'{console}-apitoken'
    })
    
    provider_type = secret_config.get('provider', 'aws_ssm')
    secret_identifier = secret_config.get('parameter_name', f'{console}-apitoken')
    
    # Get or create provider instance (cached)
    provider = _get_or_create_provider(provider_type, secret_config)
    
    # Retrieve the secret
    logger.info(f"Getting secret for console '{console}' using provider '{provider_type}'")
    return provider.get_secret(secret_identifier)


def _get_or_create_provider(provider_type: str, secret_config: Dict[str, Any]) -> SecretProvider:
    """
    Get or create a secret provider instance, with caching.
    
    Args:
        provider_type: Type of provider ('aws_ssm', 'aws_secrets_manager')
        secret_config: Configuration for the provider
        
    Returns:
        SecretProvider instance
    """
    cache_key = f"{provider_type}:{secret_config.get('region_name', 'us-east-1')}"
    
    if cache_key not in _provider_cache:
        # Extract provider initialization parameters
        provider_kwargs = {}
        if 'region_name' in secret_config:
            provider_kwargs['region_name'] = secret_config['region_name']
        
        _provider_cache[cache_key] = SecretProviderFactory.create_provider(
            provider_type, **provider_kwargs
        )
        logger.debug(f"Created new provider instance: {cache_key}")
    
    return _provider_cache[cache_key]
