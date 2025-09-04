# Disclaimer
This is an experimental project intended to demonstrate SafeBreach capabilities with MCP. It is not officially supported or verified by SafeBreach.

# SafeBreach MCP Server

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)
[![SafeBreach Platform](https://img.shields.io/badge/platform-SafeBreach-orange.svg)](https://safebreach.com)

A Model Context Protocol (MCP) server that bridges AI agents with SafeBreach's Breach and Attack Simulation platform. Enables natural language queries and seamless integration through a multi-server architecture with specialized domains.

## 🚀 Quick Start

### New Team Members
```bash
# 1. Clone and setup security tools (one-time setup)
git clone <repository-url>
cd safebreach-mcp
./setup-security.sh

# 2. Configure your environment
cp .env.template .env
# Edit .env with your actual API tokens

# 3. ALWAYS launch Claude with security context
./claude-launcher.sh
```

### 🔒 Security-First Development
This project implements comprehensive security measures to prevent API token leaks:
- **Automated secret scanning** with pre-commit hooks
- **Claude security context** ensuring AI awareness of best practices  
- **Template-based configuration** preventing accidental commits
- **Multi-layer validation** in CI/CD pipelines

📚 **See [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md) for complete development guidelines.**

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Installation](#installation)
- [External Connection Support](#external-connection-support)
- [Usage](#usage-)
  - [Registering with Claude Desktop](#registering-with-claude-desktop-)
  - [Windows Configuration](#windows-configuration)
- [API Reference](#api-reference-)
- [Testing](#testing-)
- [Development](#development-)
- [Troubleshooting](#troubleshooting-)
- [Security Considerations](#security-considerations-)
- [Contributing](#contributing-)

## Overview

This MCP server enables AI agents to interact with SafeBreach management consoles to:
- Retrieve simulator information and status
- Access test execution history and results  
- Query simulation details and security control effectiveness
- Retrieve security control events and SIEM logs
- Access test findings data similar to penetration test reports
- Analyze attack simulation outcomes and root cause analysis

## Features

### 🏗️ Architecture
- **Multi-Server Architecture**: Specialized servers for different domains (config, data, utilities, playbook)
- **Domain Separation**: Clear separation of concerns with independent scaling capabilities
- **Horizontal Scaling**: Each server can be scaled independently based on demand

### 🔒 Security & Connectivity
- **Security-First Design**: Localhost-only default with Bearer token authentication for external access
- **External Connection Support**: Optional external network access with HTTP Authorization security
- **SSE Transport**: Server-Sent Events transport for real-time communication

### 📊 Data Management
- **Simulator Management**: Query SafeBreach simulators, their status, and detailed configurations
- **Test History**: Retrieve paginated test execution history with advanced filtering capabilities
- **Simulation Analysis**: Access detailed simulation results including security control interactions
- **Playbook Attacks**: Browse and analyze SafeBreach's comprehensive attack knowledge base

### 🌐 Integration
- **Multi-Environment Support**: Connect to multiple SafeBreach environments (staging, dev, production)
- **Intelligent Caching**: Server-specific caching for improved performance and reduced API calls

## Architecture

### Multi-Server Architecture (Recommended)

**Core Shared Components:**
- **`safebreach_mcp_core/`**: Shared components for all servers
  - `safebreach_auth.py`: Centralized authentication
  - `safebreach_base.py`: Base class for all MCP servers
  - `datetime_utils.py`: Shared datetime utilities
  - `environments_metadata.py`: Configuration for supported SafeBreach environments (supports single-tenant mode via environment variables)
  - `secret_utils.py`: AWS SSM Parameter Store and Secrets Manager integration

**Specialized Servers:**
- **`safebreach_mcp_config/`**: Config Server (Port 8000) - Simulator operations
- **`safebreach_mcp_data/`**: Data Server (Port 8001) - Test and simulation data
- **`safebreach_mcp_utilities/`**: Utilities Server (Port 8002) - Datetime functions
- **`safebreach_mcp_playbook/`**: Playbook Server (Port 8003) - Playbook attack operations

**Multi-Server Launchers:**
- **`start_all_servers.py`**: Concurrent multi-server launcher

**Additional Components:**
- **`mcp_server_bug_423_hotfix.py`**: MCP initialization fix

## Configuration
Configuration of the SafeBreach MCP Server consists of:
- Specifying which SafeBreach consoles are in scope for the MCP. For each SafeBreach console, provide the 'url', 'account' and the provider (method) for fetching the API key
- Making the API keys available to the MCP server through either environment variables, AWS SSM or AWS Secrets Manager

### Prerequisites

**For All Users (Running the MCP Server):**
- `uv` package manager (automatically handles Python installation)
- SafeBreach API tokens (see [API Tokens](#api-tokens) section for storage options)

**For AWS-based Token Storage (Optional):**
- AWS credentials configured for SSM Parameter Store or Secrets Manager access
- *Note: You can also use environment variables for token storage without AWS*

**For Local Development Only:**
- Python 3.12+ (if not using `uv` for dependency management)
- Git (for cloning the repository)

### SafeBreach Environments
**Specifying The SafeBreach Environments With An Environment Variable And File**
Set the environment variable to point to a configuration JSON file anywhere on your disk that is available to the MCP server for read.
```bash
export SAFEBREACH_ENVS_FILE=/path/to/more_envs.json
```

The JSON file format should adhere to the following schema:
```
{
    "console-friendly-name": {
        "url": "my-console.safebreach.com",
        "account": "1234567890",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "my-console-apitoken"
        }
    }
}
```

### Single-Tenant Configuration (SafeBreach Internal Use)

For deployment within SafeBreach management consoles, the MCP server supports single-tenant mode using environment variables. This allows the server to connect to local SafeBreach APIs without requiring external environment metadata configuration.

**Environment Variables:**
```bash
# API endpoints for single-tenant deployment
export DATA_URL="http://localhost:3400"          # Data API endpoint
export CONFIG_URL="http://localhost:3401"        # Config API endpoint  
export SIEM_URL="http://localhost:3402"          # SIEM API endpoint
export ACCOUNT_ID="your-account-id"              # SafeBreach account ID

# API authentication
export console_name_apitoken="your-api-token"    # API token for the console
```

**How it works:**
- When environment variables are set, the server uses local API endpoints
- When environment variables are not set, the server falls back to multi-tenant mode using environments metadata
- This enables seamless deployment within SafeBreach management consoles

**Hardcoding The Environments**
In some cases, you might prefer to clone the repo and hard code your environments to avoid the dependency on environmental settings. That can be achieved by editing `environments_metadata.py`:

```python
safebreach_envs = {
    "console-name": {
        "url": "console.safebreach.com", 
        "account": "account_id",
        "secret_config": {
            "provider": "aws_ssm",  # or "aws_secrets_manager" or "env_var"
            "parameter_name": "console-name-apitoken"
        }
    }
}
```

### API Tokens

SafeBreach API tokens can be stored using three different providers:

**1. AWS SSM Parameter Store (default):**
```bash
aws ssm put-parameter --name "console-name-apitoken" --value "your-api-token" --type "SecureString"
```

**2. AWS Secrets Manager:**
```bash
aws secretsmanager create-secret --name "safebreach/console-name/api-token" --secret-string "your-api-token"
```

**3. Environment Variables:**
```bash
# For parameter_name "console-name-apitoken", set:
export CONSOLE_NAME_APITOKEN="your-api-token"

# Note: Dashes are automatically converted to underscores for environment variable lookup
```

## Installation

### Option 1: Direct Installation from Git (Recommended) 🚀

Install and run the MCP server directly from the repository:

**Additional Requirements for Remote Installation:**
- SSH key configured with GitHub (recommended), OR
- GitHub Personal Access Token for HTTPS authentication
- `uv` version 0.4.0+ (check with `uv --version`) for `--from` flag support

**Setting up SSH access to GitHub:**
1. Generate SSH key: `ssh-keygen -t ed25519 -C "your_email@example.com"`
2. Add to SSH agent: `ssh-add ~/.ssh/id_ed25519`
3. Add public key to GitHub: Settings → SSH and GPG keys → New SSH key
4. Test: `ssh -T git@github.com`

```bash
# Method 1: Install latest version of the package as a tool with SSH (recommended for private repos)
uv tool install --force git+ssh://git@github.com/SafeBreach/safebreach-mcp.git

# Update PATH if needed (uv will show a warning if required)
export PATH="/Users/$(whoami)/.local/bin:$PATH"  # or run: uv tool update-shell

# Run multi-server architecture (recommended)
safebreach-mcp-all-servers

# Or run individual servers
safebreach-mcp-config-server     # Port 8000
safebreach-mcp-data-server       # Port 8001
safebreach-mcp-utilities-server  # Port 8002
safebreach-mcp-playbook-server   # Port 8003

# Method 2: Install with HTTPS authentication
# First, configure git credentials or use personal access token
uv tool install git+https://username:personal-access-token@github.com/SafeBreach/safebreach-mcp.git
safebreach-mcp-all-servers

# Method 3: Install with pip in a uv environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install git+ssh://git@github.com/SafeBreach/safebreach-mcp.git
safebreach-mcp-all-servers

# Method 4: For newer uv versions (0.4.0+) with SSH
uv run --from git+ssh://git@github.com/SafeBreach/safebreach-mcp.git safebreach-mcp-all-servers
```

### Option 2: Local Development Setup 🛠️

1. Clone the repository:
```bash
git clone git@github.com:SafeBreach/safebreach-mcp.git
```

2. Install dependencies:
```bash
uv sync
```

## External Connection Support
Commonly MCP servers are deployed locally on the same host running the AI client application (e.g. Claude Desktop). That is also the default running mode for the SafeBreach MCP Server. In addition, the SafeBreach MCP Server supports running the server on a remote host making it accessible to multiple clients with an authorization header simultaneously.

> ⚠️ **Important Security Notice**: The following deployment mode should be used with extreme caution. The current authorization method is experimental and does not contain validated authentication flows for external MCP connections. External exposure significantly increases security risks and should only be implemented in controlled environments with appropriate security measures.

### Security Model

- **Default Behavior**: All servers bind to localhost (127.0.0.1) - no external access
- **External Access**: Optional with explicit configuration required
- **Authentication**: HTTP Authorization header with Bearer token required for external connections
- **Localhost Bypass**: Local connections bypass authentication automatically
- **Command-line Control**: Full command-line argument support for flexible deployment

### Configuration Options

**Environment Variables:**
```bash
# Global external access (all servers)
export SAFEBREACH_MCP_ALLOW_EXTERNAL=true
export SAFEBREACH_MCP_AUTH_TOKEN="your-secure-token"

# Server-specific external access
export SAFEBREACH_MCP_CONFIG_EXTERNAL=true      # Config server only
export SAFEBREACH_MCP_DATA_EXTERNAL=true        # Data server only  
export SAFEBREACH_MCP_UTILITIES_EXTERNAL=true   # Utilities server only

# Custom bind host (default: 127.0.0.1)
export SAFEBREACH_MCP_BIND_HOST=0.0.0.0
```

**Command-Line Arguments:**
```bash
# Enable external connections for all servers
SAFEBREACH_MCP_AUTH_TOKEN="your-token" safebreach-mcp-all-servers --external

# Enable external connections for specific servers
SAFEBREACH_MCP_AUTH_TOKEN="your-token" safebreach-mcp-all-servers --external-data --external-utilities

# Custom bind host
SAFEBREACH_MCP_AUTH_TOKEN="your-token" safebreach-mcp-all-servers --external --host 0.0.0.0

# Help with usage examples
safebreach-mcp-all-servers --help
```

### Usage Examples

**Local Development (Default):**
```bash
# Secure localhost-only access - no external configuration needed
uv run start_all_servers.py
```

**External Access - All Servers:**
```bash
# Enable external connections for all servers
export SAFEBREACH_MCP_AUTH_TOKEN="your-very-secure-token"
export SAFEBREACH_MCP_ALLOW_EXTERNAL=true
uv run start_all_servers.py

# Or with command-line arguments
SAFEBREACH_MCP_AUTH_TOKEN="your-token" uv run start_all_servers.py --external
```

**External Access - Specific Servers:**
```bash
# Only Data and Utilities servers accessible externally, Config remains local-only
export SAFEBREACH_MCP_AUTH_TOKEN="your-secure-token"
export SAFEBREACH_MCP_DATA_EXTERNAL=true
export SAFEBREACH_MCP_UTILITIES_EXTERNAL=true
uv run start_all_servers.py
```

**Individual Server External Access:**
```bash
# Run individual server with external access
export SAFEBREACH_MCP_AUTH_TOKEN="your-token"
export SAFEBREACH_MCP_DATA_EXTERNAL=true
uv run -m safebreach_mcp_data.data_server
```

### Client Authentication

When accessing externally enabled servers, clients must include the Authorization header:

```bash
# Example HTTP request to external server
curl -H "Authorization: Bearer your-secure-token" \
     "http://your-server:8001/sse"

# Local connections don't require authentication
curl "http://localhost:8001/sse"
```

### Security Warnings

When external connections are enabled, the servers will log security warnings:

```
🚨 SECURITY WARNING: Server binding to 0.0.0.0:8001 - accessible from external networks!
🔒 HTTP Authorization required for external connections
🔑 Set SAFEBREACH_MCP_AUTH_TOKEN environment variable for authentication
🌐 External connections enabled for: Data Server, Utilities Server
🏠 Local connections only for: Config Server
✅ SAFEBREACH_MCP_AUTH_TOKEN configured
```

### Claude Desktop Integration with External Servers

For external servers, update your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "safebreach-data-external": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://100.117.2.202:8001/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-secure-token"
      ]
    }
  }
}
```


## Usage 🎯

### Starting the MCP Server

#### Multi-Server Architecture (Recommended)

**Local Development (Default - Secure):**
```bash
# Run all servers concurrently on localhost only
uv run start_all_servers.py

# Or run individual servers
uv run -m safebreach_mcp_config.config_server     # Port 8000
uv run -m safebreach_mcp_data.data_server         # Port 8001
uv run -m safebreach_mcp_utilities.utilities_server # Port 8002
uv run -m safebreach_mcp_playbook.playbook_server # Port 8003
```

**External Access:**
```bash
# Enable external connections for all servers with environment variables
export SAFEBREACH_MCP_AUTH_TOKEN="your-secure-token"
export SAFEBREACH_MCP_ALLOW_EXTERNAL=true
uv run start_all_servers.py

# Enable external connections with command-line arguments
SAFEBREACH_MCP_AUTH_TOKEN="your-token" uv run start_all_servers.py --external

# Enable external connections for specific servers only
SAFEBREACH_MCP_AUTH_TOKEN="your-token" uv run start_all_servers.py --external-data --external-utilities

# Get help with all external connection options
uv run start_all_servers.py --help
```

**Single-Tenant Deployment (SafeBreach Internal):**
```bash
# Set single-tenant environment variables
export DATA_URL="http://localhost:3400"
export CONFIG_URL="http://localhost:3401"
export SIEM_URL="http://localhost:3402" 
export ACCOUNT_ID="your-account-id"
export console_name_apitoken="your-api-token"

# Start all servers (will use local APIs)
uv run start_all_servers.py
```

#### Troubleshooting Remote Installation

| Issue | Solution |
|-------|----------|
| "could not read Username" | Use SSH method or set up GitHub Personal Access Token |
| "Address already in use" | Stop existing servers: `lsof -ti:8000,8001,8002 \| xargs kill` |
| "command not found" | Add uv tools to PATH: `export PATH="$HOME/.local/bin:$PATH"` |
| SSH key issues | Verify with `ssh -T git@github.com` |


### Registering with Claude Desktop 🔗

Claude Desktop reads the MCP server configurations from the file:

**macOS/Linux:**
`~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows:**
`%APPDATA%\Claude\claude_desktop_config.json`

#### Local Development Configuration

**Multi-Server Configuration (Localhost):**
```json
{
  "mcpServers": {
    "safebreach-config": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://127.0.0.1:8000/sse",
        "--transport",
        "http-first"
      ]
    },
    "safebreach-data": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://127.0.0.1:8001/sse",
        "--transport",
        "http-first"
      ]
    },
    "safebreach-utilities": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://127.0.0.1:8002/sse",
        "--transport",
        "http-first"
      ]
    },
    "safebreach-playbook": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://127.0.0.1:8003/sse",
        "--transport",
        "http-first"
      ]
    }
  }
}
```

#### Windows Configuration

**Multi-Server Configuration (Windows with External Server):**
```json
{
  "mcpServers": {
    "safebreach-config-staging": {
      "command": "cmd",
      "args": [
        "/c",
        "npx",
        "mcp-remote@0.1.24",
        "http://your-server-ip:8000/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-auth-token-here"
      ]
    },
    "safebreach-data-staging": {
      "command": "cmd",
      "args": [
        "/c",
        "npx",
        "mcp-remote@0.1.24",
        "http://your-server-ip:8001/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-auth-token-here"
      ]
    },
    "safebreach-utilities": {
      "command": "cmd",
      "args": [
        "/c",
        "npx",
        "mcp-remote@0.1.24",
        "http://your-server-ip:8002/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-auth-token-here"
      ]
    },
    "safebreach-playbook": {
      "command": "cmd",
      "args": [
        "/c",
        "npx",
        "mcp-remote@0.1.24",
        "http://your-server-ip:8003/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-auth-token-here"
      ]
    }
  }
}
```

> **Note for Windows Users**: 
> - Use `"command": "cmd"` instead of `"npx"`
> - Add `"/c"` as the first argument
> - Add `--allow-http` flag for HTTP connections (if not using HTTPS)

#### Remote Server Configuration

**For External/Production Servers with Authentication:**
```json
{
  "mcpServers": {
    "safebreach-data-staging": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://100.117.2.202:8001/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-secure-token-here"
      ]
    },
    "safebreach-config-staging": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://100.117.2.202:8000/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-secure-token-here"
      ]
    },
    "safebreach-utils-staging": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://100.117.2.202:8002/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-secure-token-here"
      ]
    },
    "safebreach-playbook-staging": {
      "command": "npx",
      "args": [
        "mcp-remote@0.1.24",
        "http://100.117.2.202:8003/sse",
        "--transport",
        "http-first",
        "--allow-http",
        "--header",
        "Authorization: Bearer your-secure-token-here"
      ]
    }
  }
}
```

#### OAuth 2.0 Automatic Discovery Support

The MCP servers support OAuth 2.0 discovery for automatic authentication with compatible clients:

**Supported OAuth 2.0 Endpoints:**
- `/.well-known/oauth-protected-resource` - OAuth discovery metadata
- `/.well-known/oauth-authorization-server/sse` - OAuth authorization server metadata
- `/register` (POST) - Dynamic client registration
- `/auth` (GET) - Authorization endpoint (requires Bearer token)
- `/token` (POST) - Token endpoint (requires Bearer token)

**Security Features:**
- OAuth discovery endpoints are publicly accessible (required for OAuth specification compliance)
- Authorization and token endpoints require valid Bearer token authentication
- OAuth flow integrates with existing Bearer token system
- Full PKCE (Proof Key for Code Exchange) support for secure flows

#### Configuration Best Practices

1. **Development**: Use localhost configuration for local development
2. **Production**: Use remote server configuration with proper authentication tokens
3. **Authentication**: Always use Bearer tokens for external/production servers
4. **Token Security**: Keep authentication tokens secure and rotate them periodically

#### Getting the Authentication Token

For remote servers with authentication enabled, you need the Bearer token:

```bash
# Get token from deployment script output
python deploy_safebreach_mcp.py status --host your-server-ip

# Or check the environment file on the remote server
ssh user@server "cat ~/.config/safebreach-mcp/environment | grep SAFEBREACH_MCP_AUTH_TOKEN"
```

#### Troubleshooting Claude Desktop Connection

| Issue | Solution |
|-------|----------|
| **Connection Failed** | Verify server is running: `curl http://your-server-ip:8001/sse` |
| **Authentication Failed** | Check Bearer token: `curl -H "Authorization: Bearer your-token" http://your-server-ip:8001/sse` |
| **Tool Loading Failed** | Verify JSON syntax, check for extra commas, ensure `npx` is in PATH |
| **mcp-remote@0.1.24 Not Found** | Install globally: `npm install -g @anthropic/mcp-remote@0.1.24` |

After updating the configuration file, restart Claude Desktop for changes to take effect.


## API Reference 📚

The MCP server exposes the following tools for SafeBreach operations:

### Available Tools

#### Multi-Server Distribution

**Config Server (Port 8000):**
1. **`get_console_simulators`** ✨ **Enhanced with Filtering**
2. **`get_simulator_details`**

**Data Server (Port 8001):**
3. **`get_tests_history`** ✨ **Enhanced with Filtering**
4. **`get_test_details`** ✨ **Enhanced with Optional Statistics**
5. **`get_test_simulations`** ✨ **Enhanced with Filtering**
6. **`get_simulation_details`** ✨ **Enhanced with Optional Extensions**
7. **`get_security_controls_events`** ✨ **NEW** - Security control events with filtering
8. **`get_security_control_event_details`** ✨ **NEW** - Detailed security event with verbosity levels
9. **`get_test_findings_counts`** ✨ **NEW** - Findings summary by type with filtering
10. **`get_test_findings_details`** ✨ **NEW** - Detailed findings with comprehensive filtering

**Playbook Server (Port 8003):**
11. **`get_playbook_attacks`** ✨ **NEW** - Filtered and paginated playbook attacks with comprehensive filtering
12. **`get_playbook_attack_details`** ✨ **NEW** - Detailed attack information with verbosity options

**Utilities Server (Port 8002):**
13. **`convert_datetime_to_epoch`**
14. **`convert_epoch_to_datetime`**

#### Tool Details

1. **`get_console_simulators`** ✨ **Enhanced with Filtering**
   - Retrieves filtered SafeBreach simulators for a given console
   - Parameters: 
     - `console` (string, required) - SafeBreach console name
     - `status_filter` (string, optional) - Filter by "connected", "disconnected", "enabled", "disabled", or None for all
     - `name_filter` (string, optional) - Case-insensitive partial match on simulator name
     - `label_filter` (string, optional) - Case-insensitive partial match on simulator labels
     - `os_type_filter` (string, optional) - Filter by OS type (e.g., "Linux", "Windows")
     - `critical_only` (bool, optional) - Filter for critical simulators only (True/False/None)
     - `order_by` (string, default "name") - Sort field: "name", "id", "version", "isConnected", "isEnabled"
     - `order_direction` (string, default "asc") - Sort direction: "asc" or "desc"
   - Returns: Enhanced response with `simulators`, `total_simulators`, and `applied_filters`

2. **`get_simulator_details`**
   - Gets detailed information about a specific simulator
   - Parameters: `console` (string), `simulator_id` (string)
   - Returns: Complete simulator configuration and host details

3. **`get_tests_history`** ✨ **Enhanced with Filtering**
   - Retrieves filtered and paginated test execution history
   - Parameters: 
     - `console` (string, required) - SafeBreach console name
     - `page_number` (int, default 0) - Page number (0-based)
     - `test_type` (string, optional) - Filter by "validate" (BAS), "propagate" (ALM), or None for all
     - `start_date` (int, optional) - Filter tests with end_time >= start_date (Unix timestamp)
     - `end_date` (int, optional) - Filter tests with end_time <= end_date (Unix timestamp)
     - `status_filter` (string, optional) - Filter by "completed", "canceled", "failed", or None for all
     - `name_filter` (string, optional) - Case-insensitive partial match on test name
     - `order_by` (string, default "end_time") - Sort field: "end_time", "start_time", "name", "duration"
     - `order_direction` (string, default "desc") - Sort direction: "desc" or "asc"
   - Returns: Enhanced response with `total_tests`, `applied_filters`, and filtered results

4. **`get_test_details`** ✨ **Enhanced with Optional Statistics**
   - Gets comprehensive details for a specific test
   - Parameters: 
     - `console` (string, required) - SafeBreach console name
     - `test_id` (string, required) - Test ID to get details for
     - `include_simulations_statistics` (bool, optional, default False) - Include detailed simulation statistics breakdown
   - Returns: Test details with optional simulation statistics by status

5. **`get_test_simulations`** ✨ **Enhanced with Filtering**
   - Retrieves filtered and paginated simulations within a test
   - Parameters: 
     - `console` (string, required) - SafeBreach console name
     - `test_id` (string, required) - Test ID to get simulations for
     - `page_number` (int, default 0) - Page number (0-based)
     - `status_filter` (string, optional) - Filter by simulation status (e.g., "missed", "stopped", "prevented", "reported", "logged")
     - `start_time` (int, optional) - Filter simulations with end_time >= start_time (Unix timestamp)
     - `end_time` (int, optional) - Filter simulations with end_time <= end_time (Unix timestamp)
     - `playbook_attack_id_filter` (string, optional) - Filter by exact playbook attack ID match
     - `playbook_attack_name_filter` (string, optional) - Filter by partial playbook attack name match (case-insensitive)
   - Returns: Enhanced response with `total_simulations`, `applied_filters`, and filtered results

6. **`get_simulation_details`** ✨ **Enhanced with Optional Extensions**
   - Gets detailed results for a specific simulation
   - Parameters: 
     - `console` (string, required) - SafeBreach console name
     - `simulation_id` (string, required) - Simulation ID to get details for
     - `include_mitre_techniques` (bool, optional, default False) - Include MITRE ATT&CK technique details
     - `include_full_attack_logs` (bool, optional, default False) - Include detailed attack logs by host
     - `include_simulation_logs` (bool, optional, default False) - Include simulation execution logs
   - Returns: Complete simulation results with optional extensions

7. **`get_security_controls_events`** ✨ **NEW** - Security Control Events with Filtering
   - Retrieves filtered and paginated security control events from SafeBreach SIEM logs
   - Parameters:
     - `console` (string, required) - SafeBreach console name
     - `test_id` (string, required) - Test ID to get security events for
     - `simulation_id` (string, required) - Simulation ID to get security events for
     - `page_number` (int, default 0) - Page number (0-based)
     - `product_name_filter` (string, optional) - Filter by security product name (case-insensitive partial match)
     - `vendor_name_filter` (string, optional) - Filter by security product vendor (case-insensitive partial match)
     - `security_action_filter` (string, optional) - Filter by security action (e.g., "block", "allow", "detect")
     - `connector_name_filter` (string, optional) - Filter by connector name (case-insensitive partial match)
     - `source_host_filter` (string, optional) - Filter by source host (case-insensitive partial match)
     - `destination_host_filter` (string, optional) - Filter by destination host (case-insensitive partial match)
   - Returns: Filtered security control events with pagination and applied filters metadata

8. **`get_security_control_event_details`** ✨ **NEW** - Detailed Security Event with Verbosity Levels
   - Gets comprehensive details for a specific security control event with configurable verbosity
   - Parameters:
     - `console` (string, required) - SafeBreach console name
     - `test_id` (string, required) - Test ID containing the security event
     - `simulation_id` (string, required) - Simulation ID containing the security event
     - `event_id` (string, required) - Security event ID to get details for
     - `verbosity_level` (string, default "standard") - Detail level: "minimal", "standard", "detailed", "full"
   - Returns: Security event details with verbosity-controlled fields
   - Verbosity Levels:
     - **minimal**: Basic identification (timestamp, product, action)
     - **standard**: Common fields (adds source/destination, rule info)
     - **detailed**: Extended fields (adds technical details, metadata)
     - **full**: All available fields (complete event data)

9. **`get_test_findings_counts`** ✨ **NEW** - Findings Summary with Filtering
   - Returns counts of findings by type for a specific test with optional attribute filtering
   - Parameters:
     - `console` (string, required) - SafeBreach console name
     - `test_id` (string, required) - Test ID to get findings counts for
     - `attribute_filter` (string, optional) - Filter by any finding attribute with partial case-insensitive matching
   - Returns: Summary of findings counts by type with applied filters metadata
   - Useful for: Getting an overview of security findings identified during Propagate tests
   - Filtering: Supports partial matching across all finding attributes including type, source, severity, hostname, IP addresses, ports, protocols, and nested data structures
   - Note: Uses the propagateSummary API to retrieve test-level findings across all simulations

10. **`get_test_findings_details`** ✨ **NEW** - Detailed Findings with Comprehensive Filtering
   - Returns detailed findings for a specific test with comprehensive filtering and pagination
   - Parameters:
     - `console` (string, required) - SafeBreach console name
     - `test_id` (string, required) - Test ID to get detailed findings for
     - `page_number` (int, default 0) - Page number for pagination (0-based)
     - `attribute_filter` (string, optional) - Filter by any finding attribute with partial case-insensitive matching
   - Returns: Detailed findings with pagination metadata and applied filters information
   - Useful for: Deep analysis of security findings similar to penetration test reports
   - Filtering: Advanced attribute search across all finding fields including nested objects, arrays, and complex data structures
   - Note: Retrieves test-level findings across all simulations (not simulation-specific findings)

#### Utility Tools

11. **`convert_datetime_to_epoch`**
   - Converts ISO datetime strings to Unix epoch timestamps
   - Parameters: `datetime_str` (string, required) - ISO format datetime string
   - Returns: Epoch timestamp and parsing details
   - Useful for: Preparing datetime values for SafeBreach API filtering

11. **`get_playbook_attacks`** ✨ **NEW** - Filtered and Paginated Playbook Attacks
   - Retrieves filtered and paginated SafeBreach playbook attacks from the comprehensive attack knowledge base
   - Parameters:
     - `console` (string, required) - SafeBreach console name
     - `page_number` (int, default 0) - Page number (0-based)
     - `name_filter` (string, optional) - Case-insensitive partial match on attack name
     - `description_filter` (string, optional) - Case-insensitive partial match on attack description
     - `id_min` (int, optional) - Minimum attack ID for range filtering
     - `id_max` (int, optional) - Maximum attack ID for range filtering
     - `modified_date_start` (string, optional) - Filter attacks modified after this ISO date
     - `modified_date_end` (string, optional) - Filter attacks modified before this ISO date
     - `published_date_start` (string, optional) - Filter attacks published after this ISO date
     - `published_date_end` (string, optional) - Filter attacks published before this ISO date
   - Returns: Paginated list of attacks with filtering metadata
   - Useful for: Browsing and searching the SafeBreach attack playbook

12. **`get_playbook_attack_details`** ✨ **NEW** - Detailed Attack Information
   - Gets comprehensive details for a specific SafeBreach playbook attack with configurable verbosity
   - Parameters:
     - `console` (string, required) - SafeBreach console name
     - `attack_id` (int, required) - Attack ID to get details for
     - `include_fix_suggestions` (bool, optional, default False) - Include remediation suggestions
     - `include_tags` (bool, optional, default False) - Include attack classification tags
     - `include_parameters` (bool, optional, default False) - Include attack configuration parameters
   - Returns: Complete attack details with optional extensions
   - Useful for: Understanding specific attack techniques and their remediation

13. **`convert_datetime_to_epoch`**
   - Converts ISO datetime strings to Unix epoch timestamps
   - Parameters: `datetime_str` (string, required) - ISO format datetime string
   - Returns: Epoch timestamp and parsing details
   - Useful for: Preparing datetime values for SafeBreach API filtering

14. **`convert_epoch_to_datetime`**
   - Converts Unix epoch timestamps to readable datetime strings
   - Parameters: 
     - `epoch_timestamp` (int, required) - Unix timestamp as integer
     - `timezone` (string, optional, default "UTC") - Timezone for output
   - Returns: ISO datetime string and formatted information
   - Useful for: Interpreting epoch timestamps from SafeBreach API responses

### Usage Examples

**Basic simulator retrieval (unchanged for backward compatibility):**
```python
# Get all simulators
simulators = get_console_simulators("sample-console")
```

**Filter simulators by status:**
```python
# Get only connected simulators
connected_sims = get_console_simulators("sample-console", status_filter="connected")

# Get only enabled simulators
enabled_sims = get_console_simulators("sample-console", status_filter="enabled")
```

**Filter by OS type and criticality:**
```python
# Get critical Linux simulators only
critical_linux = get_console_simulators("sample-console", os_type_filter="Linux", critical_only=True)

# Get Windows simulators ordered by version
windows_sims = get_console_simulators("sample-console", os_type_filter="Windows", order_by="version", order_direction="desc")
```

**Search by name and labels:**
```python
# Find simulators with "server" in name
servers = get_console_simulators("sample-console", name_filter="server")

# Find production simulators
production_sims = get_console_simulators("sample-console", label_filter="production")
```

**Combined filtering:**
```python
# Get connected, enabled, non-critical Linux simulators ordered by name
result = get_console_simulators(
    console="sample-console",
    status_filter="connected",
    os_type_filter="Linux", 
    critical_only=False,
    order_by="name",
    order_direction="asc"
)
```

**Basic test history usage (unchanged for backward compatibility):**
```python
# Get first page of all tests
tests = get_tests_history("sample-console", 0)
```

**Filter by test type:**
```python
# Get only validation tests (BAS)
validation_tests = get_tests_history("sample-console", test_type="validate")

# Get only propagation tests (ALM)
propagation_tests = get_tests_history("sample-console", test_type="propagate")
```

**Filter by time window:**
```python
import time

# Get tests from last 7 days
week_ago = int(time.time()) - (7 * 24 * 3600)
recent_tests = get_tests_history("sample-console", start_date=week_ago)

# Get tests from specific date range
start_date = 1640995200  # 2022-01-01
end_date = 1641081600    # 2022-01-02
tests_jan_1_2 = get_tests_history("sample-console", start_date=start_date, end_date=end_date)
```

**Filter by status and name:**
```python
# Get failed tests only
failed_tests = get_tests_history("sample-console", status_filter="failed")

# Search for specific test campaigns
quarterly_tests = get_tests_history("sample-console", name_filter="quarterly")
```

**Custom ordering:**
```python
# Get tests ordered by name alphabetically
tests_by_name = get_tests_history("sample-console", order_by="name", order_direction="asc")

# Get oldest tests first
oldest_tests = get_tests_history("sample-console", order_direction="asc")
```

**Combined filters:**
```python
# Get completed validation tests from last month, ordered by duration
last_month = int(time.time()) - (30 * 24 * 3600)
results = get_tests_history(
    console="sample-console",
    test_type="validate",
    status_filter="completed", 
    start_date=last_month,
    order_by="duration",
    order_direction="desc"
)
```

**Basic simulation retrieval (unchanged for backward compatibility):**
```python
# Get all simulations for a test
simulations = get_test_simulations("sample-console", "test-id-123", 0)
```

**Filter simulations by status:**
```python
# Get only missed simulations (successful attacks)
missed_sims = get_test_simulations("sample-console", "test-id-123", 0, status_filter="missed")

# Get only prevented simulations
prevented_sims = get_test_simulations("sample-console", "test-id-123", 0, status_filter="prevented")

# Get only stopped simulations
stopped_sims = get_test_simulations("sample-console", "test-id-123", 0, status_filter="stopped")
```

**Filter by time window:**
```python
import time

# Get simulations from last 24 hours
day_ago = int(time.time()) - (24 * 3600)
recent_sims = get_test_simulations("sample-console", "test-id-123", 0, start_time=day_ago)

# Get simulations from specific time range
start_time = 1640995200  # 2022-01-01
end_time = 1641081600    # 2022-01-02
sims_jan_1_2 = get_test_simulations("sample-console", "test-id-123", 0, start_time=start_time, end_time=end_time)
```

**Filter by playbook attack details:**
```python
# Get simulations for specific attack ID
attack_sims = get_test_simulations("sample-console", "test-id-123", 0, playbook_attack_id_filter="ATT-1234")

# Search for file-related attacks
file_attacks = get_test_simulations("sample-console", "test-id-123", 0, playbook_attack_name_filter="file")

# Search for credential attacks
cred_attacks = get_test_simulations("sample-console", "test-id-123", 0, playbook_attack_name_filter="credential")
```

**Combined simulation filters:**
```python
# Get missed file-related attacks from last week
week_ago = int(time.time()) - (7 * 24 * 3600)
results = get_test_simulations(
    console="sample-console",
    test_id="test-id-123",
    page_number=0,
    status_filter="missed",
    start_time=week_ago,
    playbook_attack_name_filter="file"
)

# Get all network attacks that were prevented or stopped
network_blocked = get_test_simulations(
    console="sample-console",
    test_id="test-id-123", 
    page_number=0,
    playbook_attack_name_filter="network"
)
# Note: Filter by status in separate calls since status_filter accepts single value
```

**Security control events usage:**
```python
# Get all security control events for a simulation
events = get_security_controls_events("sample-console", "test-id-123", "sim-id-456")

# Filter by security product vendor
firewall_events = get_security_controls_events(
    console="sample-console",
    test_id="test-id-123", 
    simulation_id="sim-id-456",
    vendor_name_filter="Palo Alto"
)

# Filter by security action (blocked events)
blocked_events = get_security_controls_events(
    console="sample-console",
    test_id="test-id-123",
    simulation_id="sim-id-456", 
    security_action_filter="block"
)

# Combined filters: antivirus detections on specific host
av_detections = get_security_controls_events(
    console="sample-console",
    test_id="test-id-123",
    simulation_id="sim-id-456",
    product_name_filter="antivirus",
    source_host_filter="workstation-01",
    security_action_filter="detect"
)
```

**Security event details with verbosity:**
```python
# Basic event details (standard verbosity)
event = get_security_control_event_details("sample-console", "test-123", "sim-456", "event-789")

# Minimal details for overview
minimal = get_security_control_event_details(
    console="sample-console",
    test_id="test-123", 
    simulation_id="sim-456",
    event_id="event-789",
    verbosity_level="minimal"
)

# Full details for investigation
full_details = get_security_control_event_details(
    console="sample-console",
    test_id="test-123",
    simulation_id="sim-456", 
    event_id="event-789",
    verbosity_level="full"
)
```

**Test findings usage:**
```python
# Get basic findings counts for a test
findings_summary = get_test_findings_counts("sample-console", "test-id-123")

# Filter findings by type
credential_findings = get_test_findings_counts(
    console="sample-console",
    test_id="test-id-123",
    attribute_filter="credential"
)

# Filter by severity level
high_severity_findings = get_test_findings_counts(
    console="sample-console", 
    test_id="test-id-123",
    attribute_filter="high"
)

# Get detailed findings (first page)
detailed_findings = get_test_findings_details("sample-console", "test-id-123")

# Filter detailed findings by hostname
host_findings = get_test_findings_details(
    console="sample-console",
    test_id="test-id-123",
    page_number=0,
    attribute_filter="workstation-01"
)

# Filter by port or protocol
port_findings = get_test_findings_details(
    console="sample-console",
    test_id="test-id-123",
    attribute_filter="3389"
)

# Search across all attributes (case-insensitive)
search_findings = get_test_findings_details(
    console="sample-console",
    test_id="test-id-123",
    attribute_filter="rdp"
)

# Paginate through results
page_2_findings = get_test_findings_details(
    console="sample-console",
    test_id="test-id-123",
    page_number=1,
    attribute_filter="open"
)
```

**Playbook attack usage:**
```python
# Get all playbook attacks (first page)
attacks = get_playbook_attacks("sample-console")

# Filter attacks by name
file_attacks = get_playbook_attacks("sample-console", name_filter="file")

# Filter attacks by ID range
recent_attacks = get_playbook_attacks("sample-console", id_min=3000, id_max=4000)

# Filter attacks by modification date
import datetime
start_date = "2024-01-01T00:00:00Z"
recent_modified = get_playbook_attacks(
    console="sample-console",
    modified_date_start=start_date
)

# Combined filtering: credential attacks from specific time period
cred_attacks = get_playbook_attacks(
    console="sample-console",
    name_filter="credential",
    description_filter="harvest",
    published_date_start="2020-01-01T00:00:00Z"
)

# Get detailed attack information (basic)
attack_details = get_playbook_attack_details(
    console="sample-console",
    attack_id=3405
)

# Get attack details with all optional information
full_attack_details = get_playbook_attack_details(
    console="sample-console",
    attack_id=3405,
    include_fix_suggestions=True,
    include_tags=True,
    include_parameters=True
)

# Get attack details with specific verbosity options
attack_with_fixes = get_playbook_attack_details(
    console="sample-console",
    attack_id=3405,
    include_fix_suggestions=True,
    include_tags=False,
    include_parameters=False
)
```

## Testing 🧪

The project includes a comprehensive test suite with 100% code coverage.

### Running Tests

```bash
# Run all multi-server tests
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ tests/ -v

# Run authentication tests
uv run python tests/run_auth_tests.py --quick --verbose

# Run specific server test suites
uv run pytest safebreach_mcp_config/tests/ -v  # Config server tests
uv run pytest safebreach_mcp_data/tests/ -v    # Data server tests  
uv run pytest safebreach_mcp_utilities/tests/ -v # Utilities server tests
uv run pytest safebreach_mcp_playbook/tests/ -v # Playbook server tests

# Run with coverage report
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ tests/ --cov=. --cov-report=html
```

### VS Code Integration

The project includes VS Code launch configurations for easy testing:

1. Press `F5` in VS Code
2. Select from available test configurations:
   - `Run All Tests` - Complete test suite
   - `Run Unit Tests` - Unit tests only
   - `Run Integration Tests` - Integration tests only
   - `Run Tests with Coverage` - Tests with coverage analysis
   - `Debug Specific Test` - Debug individual tests

Tests are auto-discovered in VS Code Test Explorer.

## Development 🔧

### Project Structure

```
.
├── safebreach_mcp_core/                # Shared components
│   ├── __init__.py
│   ├── safebreach_auth.py              # Centralized authentication
│   ├── safebreach_base.py              # Base MCP server class
│   ├── datetime_utils.py               # Datetime utilities
│   ├── environments_metadata.py        # Environment configurations
│   ├── secret_utils.py                 # Factory facade for secure credential management
│   └── secret_providers.py             # Pluggable secret provider interface
├── safebreach_mcp_config/              # Config server (Port 8000)
│   ├── __init__.py
│   ├── config_server.py                # Config MCP server
│   ├── config_functions.py             # Simulator business logic
│   ├── config_types.py                 # Simulator data transformations
│   └── tests/                          # Config server tests
│       ├── __init__.py
│       └── test_config_functions.py
├── safebreach_mcp_data/                # Data server (Port 8001)
│   ├── __init__.py
│   ├── data_server.py                  # Data MCP server
│   ├── data_functions.py               # Test/simulation/security event business logic
│   ├── data_types.py                   # Test/simulation/security event data transformations
│   └── tests/                          # Data server tests
│       ├── __init__.py
│       ├── test_data_functions.py
│       ├── test_data_types.py
│       └── test_integration.py
├── safebreach_mcp_utilities/           # Utilities server (Port 8002)
│   ├── __init__.py
│   ├── utilities_server.py             # Utilities MCP server
│   └── tests/                          # Utilities server tests
│       ├── __init__.py
│       └── test_utilities_server.py
├── safebreach_mcp_playbook/            # Playbook server (Port 8003)
│   ├── __init__.py
│   ├── playbook_server.py              # Playbook MCP server
│   ├── playbook_functions.py           # Playbook attack business logic
│   ├── playbook_types.py               # Playbook attack data transformations
│   └── tests/                          # Playbook server tests
│       ├── __init__.py
│       ├── test_playbook_functions.py
│       ├── test_playbook_server.py
│       ├── test_playbook_types.py
│       ├── test_integration.py
│       └── test_e2e.py
├── tests/                              # Authentication and integration tests
│   ├── __init__.py
│   ├── pytest.ini                     # Pytest configuration
│   ├── README.md                       # Test documentation
│   ├── run_auth_tests.py               # Authentication test suite runner
│   └── test_external_authentication.py # Authentication wrapper unit tests
├── start_all_servers.py                # Concurrent multi-server launcher
├── mcp_server_bug_423_hotfix.py        # MCP initialization fix
├── .gitignore                          # Git ignore patterns
├── CLAUDE.md                           # Claude Code guidance
├── DESIGN.md                           # Design documentation
├── MANIFEST.in                         # Package manifest
├── pyproject.toml                      # Project configuration
├── README.md                           # Project documentation
├── requirements.txt                    # Python dependencies
└── uv.lock                             # UV lockfile
```

### Caching Behavior

The multi-server architecture implements intelligent caching with server-specific optimization:

**Config Server:**
- **Simulator Cache**: 1-hour TTL for simulator data per console
- **Console Isolation**: Separate caches per SafeBreach console

**Data Server:**
- **Test Cache**: 1-hour TTL for test history data per console
- **Simulation Cache**: 1-hour TTL for simulation results per test
- **Security Events Cache**: 1-hour TTL for security control events per simulation
- **Findings Cache**: 1-hour TTL for test findings data per test
- **Console/Test Isolation**: Separate caches per SafeBreach console and test

**Utilities Server:**
- **Stateless**: No caching (pure utility functions)

**Common Features:**
- **Automatic Expiration**: Stale data automatically refreshed
- **Cache Isolation**: Each server maintains its own cache

### Adding New Environments

**Method 1: Edit `environments_metadata.py` directly**
```python
safebreach_envs["new-console"] = {
    "url": "new-console.safebreach.com",
    "account": "account_id",
    "secret_config": {
        "provider": "aws_ssm",  # or "aws_secrets_manager" or "env_var"
        "parameter_name": "new-console-apitoken"
    }
}
```

**Method 2: Use JSON file for dynamic loading (recommended)**
1. Create a JSON file (e.g., `my_consoles.json`):
```json
{
    "new-console": {
        "url": "new-console.safebreach.com",
        "account": "account_id",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "new-console-apitoken"
        }
    }
}
```

2. Set environment variable and token:
```bash
export SAFEBREACH_ENVS_FILE=/path/to/my_consoles.json
export NEW_CONSOLE_APITOKEN="your-api-token"
```

**Method 3: Store token in AWS (for aws_ssm or aws_secrets_manager providers)**
```bash
# For AWS SSM
aws ssm put-parameter --name "new-console-apitoken" --value "your-api-token" --type "SecureString"

# For AWS Secrets Manager
aws secretsmanager create-secret --name "safebreach/new-console/api-token" --secret-string "your-api-token"
```

## Troubleshooting 🔍

### Common Issues

| Issue | Solution |
|-------|----------|
| **Server fails to start** | Verify Python 3.12+, run `uv sync`, check AWS credentials |
| **API authentication errors** | Check tokens in AWS SSM, verify naming: `{console-name}-apitoken` |
| **Cache issues** | Caches expire after 1 hour, restart server to clear |
| **Test failures** | Install pytest/pytest-mock, run from project root |

### Remote MCP Server Issues

**✅ RESOLVED: External Connection Middleware Bug:**
- **Error**: `'function' object has no attribute 'middleware'` when using `--external` flag (FIXED)
- **Root Cause**: Outdated MCP SDK version (1.11.0) and missing updated code on remote server
- **Resolution**: Updated MCP SDK to 1.12.1 and deployed latest authentication wrapper code
- **Current Status**: External connections fully operational with Bearer token authentication
- **Access**: Direct external connections working: `curl -H "Authorization: Bearer token" http://server:port/sse`

**Middleware Bug Fix Summary:**
1. **Root Cause**: Outdated MCP SDK (1.11.0) + missing code updates
2. **Fix Applied**: Upgraded to MCP SDK 1.12.1 + deployed latest safebreach_base.py
3. **Result**: External connections with Bearer token authentication fully operational
4. **Validation**: Authentication working (401 without token, passes with valid token)

## Security Considerations 🔒

- **Default Security**: All servers bind to localhost (127.0.0.1) by default - no external access
- **External Access Control**: Optional external connections require explicit configuration and Bearer token authentication
- **Authentication Bypass**: Localhost connections automatically bypass authentication for development convenience
- **API Token Storage**: SafeBreach API tokens stored securely in AWS SSM Parameter Store or environment variables
- **No Data Logging**: No sensitive data is logged or cached locally
- **HTTPS Enforcement**: HTTPS enforced for all SafeBreach API communications
- **Connection Timeouts**: Timeout controls prevent hanging connections (120 seconds)
- **Security Warnings**: Comprehensive logging when external access is enabled
- **Token Validation**: Bearer token validation for all external requests with proper error responses

## Package Information 📦

The project provides multiple installation options with various entry points:

**Multi-Server Entry Points:**
- **`safebreach-mcp-all-servers`**: Concurrent multi-server launcher (recommended)
- **`safebreach-mcp-config-server`**: Config server only (Port 8000)
- **`safebreach-mcp-data-server`**: Data server only (Port 8001)
- **`safebreach-mcp-utilities-server`**: Utilities server only (Port 8002)
- **`safebreach-mcp-playbook-server`**: Playbook server only (Port 8003)

**Package Details:**
- **Package Name**: safebreach-mcp-server
- **Version**: 1.1.0
- **Dependencies**: boto3, requests, mcp (see pyproject.toml)
- **Python Version**: 3.12+
- **Distribution**: Available via git+ssh or git+https installation

## Contributing 🤝

1. Create feature branch from `master`
2. Write tests for new functionality (maintain 100% coverage)
3. Update documentation as needed
4. Run full test suite before submitting PR
5. Follow existing code style and patterns

### Code Quality

- Maintain 100% test coverage
- Use type hints for all function parameters
- Include comprehensive docstrings
- Follow existing error handling patterns
