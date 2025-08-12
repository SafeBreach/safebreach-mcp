# SafeBreach MCP Server Manager - API Documentation

This document provides comprehensive documentation and examples for using the SafeBreach MCP Server Manager API to programmatically manage multiple MCP server instances with different configurations.

## Table of Contents
- [Overview](#overview)
- [Basic Python API Usage](#basic-python-api-usage)
- [Advanced Configuration Examples](#advanced-configuration-examples)
- [REST API Usage](#rest-api-usage)
- [Integration Examples](#integration-examples)
- [Error Handling](#error-handling)

## Overview

The SafeBreach MCP Server Manager provides two main interfaces:

1. **Python API** (`mcp_server_manager.py`) - Direct programmatic control
2. **REST API** (`mcp_server_rest_api.py`) - HTTP-based management interface

### Key Features

- **Environment Variable Isolation** - Each server instance runs with its own environment
- **Multiple Server Types** - Support for config, data, utilities, playbook, and multi-server instances
- **Port Management** - Automatic port conflict detection and management
- **Lifecycle Management** - Start, stop, restart, and monitor server instances
- **Health Monitoring** - Real-time status checking and health management
- **External Access Support** - Configure servers for external connections with authentication

## Basic Python API Usage

### Simple Server Management

```python
#!/usr/bin/env python3
"""
Basic example of managing SafeBreach MCP servers programmatically.
"""

from mcp_server_manager import MCPServerManager, ServerConfig, ServerType

def basic_example():
    # Create a server manager instance
    manager = MCPServerManager()
    
    try:
        # Create server configurations
        config1 = ServerConfig(
            server_type=ServerType.CONFIG,
            port=8100,
            base_url="/api/v1/config",
            environment_vars={"demo_apitoken": "config-token-123"}
        )
        
        config2 = ServerConfig(
            server_type=ServerType.DATA,
            port=8101,
            base_url="/api/v1/data",
            environment_vars={"demo_apitoken": "data-token-456"}
        )
        
        # Start the servers
        print("Starting servers...")
        success1 = manager.start_server("config-instance", config1)
        success2 = manager.start_server("data-instance", config2)
        
        if success1 and success2:
            print("✅ All servers started successfully!")
            
            # List running servers
            servers = manager.list_servers()
            for server in servers:
                print(f"  - {server['instance_id']}: {server['endpoint']} (Status: {server['status']})")
            
            input("Press Enter to stop servers...")
        else:
            print("❌ Some servers failed to start")
    
    finally:
        # Always clean up
        manager.stop_all_servers()

if __name__ == "__main__":
    basic_example()
```

### Multiple Environment Configuration

```python
#!/usr/bin/env python3
"""
Example of running multiple server instances for different SafeBreach environments.
"""

from mcp_server_manager import MCPServerManager, ServerConfig, ServerType

def multi_environment_example():
    manager = MCPServerManager()
    
    # Define configurations for different environments
    environments = {
        "development": {
            "base_port": 8100,
            "base_url": "/dev/api",
            "tokens": {
                "dev_console_apitoken": "dev-token-123"
            }
        },
        "staging": {
            "base_port": 8200, 
            "base_url": "/staging/api",
            "tokens": {
                "staging_console_apitoken": "staging-token-456"
            }
        },
        "production": {
            "base_port": 8300,
            "base_url": "/prod/api", 
            "tokens": {
                "prod_console_apitoken": "prod-token-789"
            }
        }
    }
    
    try:
        # Start server instances for each environment
        for env_name, env_config in environments.items():
            for server_type in [ServerType.CONFIG, ServerType.DATA, ServerType.UTILITIES]:
                port_offset = {
                    ServerType.CONFIG: 0,
                    ServerType.DATA: 1, 
                    ServerType.UTILITIES: 2
                }[server_type]
                
                config = ServerConfig(
                    server_type=server_type,
                    port=env_config["base_port"] + port_offset,
                    base_url=f"{env_config['base_url']}/{server_type.value}",
                    environment_vars=env_config["tokens"]
                )
                
                instance_id = f"{env_name}-{server_type.value}"
                success = manager.start_server(instance_id, config)
                
                if success:
                    info = manager.get_server_info(instance_id)
                    print(f"✅ Started {instance_id}: {info['endpoint']}")
                else:
                    print(f"❌ Failed to start {instance_id}")
        
        print(f"\nTotal running servers: {len(manager.list_servers())}")
        input("Press Enter to stop all servers...")
    
    finally:
        manager.stop_all_servers()

if __name__ == "__main__":
    multi_environment_example()
```

## Advanced Configuration Examples

### External Access with Authentication

```python
#!/usr/bin/env python3
"""
Example of configuring servers with external access and authentication.
"""

from mcp_server_manager import MCPServerManager, ServerConfig, ServerType

def external_access_example():
    manager = MCPServerManager()
    
    # Configuration for external-facing servers
    external_config = ServerConfig(
        server_type=ServerType.ALL,  # Multi-server launcher
        port=8000,
        host="0.0.0.0",  # Bind to all interfaces
        base_url="/api/mcp",
        allow_external=True,
        auth_token="secure-external-token-123",
        environment_vars={
            # Multiple console tokens
            "console1_apitoken": "token1",
            "console2_apitoken": "token2",
            "console3_apitoken": "token3"
        }
    )
    
    try:
        success = manager.start_server("external-multi-server", external_config)
        
        if success:
            info = manager.get_server_info("external-multi-server")
            print(f"✅ External multi-server started: {info['endpoint']}")
            print(f"🔒 Authentication required with token: {external_config.auth_token}")
            print("🌐 Accessible from external networks")
            
            input("Press Enter to stop server...")
        else:
            print("❌ Failed to start external server")
    
    finally:
        manager.stop_all_servers()

if __name__ == "__main__":
    external_access_example()
```

### Custom Arguments and Fine-tuned Configuration

```python
#!/usr/bin/env python3
"""
Example of using custom arguments and fine-tuned server configurations.
"""

from mcp_server_manager import MCPServerManager, ServerConfig, ServerType

def custom_config_example():
    manager = MCPServerManager()
    
    configs = [
        ServerConfig(
            server_type=ServerType.CONFIG,
            port=8100,
            base_url="/simulators",
            environment_vars={
                "demo_apitoken": "simulator-token",
                "CUSTOM_LOG_LEVEL": "DEBUG",
                "FEATURE_FLAG_ADVANCED_FILTERS": "true"
            },
            custom_args=["--verbose", "--debug"]
        ),
        ServerConfig(
            server_type=ServerType.DATA,
            port=8101,
            base_url="/data/v2",
            environment_vars={
                "demo_apitoken": "data-token",
                "CACHE_SIZE": "1000",
                "MAX_CONNECTIONS": "50"
            }
        ),
        ServerConfig(
            server_type=ServerType.PLAYBOOK,
            port=8103,
            base_url="/attacks",
            environment_vars={
                "demo_apitoken": "playbook-token",
                "ATTACK_CACHE_TTL": "7200"
            }
        )
    ]
    
    try:
        # Start all servers with different configurations
        for i, config in enumerate(configs):
            instance_id = f"custom-server-{i+1}"
            success = manager.start_server(instance_id, config)
            
            if success:
                info = manager.get_server_info(instance_id)
                print(f"✅ {info['server_type'].upper()} server: {info['endpoint']}")
            else:
                print(f"❌ Failed to start server {instance_id}")
        
        input("Press Enter to stop all servers...")
    
    finally:
        manager.stop_all_servers()

if __name__ == "__main__":
    custom_config_example()
```

## REST API Usage

### Starting the REST API Server

```bash
# Install FastAPI dependencies first (if not already installed)
pip install fastapi uvicorn

# Start the REST API server
python mcp_server_rest_api.py --port 9000

# Or with custom host binding
python mcp_server_rest_api.py --host 0.0.0.0 --port 9000
```

### REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API root and information |
| GET | `/health` | Health check endpoint |
| POST | `/servers/{instance_id}` | Create and start a server instance |
| GET | `/servers` | List all server instances |
| GET | `/servers/{instance_id}` | Get specific server information |
| DELETE | `/servers/{instance_id}` | Stop and remove a server instance |
| POST | `/servers/{instance_id}/restart` | Restart a server instance |
| GET | `/servers/{instance_id}/logs` | Get server logs |
| DELETE | `/servers` | Stop all server instances |

### REST API Examples with curl

```bash
# Check API health
curl http://localhost:9000/health

# Create and start a new server instance
curl -X POST "http://localhost:9000/servers/my-config-server" \
  -H "Content-Type: application/json" \
  -d '{
    "server_type": "config",
    "port": 8100,
    "base_url": "/api/config",
    "allow_external": false,
    "environment_vars": {
      "demo_apitoken": "config-token-123"
    }
  }'

# List all server instances
curl http://localhost:9000/servers

# Get specific server information
curl http://localhost:9000/servers/my-config-server

# Restart a server instance
curl -X POST http://localhost:9000/servers/my-config-server/restart

# Stop and remove a server instance
curl -X DELETE http://localhost:9000/servers/my-config-server

# Stop all servers
curl -X DELETE http://localhost:9000/servers
```

### REST API Python Client Example

```python
#!/usr/bin/env python3
"""
Example of using the REST API from Python.
"""

import requests
import json

def rest_api_client_example():
    base_url = "http://localhost:9000"
    
    # Create server configuration
    server_config = {
        "server_type": "data",
        "port": 8101,
        "base_url": "/api/data",
        "allow_external": False,
        "environment_vars": {
            "demo_apitoken": "data-token-456"
        }
    }
    
    try:
        # Start a server
        response = requests.post(
            f"{base_url}/servers/api-data-server",
            json=server_config
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Server started: {result['data']['endpoint']}")
            
            # Get server info
            info_response = requests.get(f"{base_url}/servers/api-data-server")
            if info_response.status_code == 200:
                info = info_response.json()
                print(f"Server status: {info['data']['status']}")
                print(f"Server PID: {info['data']['pid']}")
                print(f"Uptime: {info['data']['uptime']:.2f} seconds")
            
            input("Press Enter to stop server...")
            
            # Stop the server
            stop_response = requests.delete(f"{base_url}/servers/api-data-server")
            if stop_response.status_code == 200:
                print("✅ Server stopped successfully")
        else:
            print(f"❌ Failed to start server: {response.text}")
    
    except requests.RequestException as e:
        print(f"❌ API request failed: {e}")

if __name__ == "__main__":
    rest_api_client_example()
```

## Integration Examples

### Health Check and Monitoring

```python
#!/usr/bin/env python3
"""
Example of implementing health checks and monitoring for managed servers.
"""

import time
import threading
from mcp_server_manager import MCPServerManager, ServerConfig, ServerType, ServerStatus

class ServerMonitor:
    """Monitor and manage server health."""
    
    def __init__(self, manager: MCPServerManager):
        self.manager = manager
        self.monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self, interval: int = 30):
        """Start monitoring servers with specified interval."""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        print(f"🔍 Started monitoring with {interval}s interval")
    
    def stop_monitoring(self):
        """Stop monitoring servers."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("🛑 Monitoring stopped")
    
    def _monitor_loop(self, interval: int):
        """Main monitoring loop."""
        while self.monitoring:
            self._check_server_health()
            time.sleep(interval)
    
    def _check_server_health(self):
        """Check health of all managed servers."""
        servers = self.manager.list_servers()
        
        print(f"\n📊 Health Check at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)
        
        healthy_count = 0
        for server in servers:
            status = self.manager.get_server_status(server['instance_id'])
            
            if status == ServerStatus.RUNNING:
                print(f"✅ {server['instance_id']}: HEALTHY (PID: {server['pid']}, Uptime: {server['uptime']:.1f}s)")
                healthy_count += 1
            else:
                print(f"❌ {server['instance_id']}: UNHEALTHY (Status: {status.value if status else 'unknown'})")
                
                # Attempt to restart unhealthy servers
                print(f"🔄 Attempting to restart {server['instance_id']}...")
                if self.manager.restart_server(server['instance_id']):
                    print(f"✅ Successfully restarted {server['instance_id']}")
                else:
                    print(f"❌ Failed to restart {server['instance_id']}")
        
        print(f"📈 Summary: {healthy_count}/{len(servers)} servers healthy")

def monitoring_example():
    """Example of server monitoring."""
    manager = MCPServerManager()
    monitor = ServerMonitor(manager)
    
    # Start some test servers
    configs = [
        ServerConfig(server_type=ServerType.UTILITIES, port=8102, base_url="/utils"),
        ServerConfig(server_type=ServerType.CONFIG, port=8103, base_url="/config")
    ]
    
    try:
        # Start servers
        for i, config in enumerate(configs):
            instance_id = f"monitored-server-{i+1}"
            if manager.start_server(instance_id, config):
                print(f"✅ Started {instance_id}")
        
        # Start monitoring
        monitor.start_monitoring(interval=10)
        
        print("\n🔍 Monitoring servers... (Press Ctrl+C to stop)")
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitoring and servers...")
    
    finally:
        monitor.stop_monitoring()
        manager.stop_all_servers()

if __name__ == "__main__":
    monitoring_example()
```

## Error Handling

### Robust Error Handling Example

```python
#!/usr/bin/env python3
"""
Example of robust error handling with the server manager.
"""

import logging
from mcp_server_manager import MCPServerManager, ServerConfig, ServerType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def robust_server_management():
    """Example with comprehensive error handling."""
    manager = MCPServerManager()
    
    server_configs = [
        ("config-server", ServerConfig(ServerType.CONFIG, 8100)),
        ("data-server", ServerConfig(ServerType.DATA, 8101)), 
        ("utilities-server", ServerConfig(ServerType.UTILITIES, 8102))
    ]
    
    started_servers = []
    
    try:
        # Start servers with error handling
        for instance_id, config in server_configs:
            try:
                logger.info(f"Starting server: {instance_id}")
                success = manager.start_server(instance_id, config)
                
                if success:
                    started_servers.append(instance_id)
                    info = manager.get_server_info(instance_id)
                    logger.info(f"✅ {instance_id} started successfully on port {info['port']}")
                else:
                    logger.error(f"❌ Failed to start {instance_id}")
                    
            except ValueError as e:
                logger.error(f"❌ Configuration error for {instance_id}: {e}")
            except Exception as e:
                logger.error(f"❌ Unexpected error starting {instance_id}: {e}")
        
        if started_servers:
            logger.info(f"Successfully started {len(started_servers)} servers")
            
            # Demonstrate server operations with error handling
            for instance_id in started_servers:
                try:
                    # Check server status
                    status = manager.get_server_status(instance_id)
                    logger.info(f"Server {instance_id} status: {status.value if status else 'unknown'}")
                    
                    # Get detailed info
                    info = manager.get_server_info(instance_id)
                    if info:
                        logger.info(f"Server {instance_id} endpoint: {info['endpoint']}")
                    
                except Exception as e:
                    logger.error(f"❌ Error checking {instance_id}: {e}")
            
            input("Press Enter to stop servers...")
        else:
            logger.warning("⚠️  No servers were started successfully")
    
    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
    
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
    
    finally:
        # Graceful shutdown with error handling
        logger.info("Shutting down servers...")
        
        for instance_id in started_servers:
            try:
                if manager.stop_server(instance_id, timeout=15):
                    logger.info(f"✅ Stopped {instance_id}")
                else:
                    logger.warning(f"⚠️  Failed to stop {instance_id} gracefully")
            except Exception as e:
                logger.error(f"❌ Error stopping {instance_id}: {e}")
        
        logger.info("Cleanup complete")

if __name__ == "__main__":
    robust_server_management()
```

## API Reference

### ServerConfig Class

```python
@dataclass
class ServerConfig:
    server_type: ServerType          # Type of server (config, data, utilities, playbook, all)
    port: int                        # Port number (1024-65535)
    host: str = "127.0.0.1"         # Host to bind to
    base_url: str = "/"             # Base URL path for endpoints
    allow_external: bool = False     # Allow external connections
    auth_token: Optional[str] = None # Authentication token for external access
    environment_vars: Dict[str, str] # Custom environment variables
    custom_args: List[str]          # Additional command-line arguments
```

### MCPServerManager Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `start_server(instance_id, config)` | Start a new server instance | `bool` |
| `stop_server(instance_id, timeout=10)` | Stop a server instance | `bool` |
| `restart_server(instance_id, timeout=10)` | Restart a server instance | `bool` |
| `get_server_status(instance_id)` | Get server status | `Optional[ServerStatus]` |
| `get_server_info(instance_id)` | Get detailed server information | `Optional[Dict]` |
| `list_servers()` | List all server instances | `List[Dict]` |
| `stop_all_servers(timeout=10)` | Stop all running servers | `bool` |

### ServerType Enum

- `ServerType.CONFIG` - Configuration/simulator server
- `ServerType.DATA` - Data/test results server  
- `ServerType.UTILITIES` - Utilities server
- `ServerType.PLAYBOOK` - Playbook/attack server
- `ServerType.ALL` - Multi-server launcher

### ServerStatus Enum

- `ServerStatus.STOPPED` - Server is not running
- `ServerStatus.STARTING` - Server is starting up
- `ServerStatus.RUNNING` - Server is running normally
- `ServerStatus.STOPPING` - Server is shutting down
- `ServerStatus.FAILED` - Server failed to start or crashed
- `ServerStatus.UNKNOWN` - Status cannot be determined

## Testing Your Integration

### Basic Functionality Test

```python
#!/usr/bin/env python3
"""
Quick test to verify server manager functionality.
"""

def test_basic_functionality():
    """Test basic server manager functionality without starting real servers."""
    from mcp_server_manager import MCPServerManager, ServerConfig, ServerType
    
    print("🧪 Testing SafeBreach MCP Server Manager...")
    
    try:
        # Test 1: Manager initialization
        manager = MCPServerManager()
        assert len(manager.instances) == 0
        print("✅ Manager initialization")
        
        # Test 2: Configuration creation
        config = ServerConfig(
            server_type=ServerType.UTILITIES,
            port=8099,
            base_url="/test/api",
            environment_vars={"TEST_VAR": "test_value"}
        )
        assert config.server_type == ServerType.UTILITIES
        assert config.port == 8099
        assert config.base_url == "/test/api"
        print("✅ Configuration creation")
        
        # Test 3: Command generation
        cmd = manager._get_server_command(config)
        expected = ["uv", "run", "-m", "safebreach_mcp_utilities.utilities_server"]
        assert cmd == expected
        print("✅ Command generation")
        
        # Test 4: Environment preparation
        env = manager._prepare_environment(config)
        assert env.get("SAFEBREACH_MCP_BASE_URL") == "/test/api"
        assert env.get("TEST_VAR") == "test_value"
        print("✅ Environment preparation")
        
        # Test 5: Port availability checking
        assert manager._check_port_availability(8099, "test-instance")
        print("✅ Port availability checking")
        
        print("🎉 All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

if __name__ == "__main__":
    test_basic_functionality()
```

---

This API provides powerful programmatic control over SafeBreach MCP server instances, enabling complex deployment scenarios, multi-environment configurations, and automated management workflows.