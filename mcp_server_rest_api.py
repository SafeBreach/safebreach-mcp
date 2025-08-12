#!/usr/bin/env python3
"""
SafeBreach MCP Server REST API

A REST API wrapper around the MCP Server Manager for HTTP-based server management.
This provides HTTP endpoints for managing SafeBreach MCP servers programmatically.

Usage:
    # Start the REST API server
    python mcp_server_rest_api.py --port 9000
    
    # Example API calls:
    POST /servers - Create and start a new server instance
    GET /servers - List all server instances
    GET /servers/{instance_id} - Get specific server info
    DELETE /servers/{instance_id} - Stop and remove a server instance
    POST /servers/{instance_id}/restart - Restart a server instance
"""

import json
import logging
import sys
from typing import Dict, Any, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from contextlib import asynccontextmanager

# Import our MCP Server Manager
from mcp_server_manager import MCPServerManager, ServerConfig, ServerType, ServerStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global server manager instance
server_manager: Optional[MCPServerManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    global server_manager
    
    # Startup
    logger.info("Starting MCP Server REST API...")
    server_manager = MCPServerManager()
    yield
    
    # Shutdown
    logger.info("Shutting down MCP Server REST API...")
    if server_manager:
        server_manager.stop_all_servers()

# FastAPI app with lifespan management
app = FastAPI(
    title="SafeBreach MCP Server Management API",
    description="REST API for managing SafeBreach MCP server instances",
    version="1.0.0",
    lifespan=lifespan
)

# Pydantic models for request/response validation

class ServerConfigRequest(BaseModel):
    """Request model for server configuration."""
    server_type: str = Field(..., description="Server type: config, data, utilities, playbook, or all")
    port: int = Field(..., gt=1023, lt=65536, description="Port number (1024-65535)")
    host: str = Field(default="127.0.0.1", description="Host address to bind to")
    base_url: str = Field(default="/", description="Base URL path for endpoints")
    allow_external: bool = Field(default=False, description="Allow external connections")
    auth_token: Optional[str] = Field(default=None, description="Authentication token for external connections")
    environment_vars: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    custom_args: list = Field(default_factory=list, description="Custom command-line arguments")
    
    @validator('server_type')
    def validate_server_type(cls, v):
        """Validate server type."""
        valid_types = [t.value for t in ServerType]
        if v not in valid_types:
            raise ValueError(f"server_type must be one of: {valid_types}")
        return v
    
    @validator('base_url')
    def validate_base_url(cls, v):
        """Validate and normalize base URL."""
        if not v.startswith('/'):
            v = '/' + v
        v = v.rstrip('/')
        if v == '':
            v = '/'
        return v

class ServerResponse(BaseModel):
    """Response model for server information."""
    instance_id: str
    server_type: str
    port: int
    host: str
    base_url: str
    allow_external: bool
    status: str
    pid: Optional[int]
    start_time: Optional[float]
    stop_time: Optional[float]
    uptime: Optional[float]
    endpoint: str

class APIResponse(BaseModel):
    """Generic API response model."""
    success: bool
    message: str
    data: Any = None

# API Endpoints

@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "service": "SafeBreach MCP Server Management API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "servers": "/servers",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    running_servers = len([s for s in server_manager.list_servers() if s["status"] == "running"])
    
    return {
        "status": "healthy",
        "total_servers": len(server_manager.instances),
        "running_servers": running_servers,
        "timestamp": __import__('time').time()
    }

@app.post("/servers/{instance_id}", response_model=APIResponse)
async def create_server(instance_id: str, config: ServerConfigRequest):
    """Create and start a new server instance."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    try:
        # Convert request to ServerConfig
        server_config = ServerConfig(
            server_type=ServerType(config.server_type),
            port=config.port,
            host=config.host,
            base_url=config.base_url,
            allow_external=config.allow_external,
            auth_token=config.auth_token,
            environment_vars=config.environment_vars,
            custom_args=config.custom_args
        )
        
        # Start the server
        success = server_manager.start_server(instance_id, server_config)
        
        if success:
            server_info = server_manager.get_server_info(instance_id)
            return APIResponse(
                success=True,
                message=f"Server instance {instance_id} started successfully",
                data=server_info
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to start server instance {instance_id}"
            )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating server {instance_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.get("/servers", response_model=APIResponse)
async def list_servers():
    """List all server instances."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    try:
        servers = server_manager.list_servers()
        return APIResponse(
            success=True,
            message=f"Found {len(servers)} server instances",
            data=servers
        )
    except Exception as e:
        logger.error(f"Error listing servers: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.get("/servers/{instance_id}", response_model=APIResponse)
async def get_server(instance_id: str):
    """Get information about a specific server instance."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    server_info = server_manager.get_server_info(instance_id)
    
    if server_info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Server instance {instance_id} not found"
        )
    
    return APIResponse(
        success=True,
        message=f"Server instance {instance_id} information",
        data=server_info
    )

@app.delete("/servers/{instance_id}", response_model=APIResponse)
async def stop_server(instance_id: str, timeout: int = 10):
    """Stop and remove a server instance."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    if instance_id not in server_manager.instances:
        raise HTTPException(
            status_code=404,
            detail=f"Server instance {instance_id} not found"
        )
    
    try:
        success = server_manager.stop_server(instance_id, timeout)
        
        if success:
            return APIResponse(
                success=True,
                message=f"Server instance {instance_id} stopped successfully"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to stop server instance {instance_id}"
            )
            
    except Exception as e:
        logger.error(f"Error stopping server {instance_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.post("/servers/{instance_id}/restart", response_model=APIResponse)
async def restart_server(instance_id: str, timeout: int = 10):
    """Restart a server instance."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    if instance_id not in server_manager.instances:
        raise HTTPException(
            status_code=404,
            detail=f"Server instance {instance_id} not found"
        )
    
    try:
        success = server_manager.restart_server(instance_id, timeout)
        
        if success:
            server_info = server_manager.get_server_info(instance_id)
            return APIResponse(
                success=True,
                message=f"Server instance {instance_id} restarted successfully",
                data=server_info
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to restart server instance {instance_id}"
            )
            
    except Exception as e:
        logger.error(f"Error restarting server {instance_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.get("/servers/{instance_id}/logs", response_model=APIResponse)
async def get_server_logs(instance_id: str, lines: int = 100):
    """Get logs from a server instance."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    if instance_id not in server_manager.instances:
        raise HTTPException(
            status_code=404,
            detail=f"Server instance {instance_id} not found"
        )
    
    try:
        logs = server_manager.get_server_logs(instance_id, lines)
        
        if logs and "error" in logs:
            raise HTTPException(status_code=500, detail=logs["error"])
        
        return APIResponse(
            success=True,
            message=f"Logs for server instance {instance_id}",
            data=logs
        )
        
    except Exception as e:
        logger.error(f"Error getting logs for {instance_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.delete("/servers", response_model=APIResponse)
async def stop_all_servers(timeout: int = 10):
    """Stop all server instances."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="Server manager not initialized")
    
    try:
        success = server_manager.stop_all_servers(timeout)
        
        return APIResponse(
            success=success,
            message="All servers stopped" if success else "Some servers failed to stop cleanly"
        )
        
    except Exception as e:
        logger.error(f"Error stopping all servers: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

# Custom exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail}
    )

def main():
    """Main entry point for the REST API server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SafeBreach MCP Server REST API")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the API server to")
    parser.add_argument("--port", type=int, default=9000, help="Port to bind the API server to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    
    args = parser.parse_args()
    
    logger.info(f"Starting SafeBreach MCP Server REST API on {args.host}:{args.port}")
    
    uvicorn.run(
        "mcp_server_rest_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )

if __name__ == "__main__":
    main()