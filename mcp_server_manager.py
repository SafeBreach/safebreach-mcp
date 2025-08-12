#!/usr/bin/env python3
"""
SafeBreach MCP Server Management API

A standalone Python API for programmatically managing multiple SafeBreach MCP server instances
with different configurations and environment variables.

This module provides programmatic control over SafeBreach MCP servers without affecting
the main package functionality. It allows starting multiple server instances with
isolated environment configurations.

Usage:
    from mcp_server_manager import MCPServerManager, ServerConfig
    
    manager = MCPServerManager()
    config = ServerConfig(
        server_type="data",
        port=8001,
        base_url="/api/mcp",
        environment_vars={"console1_apitoken": "token123"}
    )
    manager.start_server("instance1", config)
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import json
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ServerType(Enum):
    """Enumeration of available MCP server types."""
    CONFIG = "config"
    DATA = "data" 
    UTILITIES = "utilities"
    PLAYBOOK = "playbook"
    ALL = "all"  # For multi-server launcher

class ServerStatus(Enum):
    """Server instance status enumeration."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass
class ServerConfig:
    """Configuration for a SafeBreach MCP server instance."""
    server_type: ServerType
    port: int
    host: str = "127.0.0.1"
    base_url: str = "/"
    allow_external: bool = False
    auth_token: Optional[str] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    custom_args: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Post-initialization validation."""
        if isinstance(self.server_type, str):
            self.server_type = ServerType(self.server_type)
        
        if self.port < 1024 or self.port > 65535:
            raise ValueError(f"Port {self.port} must be between 1024 and 65535")
        
        # Ensure base_url starts with / and remove trailing slash
        if not self.base_url.startswith('/'):
            self.base_url = '/' + self.base_url
        self.base_url = self.base_url.rstrip('/')
        if self.base_url == '':
            self.base_url = '/'

@dataclass 
class ServerInstance:
    """Represents a running MCP server instance."""
    instance_id: str
    config: ServerConfig
    process: Optional[subprocess.Popen] = None
    status: ServerStatus = ServerStatus.STOPPED
    start_time: Optional[float] = None
    stop_time: Optional[float] = None
    pid: Optional[int] = None
    env_file: Optional[str] = None  # Path to temporary environment file
    
    def __post_init__(self):
        """Post-initialization setup."""
        if self.process and self.process.pid:
            self.pid = self.process.pid

class MCPServerManager:
    """
    Main class for managing multiple SafeBreach MCP server instances.
    
    This manager allows you to:
    - Start multiple server instances with different configurations
    - Manage environment variable isolation per instance
    - Monitor server health and status
    - Stop and restart server instances
    - Query server information and logs
    """
    
    def __init__(self):
        """Initialize the MCP Server Manager."""
        self.instances: Dict[str, ServerInstance] = {}
        self.port_registry: Dict[int, str] = {}  # port -> instance_id mapping
        self._shutdown_event = threading.Event()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("SafeBreach MCP Server Manager initialized")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down all servers...")
        self.stop_all_servers()
        self._shutdown_event.set()
    
    def _get_server_command(self, config: ServerConfig) -> List[str]:
        """Build the command to start a specific server type."""
        base_cmd = ["uv", "run"]
        
        if config.server_type == ServerType.ALL:
            cmd = base_cmd + ["python", "start_all_servers.py"]
            if config.allow_external:
                cmd.append("--external")
            if config.host != "127.0.0.1":
                cmd.extend(["--host", config.host])
            if config.base_url != "/":
                cmd.extend(["--base-url", config.base_url])
        else:
            # Individual server commands
            server_modules = {
                ServerType.CONFIG: "safebreach_mcp_config.config_server",
                ServerType.DATA: "safebreach_mcp_data.data_server", 
                ServerType.UTILITIES: "safebreach_mcp_utilities.utilities_server",
                ServerType.PLAYBOOK: "safebreach_mcp_playbook.playbook_server"
            }
            cmd = base_cmd + ["-m", server_modules[config.server_type]]
        
        # Add any custom arguments
        cmd.extend(config.custom_args)
        
        return cmd
    
    def _prepare_environment(self, config: ServerConfig) -> Dict[str, str]:
        """Prepare environment variables for the server instance."""
        env = os.environ.copy()
        
        # Set base SafeBreach MCP environment variables
        if config.base_url != "/":
            env['SAFEBREACH_MCP_BASE_URL'] = config.base_url
        
        if config.allow_external:
            env['SAFEBREACH_MCP_ALLOW_EXTERNAL'] = 'true'
            if config.auth_token:
                env['SAFEBREACH_MCP_AUTH_TOKEN'] = config.auth_token
            else:
                logger.warning(f"External access enabled but no auth token provided for {config.server_type}")
        
        if config.host != "127.0.0.1":
            env['SAFEBREACH_MCP_BIND_HOST'] = config.host
        
        # Set server-specific external flags
        if config.allow_external and config.server_type != ServerType.ALL:
            env[f'SAFEBREACH_MCP_{config.server_type.value.upper()}_EXTERNAL'] = 'true'
        
        # Add custom environment variables
        env.update(config.environment_vars)
        
        return env
    
    def _create_temp_env_file(self, env_vars: Dict[str, str]) -> str:
        """Create a temporary environment file for the server instance."""
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False)
        
        for key, value in env_vars.items():
            temp_file.write(f"{key}={value}\n")
        
        temp_file.close()
        return temp_file.name
    
    def _check_port_availability(self, port: int, instance_id: str) -> bool:
        """Check if a port is available for use."""
        if port in self.port_registry:
            existing_instance = self.port_registry[port]
            if existing_instance != instance_id:
                logger.error(f"Port {port} is already in use by instance {existing_instance}")
                return False
        return True
    
    def start_server(self, instance_id: str, config: ServerConfig) -> bool:
        """
        Start a new MCP server instance with the given configuration.
        
        Args:
            instance_id: Unique identifier for this server instance
            config: Server configuration
            
        Returns:
            bool: True if server started successfully, False otherwise
        """
        try:
            # Validate instance ID
            if instance_id in self.instances:
                logger.error(f"Instance {instance_id} already exists")
                return False
            
            # Check port availability
            if not self._check_port_availability(config.port, instance_id):
                return False
            
            # Prepare environment
            env = self._prepare_environment(config)
            
            # Create environment file
            env_file = self._create_temp_env_file(env)
            
            # Build command
            cmd = self._get_server_command(config)
            
            logger.info(f"Starting server instance {instance_id} ({config.server_type.value}) on port {config.port}")
            logger.debug(f"Command: {' '.join(cmd)}")
            logger.debug(f"Environment file: {env_file}")
            
            # Start the process
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Create server instance
            instance = ServerInstance(
                instance_id=instance_id,
                config=config,
                process=process,
                status=ServerStatus.STARTING,
                start_time=time.time(),
                pid=process.pid,
                env_file=env_file
            )
            
            # Register the instance
            self.instances[instance_id] = instance
            self.port_registry[config.port] = instance_id
            
            # Wait a moment and check if process started successfully
            time.sleep(1)
            if process.poll() is None:
                instance.status = ServerStatus.RUNNING
                logger.info(f"✅ Server instance {instance_id} started successfully (PID: {process.pid})")
                return True
            else:
                # Process failed to start
                instance.status = ServerStatus.FAILED
                stdout, stderr = process.communicate(timeout=5)
                logger.error(f"❌ Server instance {instance_id} failed to start")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                self._cleanup_instance(instance_id)
                return False
                
        except Exception as e:
            logger.error(f"Error starting server instance {instance_id}: {e}")
            if instance_id in self.instances:
                self._cleanup_instance(instance_id)
            return False
    
    def stop_server(self, instance_id: str, timeout: int = 10) -> bool:
        """
        Stop a specific server instance.
        
        Args:
            instance_id: ID of the instance to stop
            timeout: Maximum time to wait for graceful shutdown
            
        Returns:
            bool: True if server stopped successfully, False otherwise
        """
        if instance_id not in self.instances:
            logger.error(f"Instance {instance_id} not found")
            return False
        
        instance = self.instances[instance_id]
        
        if instance.status == ServerStatus.STOPPED:
            logger.info(f"Instance {instance_id} is already stopped")
            return True
        
        logger.info(f"Stopping server instance {instance_id}...")
        instance.status = ServerStatus.STOPPING
        
        try:
            if instance.process and instance.process.poll() is None:
                # Try graceful shutdown first
                instance.process.terminate()
                
                # Wait for graceful shutdown
                try:
                    instance.process.wait(timeout=timeout)
                    logger.info(f"✅ Server instance {instance_id} stopped gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown failed
                    logger.warning(f"Graceful shutdown timeout for {instance_id}, forcing termination")
                    instance.process.kill()
                    instance.process.wait()
                    logger.info(f"✅ Server instance {instance_id} force stopped")
            
            instance.status = ServerStatus.STOPPED
            instance.stop_time = time.time()
            self._cleanup_instance(instance_id)
            return True
            
        except Exception as e:
            logger.error(f"Error stopping server instance {instance_id}: {e}")
            instance.status = ServerStatus.FAILED
            return False
    
    def _cleanup_instance(self, instance_id: str):
        """Clean up resources for a server instance."""
        if instance_id not in self.instances:
            return
        
        instance = self.instances[instance_id]
        
        # Remove from port registry
        if instance.config.port in self.port_registry:
            del self.port_registry[instance.config.port]
        
        # Clean up temporary environment file
        if instance.env_file and os.path.exists(instance.env_file):
            try:
                os.unlink(instance.env_file)
            except OSError as e:
                logger.warning(f"Failed to remove environment file {instance.env_file}: {e}")
        
        # Remove from instances
        del self.instances[instance_id]
    
    def get_server_status(self, instance_id: str) -> Optional[ServerStatus]:
        """Get the current status of a server instance."""
        if instance_id not in self.instances:
            return None
        
        instance = self.instances[instance_id]
        
        # Update status based on process state
        if instance.process:
            if instance.process.poll() is None:
                instance.status = ServerStatus.RUNNING
            else:
                instance.status = ServerStatus.STOPPED
        
        return instance.status
    
    def get_server_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a server instance."""
        if instance_id not in self.instances:
            return None
        
        instance = self.instances[instance_id]
        status = self.get_server_status(instance_id)
        
        info = {
            "instance_id": instance_id,
            "server_type": instance.config.server_type.value,
            "port": instance.config.port,
            "host": instance.config.host,
            "base_url": instance.config.base_url,
            "allow_external": instance.config.allow_external,
            "status": status.value if status else "unknown",
            "pid": instance.pid,
            "start_time": instance.start_time,
            "stop_time": instance.stop_time,
            "uptime": time.time() - instance.start_time if instance.start_time and status == ServerStatus.RUNNING else None,
            "endpoint": f"http://{instance.config.host}:{instance.config.port}{instance.config.base_url}/sse" if instance.config.base_url != "/" else f"http://{instance.config.host}:{instance.config.port}/sse"
        }
        
        return info
    
    def list_servers(self) -> List[Dict[str, Any]]:
        """List all server instances with their information."""
        return [self.get_server_info(instance_id) for instance_id in self.instances.keys()]
    
    def stop_all_servers(self, timeout: int = 10) -> bool:
        """Stop all running server instances."""
        logger.info("Stopping all server instances...")
        success = True
        
        for instance_id in list(self.instances.keys()):
            if not self.stop_server(instance_id, timeout):
                success = False
        
        logger.info("All servers stopped" if success else "Some servers failed to stop cleanly")
        return success
    
    def restart_server(self, instance_id: str, timeout: int = 10) -> bool:
        """Restart a specific server instance."""
        if instance_id not in self.instances:
            logger.error(f"Instance {instance_id} not found")
            return False
        
        # Get the current configuration
        config = self.instances[instance_id].config
        
        # Stop the server
        if not self.stop_server(instance_id, timeout):
            return False
        
        # Start the server with the same configuration
        return self.start_server(instance_id, config)
    
    def get_server_logs(self, instance_id: str, lines: int = 100) -> Optional[Dict[str, str]]:
        """Get recent logs from a server instance."""
        if instance_id not in self.instances:
            return None
        
        instance = self.instances[instance_id]
        
        if not instance.process:
            return {"error": "No process found for instance"}
        
        try:
            # This is a simple implementation - in production you might want to use proper log files
            stdout_data = ""
            stderr_data = ""
            
            if instance.process.stdout:
                # Note: This is a simplified approach. For production, you'd want proper log management
                stdout_data = f"Process PID: {instance.pid}\nStatus: {instance.status.value}\n"
            
            if instance.process.stderr:
                stderr_data = f"Process started at: {instance.start_time}\n"
            
            return {
                "stdout": stdout_data,
                "stderr": stderr_data
            }
            
        except Exception as e:
            return {"error": f"Failed to get logs: {e}"}

def main():
    """Example usage of the MCP Server Manager."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SafeBreach MCP Server Manager")
    parser.add_argument("--example", action="store_true", help="Run example configuration")
    args = parser.parse_args()
    
    if args.example:
        # Example usage
        manager = MCPServerManager()
        
        try:
            # Start multiple server instances with different configurations
            configs = [
                ServerConfig(
                    server_type=ServerType.CONFIG,
                    port=8100,
                    base_url="/api/v1/config",
                    environment_vars={"demo_apitoken": "config-token-123"}
                ),
                ServerConfig(
                    server_type=ServerType.DATA,
                    port=8101,
                    base_url="/api/v1/data", 
                    environment_vars={"demo_apitoken": "data-token-456"}
                ),
                ServerConfig(
                    server_type=ServerType.UTILITIES,
                    port=8102,
                    base_url="/api/v1/utils",
                    environment_vars={}
                )
            ]
            
            # Start the servers
            for i, config in enumerate(configs):
                instance_id = f"instance-{i+1}"
                if manager.start_server(instance_id, config):
                    info = manager.get_server_info(instance_id)
                    print(f"Started: {info['endpoint']}")
                
            # List all running servers
            print("\nRunning servers:")
            for server_info in manager.list_servers():
                print(f"  - {server_info['instance_id']}: {server_info['endpoint']} (Status: {server_info['status']})")
            
            # Keep servers running
            input("Press Enter to stop all servers...\n")
            
        finally:
            manager.stop_all_servers()
    else:
        print("Use --example to run example configuration")

if __name__ == "__main__":
    main()