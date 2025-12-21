"""
SafeBreach Authentication Module

Provides centralized authentication and API communication for all MCP servers.
"""

import requests
import time
from typing import Dict, Optional, Any
from .cache_config import is_caching_enabled
from .secret_utils import get_secret_for_console
from .environments_metadata import get_environment_by_name

class SafeBreachAuth:
    """Centralized authentication and API communication for SafeBreach."""
    
    def __init__(self):
        self._token_cache = {}
        self._session = requests.Session()
        self._session.timeout = 120
    
    def get_token(self, console: str) -> str:
        """Get API token for the specified console."""
        if is_caching_enabled() and console in self._token_cache:
            return self._token_cache[console]
        token = get_secret_for_console(console)
        if is_caching_enabled():
            self._token_cache[console] = token
        return token
    
    def get_headers(self, console: str) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            'Authorization': f'Bearer {self.get_token(console)}',
            'Content-Type': 'application/json'
        }
    
    def get_base_url(self, console: str) -> str:
        """Get base URL for the specified console."""
        env = get_environment_by_name(console)
        return f"https://{env['url']}/api"
    
    def make_request(self, endpoint: str, console: str = "default", params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make authenticated API request to SafeBreach.
        
        Args:
            console: Console name
            endpoint: API endpoint (e.g., '/config/v1/simulators')
            params: Optional query parameters
        
        Returns:
            Dict containing the API response
        """
        url = f"{self.get_base_url(console)}{endpoint}"
        headers = self.get_headers(console)
        
        try:
            response = self._session.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")
    
    def clear_cache(self):
        """Clear authentication cache."""
        self._token_cache.clear()