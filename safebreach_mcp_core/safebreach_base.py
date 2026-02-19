"""
SafeBreach MCP Base Server

Base class for all SafeBreach MCP servers providing common functionality.
"""

import asyncio
import contextvars
import json
import logging
import os
import sys
import time
import uuid
from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from .cache_config import is_caching_enabled
from .safebreach_cache import SafeBreachCache
# FastAPI imports - only needed for external connections
try:
    from fastapi import Request
    from fastapi.responses import JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    Request = None
    JSONResponse = None
# Add the parent directory to sys.path to import the hotfix module
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
from mcp_server_bug_423_hotfix import apply_patch
from .safebreach_auth import SafeBreachAuth

logger = logging.getLogger(__name__)

# Concurrency limiter state — shared across all server instances
_mcp_session_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('mcp_session_id', default=None)
# Stores (semaphore, creation_timestamp) tuples to enable stale entry cleanup
_session_semaphores: Dict[str, tuple[asyncio.Semaphore, float]] = {}
_concurrency_limit = int(os.environ.get('SAFEBREACH_MCP_CONCURRENCY_LIMIT', '2'))
_SEMAPHORE_MAX_AGE = 3600  # 1 hour — stale semaphores are cleaned up after this


async def _cleanup_stale_semaphores() -> None:
    """Periodically remove SSE session semaphores older than _SEMAPHORE_MAX_AGE."""
    while True:
        await asyncio.sleep(600)  # Run every 10 minutes
        now = time.time()
        stale = [
            sid for sid, (_, created) in _session_semaphores.items()
            if now - created > _SEMAPHORE_MAX_AGE
        ]
        for sid in stale:
            _session_semaphores.pop(sid, None)
        if stale:
            logger.info(f"🧹 Cleaned up {len(stale)} stale SSE semaphore(s), {len(_session_semaphores)} remaining")


class SafeBreachMCPBase:
    """Base class for SafeBreach MCP servers."""
    
    def __init__(self, server_name: str, description: str = ""):
        """
        Initialize the base MCP server.
        
        Args:
            server_name: Name of the MCP server
            description: Description of the server
        """
        self.server_name = server_name
        self.description = description
        
        # Get base URL from environment variable, default to "/"
        self.base_url = os.environ.get('SAFEBREACH_MCP_BASE_URL', '/').rstrip('/')
        if self.base_url == '':
            self.base_url = '/'
        
        self.mcp = FastMCP(server_name)
        self.auth = SafeBreachAuth()
        self._cache = SafeBreachCache(name=f"{server_name}_base", maxsize=10, ttl=3600)
    
    def get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get data from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached data if available and not expired, None otherwise
        """
        if not is_caching_enabled():
            return None
        return self._cache.get(key)

    def set_cache(self, key: str, data: Dict[str, Any]) -> None:
        """
        Set data in cache.

        Args:
            key: Cache key
            data: Data to cache
        """
        if not is_caching_enabled():
            return
        self._cache.set(key, data)

    def clear_cache(self) -> None:
        """Clear all cache data."""
        self._cache.clear()
    
    async def run_server(self, port: int = 8000, host: str = "127.0.0.1", allow_external: bool = False) -> None:
        """
        Run the MCP server.
        
        Args:
            port: Port number to run the server on
            host: Host to bind to (default: 127.0.0.1)
            allow_external: Whether to allow external connections (default: False)
        """
        import uvicorn
        apply_patch()  # Apply MCP initialization patch
        
        # Determine bind address based on configuration
        bind_host = self._determine_bind_host(host, allow_external)
        
        # Get the Starlette app from FastMCP
        mcp_app = self.mcp.sse_app()
        
        # Create the main app and mount the MCP app at the base URL
        if self.base_url != '/':
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse
            from starlette.routing import Mount
            
            app = Starlette()
            app.mount(self.base_url, mcp_app)
            
            logger.info(f"🔗 MCP server mounted at base URL: {self.base_url}")
            logger.info(f"📡 SSE endpoint will be available at: {self.base_url}/sse")
        else:
            app = mcp_app
            logger.info("🔗 MCP server running at root URL: /")
            logger.info("📡 SSE endpoint available at: /sse")
        
        # Wrap with authentication for external connections
        if allow_external:
            logger.info("Adding ASGI authentication wrapper for external connections")
            app = self._create_authenticated_asgi_app(app)
            self._log_external_binding_warning(port)
        else:
            logger.info("🏠 Local-only server - no authentication wrapper applied")

        # Wrap with concurrency limiter (applies to all servers)
        app = self._create_concurrency_limited_app(app)
        logger.info(f"🔒 Concurrency limiter enabled: max {_concurrency_limit} concurrent requests per session")

        # Start background cleanup for stale SSE semaphores
        cleanup_task = asyncio.create_task(_cleanup_stale_semaphores())

        config = uvicorn.Config(app=app, host=bind_host, port=port, log_level="info")
        server = uvicorn.Server(config)
        try:
            await server.serve()
        finally:
            cleanup_task.cancel()
    
    def _determine_bind_host(self, host: str, allow_external: bool) -> str:
        """Determine the appropriate bind host based on configuration."""
        if allow_external:
            return "0.0.0.0"  # Bind to all interfaces
        return host  # Default to provided host (typically 127.0.0.1)
    
    def _create_authenticated_asgi_app(self, original_app):
        """Create an ASGI application that handles authentication before delegating to the MCP app."""
        auth_token = os.environ.get('SAFEBREACH_MCP_AUTH_TOKEN')
        if not auth_token:
            raise ValueError("SAFEBREACH_MCP_AUTH_TOKEN environment variable required for external connections")
        
        expected_auth = f"Bearer {auth_token}"
        
        async def authenticated_asgi_app(scope, receive, send):
            # Only handle HTTP requests; pass through other types (like websockets)
            if scope["type"] != "http":
                return await original_app(scope, receive, send)
            
            # Extract client information
            client_host = "unknown"
            if scope.get("client"):
                client_host = scope["client"][0]
            
            # Extract request path and method
            path = scope.get("path", "/")
            method = scope.get("method", "GET")
            
            # Handle OAuth discovery and registration endpoints for mcp-remote compatibility
            # These endpoints must be publicly accessible for OAuth flow to work
            oauth_discovery_paths = ["/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server/sse"]
            if path in oauth_discovery_paths:
                logger.info(f"🔍 OAuth discovery request: {path} from {client_host}")
                
                # Get server info from ASGI scope
                server_name = scope.get("server", ["1.1.1.1", 8001])[0]
                server_port = scope.get("server", ["1.1.1.1", 8001])[1]
                
                # Use base URL for endpoints when configured
                base_path = self.base_url if self.base_url != '/' else ''
                
                # Provide complete OAuth metadata for mcp-remote compatibility
                # Note: OAuth discovery endpoints are publicly accessible by design
                oauth_response = {
                    "issuer": f"http://{server_name}:{server_port}{base_path}",
                    "authorization_endpoint": f"http://{server_name}:{server_port}{base_path}/auth",
                    "token_endpoint": f"http://{server_name}:{server_port}{base_path}/token",
                    "registration_endpoint": f"http://{server_name}:{server_port}{base_path}/register",
                    "resource": f"http://{server_name}:{server_port}{base_path}/sse",
                    "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code"],
                    "scopes_supported": ["mcp"],
                    "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
                    "code_challenge_methods_supported": ["S256"],
                    "registration_endpoint_auth_methods_supported": ["none"]
                }
                response_body = json.dumps(oauth_response).encode()
                logger.info(f"📋 Providing OAuth discovery to {client_host} (public endpoint)")
                await send({
                    "type": "http.response.start", 
                    "status": 200,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(response_body)).encode()],
                        [b"access-control-allow-origin", b"*"],
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": response_body,
                })
                return
            
            # Handle OAuth client registration endpoint - check both root and base URL paths
            register_paths = ["/register"]
            if self.base_url != '/':
                register_paths.append(f"{self.base_url}/register")
            
            if path in register_paths and method == "POST":
                logger.info(f"🔧 OAuth client registration request from {client_host}")
                
                # Get server info
                server_name = scope.get("server", ["1.1.1.1", 8001])[0]
                server_port = scope.get("server", ["1.1.1.1", 8001])[1] 
                base_path = self.base_url if self.base_url != '/' else ''
                
                # Generate a complete client registration response
                # For mcp-remote, we need to provide all required OAuth 2.0 fields
                registration_response = {
                    "client_id": "mcp-remote-client",
                    "client_secret": "not-required-for-pkce",
                    "registration_access_token": "not-used",
                    "registration_client_uri": f"http://{server_name}:{server_port}{base_path}/register/mcp-remote-client",
                    "client_id_issued_at": int(time.time()),
                    "client_secret_expires_at": 0,  # Never expires
                    "response_types": ["code"],
                    "grant_types": ["authorization_code"],
                    "token_endpoint_auth_method": "none",  # PKCE doesn't require client secret
                    "redirect_uris": ["http://localhost:4195/callback"],  # Required field for OAuth 2.0
                    "scope": "mcp"
                }
                response_body = json.dumps(registration_response).encode()
                logger.info(f"📝 Providing OAuth client registration to {client_host} (public endpoint)")
                await send({
                    "type": "http.response.start",
                    "status": 201,  # 201 Created for successful registration
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(response_body)).encode()],
                        [b"access-control-allow-origin", b"*"],
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": response_body,
                })
                return
            
            # Handle OAuth authorization endpoint (secure authorization code flow)
            auth_paths = ["/auth"]
            if self.base_url != '/':
                auth_paths.append(f"{self.base_url}/auth")
            
            auth_path_match = any(path.startswith(auth_path) for auth_path in auth_paths)
            if auth_path_match:
                logger.info(f"🔐 OAuth authorization request from {client_host}")
                
                # SECURITY: For OAuth authorization, we require the correct Bearer token
                # This prevents unauthorized token generation
                headers = dict(scope.get("headers", []))
                auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
                
                if auth_header != expected_auth:
                    logger.warning(f"🚫 OAuth authorization denied - invalid Bearer token from {client_host}")
                    error_response = {"error": "access_denied", "error_description": "Valid Bearer token required for OAuth authorization"}
                    response_body = json.dumps(error_response).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(response_body)).encode()],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": response_body,
                    })
                    return
                
                # Parse query parameters
                from urllib.parse import parse_qs, urlencode
                query_params = parse_qs(scope.get("query_string", b"").decode())
                
                # Extract OAuth parameters
                redirect_uri = query_params.get("redirect_uri", [""])[0]
                state = query_params.get("state", [""])[0]
                
                if redirect_uri:
                    # Generate an authorization code (simple implementation)
                    import secrets
                    auth_code = secrets.token_urlsafe(32)
                    
                    # Build redirect URL with authorization code
                    redirect_params = {
                        "code": auth_code,
                        "state": state
                    }
                    redirect_url = f"{redirect_uri}?{urlencode(redirect_params)}"
                    
                    logger.info(f"🎫 OAuth authorization approved for authenticated client {client_host}")
                    logger.info(f"🎫 Redirecting to {redirect_url}")
                    
                    # Send redirect response
                    await send({
                        "type": "http.response.start",
                        "status": 302,
                        "headers": [
                            [b"location", redirect_url.encode()],
                            [b"access-control-allow-origin", b"*"],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": b"",
                    })
                    return
                else:
                    # No redirect_uri provided, return error
                    error_response = {"error": "invalid_request", "error_description": "redirect_uri is required"}
                    response_body = json.dumps(error_response).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 400,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(response_body)).encode()],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": response_body,
                    })
                    return
            
            # Handle OAuth token endpoint  
            token_paths = ["/token"]
            if self.base_url != '/':
                token_paths.append(f"{self.base_url}/token")
                
            if path in token_paths and method == "POST":
                logger.info(f"🎟️ OAuth token request from {client_host}")
                
                # SECURITY: For OAuth token exchange, we require the correct Bearer token
                # This ensures only clients with valid tokens can exchange for OAuth tokens
                headers = dict(scope.get("headers", []))
                auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
                
                if auth_header != expected_auth:
                    logger.warning(f"🚫 OAuth token exchange denied - invalid Bearer token from {client_host}")
                    error_response = {"error": "invalid_client", "error_description": "Valid Bearer token required for token exchange"}
                    response_body = json.dumps(error_response).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(response_body)).encode()],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": response_body,
                    })
                    return
                
                # Provide the configured Bearer token (token exchange)
                token_response = {
                    "access_token": os.environ.get('SAFEBREACH_MCP_AUTH_TOKEN', 'default-token'),
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "scope": "mcp"
                }
                response_body = json.dumps(token_response).encode()
                logger.info(f"🔑 OAuth token exchange approved for authenticated client {client_host}")
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(response_body)).encode()],
                        [b"access-control-allow-origin", b"*"],
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": response_body,
                })
                return
            
            # Allow localhost connections without authentication  
            if client_host in ["127.0.0.1", "::1"]:
                logger.info(f"🏠 Localhost connection from {client_host} - bypassing auth - PATH: {path}")
                return await original_app(scope, receive, send)
            
            # Check Authorization header for external connections
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
            
            if auth_header != expected_auth:
                logger.warning(f"🚫 Unauthorized external connection from {client_host}: {auth_header[:20]}...")
                # Send 401 Unauthorized response
                response_body = b'{"error": "Unauthorized", "message": "Bearer token required"}'
                await send({
                    "type": "http.response.start", 
                    "status": 401,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(response_body)).encode()],
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": response_body,
                })
                return
            
            logger.info(f"✅ Authorized external connection from {client_host}")
            # Pass through to the MCP application
            return await original_app(scope, receive, send)
        
        return authenticated_asgi_app
    
    def _log_external_binding_warning(self, port: int) -> None:
        """Log security warning when binding to external interfaces."""
        logger.warning(f"🚨 SECURITY WARNING: Server binding to 0.0.0.0:{port} - accessible from external networks!")
        logger.warning("🔒 HTTP Authorization required for external connections")
        logger.warning("🔑 Set SAFEBREACH_MCP_AUTH_TOKEN environment variable for authentication")

    def _create_concurrency_limited_app(self, original_app):
        """Create an ASGI wrapper that limits concurrent requests per SSE session."""

        async def concurrency_limited_app(scope, receive, send):
            if scope["type"] != "http":
                return await original_app(scope, receive, send)

            path = scope.get("path", "/")

            # SSE connection establishment — assign a new session ID
            if path.endswith("/sse"):
                session_id = str(uuid.uuid4())
                _mcp_session_id.set(session_id)
                _session_semaphores[session_id] = (asyncio.Semaphore(_concurrency_limit), time.time())
                logger.info(f"🆔 New SSE session: {session_id[:8]}...")

                async def cleanup_send(message):
                    await send(message)
                    # Clean up semaphore when SSE connection ends
                    if message.get("type") == "http.response.body" and not message.get("more_body", False):
                        _session_semaphores.pop(session_id, None)
                        logger.info(f"🧹 Cleaned up session: {session_id[:8]}...")

                return await original_app(scope, receive, cleanup_send)

            # Message endpoint — apply concurrency limit
            if path.endswith("/messages/") or path.endswith("/messages"):
                session_id = _mcp_session_id.get()
                if session_id and session_id in _session_semaphores:
                    sem, _ = _session_semaphores[session_id]
                    if sem.locked() and sem._value == 0:  # noqa: SLF001
                        logger.warning(
                            f"⚠️ Concurrency limit ({_concurrency_limit}) exceeded for session {session_id[:8]}..."
                        )
                        response_body = json.dumps({
                            "error": "Too Many Requests",
                            "message": f"Concurrency limit of {_concurrency_limit} exceeded. Please retry.",
                            "retry_after": 5
                        }).encode()
                        await send({
                            "type": "http.response.start",
                            "status": 429,
                            "headers": [
                                [b"content-type", b"application/json"],
                                [b"content-length", str(len(response_body)).encode()],
                                [b"retry-after", b"5"],
                            ],
                        })
                        await send({
                            "type": "http.response.body",
                            "body": response_body,
                        })
                        return

                    async with sem:
                        return await original_app(scope, receive, send)

                # No session tracking — pass through (shouldn't happen in normal flow)
                return await original_app(scope, receive, send)

            # All other paths — pass through without limiting
            return await original_app(scope, receive, send)

        return concurrency_limited_app

    def create_main_function(self, port: int = 8000):
        """
        Create a main function for the server.
        
        Args:
            port: Port number to run the server on
        
        Returns:
            Main function that can be used as an entry point
        """
        def main():
            asyncio.run(self.run_server(port))
        return main