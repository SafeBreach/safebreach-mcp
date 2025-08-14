'''
SafeBreach Environments Configuration

This file contains metadata and configurations for Safebreach labs and AWS resources 
in the scope of impact for SafeBreach MCP Servergi.
'''
import json, os

safebreach_envs = {
    # Example configurations (uncomment and modify as needed):
    # "demo-console": {
    #     "url": "demo.safebreach.com", 
    #     "account": "1234567890",
    #     "secret_config": {
    #         "provider": "env_var",
    #         "parameter_name": "demo-console-apitoken"
    #     }
    # },
    # "example-console": {
    #     "url": "example.safebreach.com", 
    #     "account": "0987654321",
    #     "secret_config": {
    #         "provider": "env_var",
    #         "parameter_name": "example-console-apitoken"
    #     }
    # }
}

if os.environ.get('SAFEBREACH_ENVS_FILE'):
    # Load environments metadata from a JSON file if specified in environment variable
    # This allows for dynamic loading of environments without hardcoding them
    with open(os.environ['SAFEBREACH_ENVS_FILE']) as f:
        safebreach_envs.update(json.load(f))

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
    If the MCP Server is hosted in a console then it is a single-tenant environment so the function returns a local URL and port number for the internal endpoint
    like http://127.0.1:3400 . Otherwise, the MCP Server is hosted in a multi-tenant environment so the function returns the URL from the environments metadata.
    
    Args:
        console: Console name (e.g., 'demo-console', 'example-console')
        endpoint: Endpoint name can only be one of 'data', 'config', 'moves', 'queue', 'siem'

    Returns:
        Internal base URL as a string
    """

    env_var_name = f'{endpoint.upper()}_URL'
    url = os.getenv(env_var_name)

    if url:
        # Returning a URL for accessing the SafeBreach API from within the console
        return url
    
    # Returning a URL for accessing the SafeBreach API from outside the console
    url = f"https://{get_environment_by_name(console)['url']}"
    return url

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