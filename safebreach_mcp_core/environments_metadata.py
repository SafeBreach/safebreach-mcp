'''
SafeBreach Environments Configuration

This file contains metadata and configurations for Safebreach labs and AWS resources 
in the scope of impact for SafeBreach MCP Servergi.
'''
import json, os, logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

safebreach_envs = {
    # Default example configurations:
    "demo-console": {
        "url": "demo.safebreach.com", 
        "account": "1234567890",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "demo-console-apitoken"
        }
    },
    "example-console": {
        "url": "example.safebreach.com", 
        "account": "0987654321",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "example-console-apitoken"
        }
    }
}

load_dotenv()
if os.environ.get('SAFEBREACH_ENVS_FILE'):
    # Load environments metadata from a JSON file if specified in environment variable
    # This allows for dynamic loading of environments without hardcoding them
    with open(os.environ['SAFEBREACH_ENVS_FILE']) as f:
        safebreach_envs.update(json.load(f))

if os.environ.get('SAFEBREACH_LOCAL_ENV'):
    # Load environments metadata from a JSON string in environment variable
    # This allows for direct configuration without requiring a file
    # SAFEBREACH_LOCAL_ENV can extend and override environments from other sources
    try:
        local_envs = json.loads(os.environ['SAFEBREACH_LOCAL_ENV'])
        safebreach_envs.update(local_envs)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in SAFEBREACH_LOCAL_ENV environment variable: {e}")

def get_console_name() -> str:
    """
    Get the console name for single-tenant deployment.
    In single-tenant mode, the console name is provided via SAFEBREACH_CONSOLE_NAME environment variable.
    
    Returns:
        Console name from SAFEBREACH_CONSOLE_NAME environment variable, or 'default' if not set
    """
    return os.getenv('SAFEBREACH_CONSOLE_NAME', 'default')

def get_environment_by_name(name: str) -> dict:
    """
    Get environment configuration by name.
    In single-tenant mode, when no environments are configured and SAFEBREACH_CONSOLE_NAME is set,
    returns a dynamic configuration for the console.
    
    Args:
        name: Environment name
        
    Returns:
        Environment configuration dictionary
        
    Raises:
        ValueError: If environment not found
    """
    if name not in safebreach_envs:
        # Check if we're in single-tenant mode (no hardcoded environments)
        if not safebreach_envs:
            # In single-tenant mode, return dynamic configuration for any requested console
            # Use the requested console name for token lookup
            token_name = name.replace('-', '_')
            return {
                "url": "single-tenant-mode",
                "account": os.getenv('ACCOUNT_ID', 'single-tenant-account'),
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": f"{token_name}_apitoken"
                }
            }
        raise ValueError(f"Environment '{name}' not found. Available environments: {list(safebreach_envs.keys())}")
    return safebreach_envs[name]

def get_api_base_url(console:str, endpoint:str) -> str:
    """
    Get the base URL for SafeBreach API for a given console and endpoint.

    Priority order (SAF-29974: reordered so SAFEBREACH_LOCAL_ENV wins over env vars):
    1. SAFEBREACH_LOCAL_ENV service-specific URLs (set by mcp_manager in SIMP)
    2. Per-service environment variables (DATA_URL, CONFIG_URL, etc.)
    3. SAFEBREACH_LOCAL_ENV default URL fallback

    Args:
        console: Console name (e.g., 'demo-console', 'example-console')
        endpoint: Endpoint name can only be one of 'data', 'config', 'moves', 'queue', 'siem', 'playbook', 'orchestrator'

    Returns:
        Base URL as a string
    """
    # Priority 1: SAFEBREACH_LOCAL_ENV service-specific URL (SAF-29974)
    # When running inside SIMP, mcp_manager sets these to the RBAC gateway URL.
    # If the exact console name isn't found, fall back to the 'default' entry —
    # this prevents callers from bypassing OPA by specifying an unknown console name.
    for lookup_name in (console, 'default'):
        try:
            console_config = get_environment_by_name(lookup_name)
            if 'urls' in console_config and endpoint in console_config['urls']:
                service_url = console_config['urls'][endpoint]
                full_url = f"https://{service_url}" if not service_url.startswith(('http://', 'https://')) else service_url
                if lookup_name != console:
                    logger.debug("get_api_base_url('%s', '%s') → %s (from SAFEBREACH_LOCAL_ENV 'default' fallback)",
                                 console, endpoint, full_url)
                else:
                    logger.debug("get_api_base_url('%s', '%s') → %s (from SAFEBREACH_LOCAL_ENV urls)",
                                 console, endpoint, full_url)
                return full_url
        except (ValueError, KeyError):
            continue

    # Priority 2: Per-service environment variables (standalone MCP server mode)
    env_var_name = f'{endpoint.upper()}_URL'
    env_url = os.getenv(env_var_name)
    if env_url:
        logger.debug("get_api_base_url('%s', '%s') → %s (from env var %s)", console, endpoint, env_url, env_var_name)
        return env_url

    # Priority 3: SAFEBREACH_LOCAL_ENV default URL fallback
    try:
        console_config = get_environment_by_name(console)
        default_url = f"https://{console_config['url']}"
        logger.debug("get_api_base_url('%s', '%s') → %s (from default url)", console, endpoint, default_url)
        return default_url
    except (ValueError, KeyError):
        raise ValueError(f"No URL configured for console '{console}', endpoint '{endpoint}'")

def get_api_account_id(console: str) -> str:
    """
    Get the account ID for a given console.
    If the MCP Server is hosted in a console then it is a single-tenant environment and the account ID is served from an environment variable.
    Otherwise, the MCP Server is hosted in a multi-tenant environment and the account ID is retrieved from the environments metadata.
    
    Args:
        console: Console name (e.g., 'demo-console', 'example-console')
        
    Returns:
        Account ID as a string
        
    Raises:
        ValueError: If console not found
    """
    account_id = os.getenv('ACCOUNT_ID')

    if account_id:
        return account_id
    
    account_id = get_environment_by_name(console)['account']
    return account_id