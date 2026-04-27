'''
SafeBreach Secret Management Utilities

This file implements a secret accessor using a pluggable provider interface.
Supports multiple secret storage backends through the SecretProvider interface.
'''

import logging
from typing import Optional, Dict, Any
import os
from .cache_config import is_caching_enabled
from .secret_providers import SecretProviderFactory, SecretProvider
from .environments_metadata import safebreach_envs, get_environment_by_name
from .token_context import _user_auth_artifacts, mask_artifacts

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
    
    try:
        env_config = get_environment_by_name(console)
    except ValueError:
        raise ValueError(f"Console '{console}' not found in environments metadata. "
                        f"Available consoles: {list(safebreach_envs.keys())}")
    
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


class AuthenticationRequired(Exception):
    """Raised when a tool call lacks user credentials and RBAC enforcement is active."""
    pass


RBAC_DENIED_HINT = (
    "hint_to_llm: This user's role does not have permission to access this resource. "
    "Advise the user to contact their SafeBreach administrator to review their role permissions."
)


def check_rbac_response(response) -> None:
    """Call instead of response.raise_for_status() to add RBAC hints on 403.

    For 403 Forbidden responses (OPA denial), raises an error with an
    actionable hint for the LLM to advise the user about permissions.
    For all other errors, behaves like raise_for_status().
    """
    if response.status_code == 403:
        url = response.url if hasattr(response, 'url') else 'unknown'
        raise PermissionError(
            f"Access denied (403 Forbidden) for {url}.\n\n{RBAC_DENIED_HINT}"
        )
    response.raise_for_status()


def get_auth_headers_for_console(console: str) -> Dict[str, str]:
    """Return auth headers for outbound backend API calls.

    Priority:
    1. Per-request user auth bundle (from ContextVar) — RBAC-enforced path
    2. Raises AuthenticationRequired if ContextVar is empty in tool context

    Non-tool callers (startup, health checks) should use get_secret_for_console() directly.
    """
    bundle = _user_auth_artifacts.get()
    if bundle:
        logger.debug(f"get_auth_headers_for_console('{console}') → user bundle "
                     f"(keys: {list(bundle.keys())}, token: ***{list(bundle.values())[0][-4:]})")
        return dict(bundle)  # copy — callers may mutate

    # No user auth artifacts — this is an RBAC violation in tool context
    logger.warning(f"No user auth in context for '{console}' — rejecting (RBAC enforcement)")
    raise AuthenticationRequired(
        f"Authentication required for console '{console}': no user credentials in request context"
    )


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

    # Check cache first (only if caching is enabled)
    if is_caching_enabled() and cache_key in _provider_cache:
        return _provider_cache[cache_key]

    # Extract provider initialization parameters
    provider_kwargs = {}
    if 'region_name' in secret_config:
        provider_kwargs['region_name'] = secret_config['region_name']

    provider = SecretProviderFactory.create_provider(
        provider_type, **provider_kwargs
    )

    # Cache the provider (only if caching is enabled)
    if is_caching_enabled():
        _provider_cache[cache_key] = provider
        logger.debug(f"Created and cached new provider instance: {cache_key}")

    return provider
