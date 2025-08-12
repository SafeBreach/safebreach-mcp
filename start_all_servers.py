"""
SafeBreach MCP Multi-Server Launcher

This script starts all SafeBreach MCP servers concurrently on different ports using uvicorn.
Supports external binding configuration and command-line argument parsing.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from typing import List

# Import server classes
from safebreach_mcp_config.config_server import SafeBreachConfigServer
from safebreach_mcp_data.data_server import SafeBreachDataServer
from safebreach_mcp_utilities.utilities_server import SafeBreachUtilitiesServer
from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def parse_external_config() -> dict:
    """Parse external connection configuration for all servers."""
    # Check global flag first
    global_external = os.environ.get('SAFEBREACH_MCP_ALLOW_EXTERNAL', 'false').lower() == 'true'
    
    # Check server-specific flags
    config_external = os.environ.get('SAFEBREACH_MCP_CONFIG_EXTERNAL', 'false').lower() == 'true'
    data_external = os.environ.get('SAFEBREACH_MCP_DATA_EXTERNAL', 'false').lower() == 'true'
    utilities_external = os.environ.get('SAFEBREACH_MCP_UTILITIES_EXTERNAL', 'false').lower() == 'true'
    playbook_external = os.environ.get('SAFEBREACH_MCP_PLAYBOOK_EXTERNAL', 'false').lower() == 'true'
    
    return {
        'config': global_external or config_external,
        'data': global_external or data_external,
        'utilities': global_external or utilities_external,
        'playbook': global_external or playbook_external
    }

def parse_command_line_args():
    """Parse command-line arguments for external binding configuration."""
    parser = argparse.ArgumentParser(
        description='SafeBreach MCP Multi-Server Launcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
External Connection Support:
  Use --external to enable external connections for all servers.
  Use --external-config, --external-data, --external-utilities, --external-playbook for specific servers.
  
  Authentication:
    Set SAFEBREACH_MCP_AUTH_TOKEN environment variable when using external connections.
  
  Custom Binding:
    Set SAFEBREACH_MCP_BIND_HOST environment variable to customize bind address.
  
  Base URL Configuration:
    Use --base-url to set custom base URL path for MCP endpoints.
    Set SAFEBREACH_MCP_BASE_URL environment variable as an alternative.
  
Examples:
  # Local connections only (default)
  python start_all_servers.py
  
  # Enable external connections for all servers
  SAFEBREACH_MCP_AUTH_TOKEN="your-secret-token" python start_all_servers.py --external
  
  # Enable external connections for specific servers only
  SAFEBREACH_MCP_AUTH_TOKEN="your-token" python start_all_servers.py --external-data --external-utilities --external-playbook
  
  # Custom base URL path for reverse proxy deployment
  python start_all_servers.py --base-url /api/mcp
  
  # Combined configuration with external access and custom base URL
  SAFEBREACH_MCP_AUTH_TOKEN="your-token" python start_all_servers.py --external --base-url /api/mcp
        """
    )
    
    # External connection flags
    parser.add_argument('--external', action='store_true',
                      help='Enable external connections for all servers')
    parser.add_argument('--external-config', action='store_true',
                      help='Enable external connections for Config server only')
    parser.add_argument('--external-data', action='store_true',
                      help='Enable external connections for Data server only')
    parser.add_argument('--external-utilities', action='store_true',
                      help='Enable external connections for Utilities server only')
    parser.add_argument('--external-playbook', action='store_true',
                      help='Enable external connections for Playbook server only')
    
    # Binding configuration
    parser.add_argument('--host', default='127.0.0.1',
                      help='Host to bind servers to (default: 127.0.0.1)')
    parser.add_argument('--base-url', 
                      help='Base URL path for MCP endpoints (e.g., /api/mcp). Overrides SAFEBREACH_MCP_BASE_URL environment variable.')
    
    return parser.parse_args()

class MultiServerLauncher:
    """Launcher for all SafeBreach MCP servers with external binding support."""
    
    def __init__(self, args=None):
        self.servers = []
        self.running = False
        self.tasks = []
        self.args = args or argparse.Namespace()
        
        # Set base URL environment variable if provided via command line
        if hasattr(self.args, 'base_url') and self.args.base_url:
            os.environ['SAFEBREACH_MCP_BASE_URL'] = self.args.base_url
        
        # Parse external configuration from environment variables and command-line args
        self.external_config = self._determine_external_config()
    
    def _determine_external_config(self) -> dict:
        """Determine external configuration from environment variables and command-line arguments."""
        # Start with environment variable configuration
        env_config = parse_external_config()
        
        # Override with command-line arguments if provided
        if hasattr(self.args, 'external') and self.args.external:
            env_config['config'] = True
            env_config['data'] = True  
            env_config['utilities'] = True
            env_config['playbook'] = True
        
        if hasattr(self.args, 'external_config') and self.args.external_config:
            env_config['config'] = True
            
        if hasattr(self.args, 'external_data') and self.args.external_data:
            env_config['data'] = True
            
        if hasattr(self.args, 'external_utilities') and self.args.external_utilities:
            env_config['utilities'] = True
            
        if hasattr(self.args, 'external_playbook') and self.args.external_playbook:
            env_config['playbook'] = True
        
        return env_config
    
    def _get_bind_host(self) -> str:
        """Get the bind host from command-line args or environment variable."""
        # Command-line argument takes precedence
        if hasattr(self.args, 'host') and self.args.host != '127.0.0.1':
            return self.args.host
        
        # Fall back to environment variable
        return os.environ.get('SAFEBREACH_MCP_BIND_HOST', '127.0.0.1')
    
    def _log_connection_summary(self, server_configs):
        """Log a summary of connection modes for all servers."""
        external_servers = []
        local_servers = []
        
        for config in server_configs:
            server_type = config['name'].split()[0].lower()  # 'config', 'data', 'utilities'
            if self.external_config.get(server_type, False):
                external_servers.append(config['name'])
            else:
                local_servers.append(config['name'])
        
        if external_servers:
            logger.warning("🌐 External connections enabled for: " + ", ".join(external_servers))
            logger.warning("🔒 HTTP Authorization required for external connections")
            auth_token = os.environ.get('SAFEBREACH_MCP_AUTH_TOKEN')
            if not auth_token:
                logger.error("❌ SAFEBREACH_MCP_AUTH_TOKEN not set - external connections will fail!")
            else:
                logger.info("✅ SAFEBREACH_MCP_AUTH_TOKEN configured")
        
        if local_servers:
            logger.info("🏠 Local connections only for: " + ", ".join(local_servers))
        
    async def start_all_servers(self):
        """Start all servers concurrently on different ports with external binding support."""
        logger.info("Starting all SafeBreach MCP servers...")
        
        # Server configurations with server type mapping
        server_configs = [
            {
                'name': 'Config Server',
                'type': 'config',
                'port': 8000,
                'description': 'Simulators and infrastructure management',
                'server_class': SafeBreachConfigServer
            },
            {
                'name': 'Data Server',
                'type': 'data',
                'port': 8001,
                'description': 'Test and simulation data operations',
                'server_class': SafeBreachDataServer
            },
            {
                'name': 'Utilities Server',
                'type': 'utilities',
                'port': 8002,
                'description': 'Datetime conversion utilities',
                'server_class': SafeBreachUtilitiesServer
            },
            {
                'name': 'Playbook Server',
                'type': 'playbook',
                'port': 8003,
                'description': 'Playbook attack operations',
                'server_class': SafeBreachPlaybookServer
            }
        ]
        
        # Log connection mode summary
        self._log_connection_summary(server_configs)
        
        # Get bind host
        bind_host = self._get_bind_host()
        
        # Create server instances and start them
        tasks = []
        for config in server_configs:
            server_type = config['type']
            allow_external = self.external_config.get(server_type, False)
            
            connection_mode = "🌐 external" if allow_external else "🏠 local"
            logger.info(f"Starting {config['name']} on port {config['port']} ({connection_mode}) - {config['description']}")
            
            # Create server instance
            server = config['server_class']()
            self.servers.append(server)
            
            # Create task to run the server with appropriate configuration
            task = asyncio.create_task(
                server.run_server(
                    port=config['port'],
                    host=bind_host,
                    allow_external=allow_external
                )
            )
            tasks.append(task)
        
        # Store tasks for shutdown
        self.tasks = tasks
        self.running = True
        
        logger.info("All servers started successfully!")
        logger.info("Server endpoints:")
        
        # Get base URL from environment variable
        base_url = os.environ.get('SAFEBREACH_MCP_BASE_URL', '/').rstrip('/')
        base_path = base_url if base_url != '/' else ''
        
        if base_path:
            logger.info(f"🔗 Base URL configured: {base_url}")
        
        # Display endpoints with appropriate host information
        for config in server_configs:
            server_type = config['type']
            allow_external = self.external_config.get(server_type, False)
            
            if allow_external:
                # Show both local and external access options
                logger.info(f"  {config['name']}: http://localhost:{config['port']}{base_path}/sse (local)")
                if bind_host != '127.0.0.1':
                    logger.info(f"  {config['name']}: http://{bind_host}:{config['port']}{base_path}/sse (external)")
                else:
                    logger.info(f"  {config['name']}: http://0.0.0.0:{config['port']}{base_path}/sse (external - all interfaces)")
            else:
                logger.info(f"  {config['name']}: http://localhost:{config['port']}{base_path}/sse")
        
        logger.info("Press Ctrl+C to stop all servers")
        
        # Wait for all servers to complete
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Servers cancelled")
        except Exception as e:
            logger.error(f"Error running servers: {e}")
            
    async def shutdown(self):
        """Gracefully shutdown all servers."""
        if not self.running:
            return
            
        logger.info("Shutting down all servers...")
        self.running = False
        
        # Cancel all server tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete cancellation
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("All servers stopped")

# Global launcher instance - will be set in main
launcher = None

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    if launcher:
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(launcher.shutdown())

async def main(args=None):
    """Main async entry point with command-line argument support."""
    global launcher
    
    # Parse arguments if not provided
    if args is None:
        args = parse_command_line_args()
    
    # Create launcher with arguments
    launcher = MultiServerLauncher(args)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await launcher.start_all_servers()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await launcher.shutdown()

def console_entry_point():
    """Console script entry point that properly handles async main with argument parsing."""
    args = parse_command_line_args()
    asyncio.run(main(args))

if __name__ == "__main__":
    console_entry_point()