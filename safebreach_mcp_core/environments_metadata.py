'''
SafeBreach Environments Configuration

This file contains metadata and configurations for Safebreach labs and AWS resources 
in the scope of impact for SafeBreach MCP Servergi.
'''
import json, os

safebreach_envs = {
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

if os.environ.get('SAFEBREACH_ENVS_FILE'):
    # Load environments metadata from a JSON file if specified in environment variable
    # This allows for dynamic loading of environments without hardcoding them
    with open(os.environ['SAFEBREACH_ENVS_FILE']) as f:
        safebreach_envs.update(json.load(f))

def get_environment_by_name(name: str) -> dict:
    """
    Get environment configuration by name.
    
    Args:
        name: Environment name
        
    Returns:
        Environment configuration dictionary
        
    Raises:
        ValueError: If environment not found
    """
    if name not in safebreach_envs:
        raise ValueError(f"Environment '{name}' not found. Available environments: {list(safebreach_envs.keys())}")
    return safebreach_envs[name]