# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚨 SECURITY FIRST - CRITICAL FOR CLAUDE

**IMPORTANT**: Claude should always be launched using the secure launcher to ensure full project context and security awareness:

```bash
# ALWAYS use this command to launch Claude:
./claude-launcher.sh
```

**This ensures Claude has:**
- ✅ Complete project architecture and best practices knowledge
- ✅ Security context and awareness of token handling rules
- ✅ Current git status and environment configuration
- ✅ Pre-validated secure working environment

**NEVER commit real secrets:**
- Use placeholders like `your-token-here`, `REPLACE_WITH_ACTUAL_TOKEN`
- Use environment variables: `${API_TOKEN}`, `$SAFEBREACH_TOKEN`
- Pre-commit hooks will automatically scan for and block real secrets

📚 **See TEAM_WORKFLOW.md for complete security practices and development workflow.**

## Development Commands

**Running the Multi-Server Architecture (Recommended):**
```bash
# Run all servers concurrently on ports 8000, 8001, 8002 (localhost-only, secure default)
uv run start_all_servers.py


# External connection support (requires authentication token)
SAFEBREACH_MCP_AUTH_TOKEN="your-secure-token" uv run start_all_servers.py --external

# External connections for specific servers only
SAFEBREACH_MCP_AUTH_TOKEN="your-token" uv run start_all_servers.py --external-data --external-utilities

# Get help with all external connection options
uv run start_all_servers.py --help
```

**Running Individual Servers:**
```bash
# Config server (simulators) - Port 8000 (localhost-only by default)
uv run -m safebreach_mcp_config.config_server

# Data server (tests/simulations) - Port 8001 (localhost-only by default)
uv run -m safebreach_mcp_data.data_server

# Utilities server (datetime functions) - Port 8002 (localhost-only by default)
uv run -m safebreach_mcp_utilities.utilities_server

# Playbook server (attack knowledge base) - Port 8003 (localhost-only by default)
uv run -m safebreach_mcp_playbook.playbook_server

# Individual servers with external connections
SAFEBREACH_MCP_AUTH_TOKEN="your-token" SAFEBREACH_MCP_DATA_EXTERNAL=true uv run -m safebreach_mcp_data.data_server
```


**Running the MCP Server (Remote Installation):**
```bash
# Install and run from git repository
uv tool install git+ssh://git@github.com/SafeBreach/safebreach-mcp.git
export PATH="$HOME/.local/bin:$PATH"  # If needed

# Run multi-server architecture (localhost-only by default)
safebreach-mcp-all-servers

# Run with external connections
SAFEBREACH_MCP_AUTH_TOKEN="your-secure-token" safebreach-mcp-all-servers --external

# Or run individual servers
safebreach-mcp-config-server    # Port 8000
safebreach-mcp-data-server      # Port 8001
safebreach-mcp-utilities-server # Port 8002
safebreach-mcp-playbook-server  # Port 8003

```


**Installing Dependencies:**
```bash
uv sync
```

**Running Tests:**
```bash
# Run all multi-server tests
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/

# Run specific server test suites
uv run pytest safebreach_mcp_config/tests/                   # Config server tests
uv run pytest safebreach_mcp_data/tests/                     # Data server tests  
uv run pytest safebreach_mcp_utilities/tests/               # Utilities server tests
uv run pytest safebreach_mcp_playbook/tests/                # Playbook server tests
uv run pytest safebreach_mcp_data/tests/test_integration.py # Multi-server integration tests

# Run with verbose output and coverage
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ -v --cov=. --cov-report=html

# Run only unit/integration tests (skip end-to-end tests that require real SafeBreach environments)
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ -m "not e2e"

# Run quick authentication test suite
uv run python tests/run_auth_tests.py --quick --verbose
```

**VS Code Integration:**
Use Run and Debug (F5) with these configurations:
- `Run All Tests` - Execute complete test suite (excludes end-to-end tests)
- `Run Unit Tests` - Execute only unit tests
- `Run Integration Tests` - Execute only integration tests  
- `Run Tests with Coverage` - Execute tests with coverage report
- `Debug Specific Test` - Debug a single test with breakpoints

Tests are auto-discovered in VS Code Test Explorer. **Note**: End-to-end tests (`@pytest.mark.e2e`) are excluded by default in VS Code as they require real SafeBreach environments and AWS credentials.

## Authentication Testing

The project includes comprehensive test coverage for external connection authentication:

**Test Files:**
- `tests/test_external_authentication.py` - Authentication wrapper and configuration unit testing (no server startup required) 
- `tests/run_auth_tests.py` - Comprehensive authentication test suite runner

**Test Coverage:**
- ✅ **Authentication token generation and management** - Secure token creation and preservation
- ✅ **Re-entrant deployment token preservation** - Existing tokens maintained across deployments  
- ✅ **Claude Desktop configuration generation** - Correct Bearer token integration
- ✅ **Multi-server launcher authentication** - Consistent auth across all servers
- ✅ **Environment variable configuration** - Proper auth token handling
- ✅ **systemd service authentication setup** - Deployment script integration
- ✅ **Localhost authentication bypass** - Development-friendly localhost access
- ✅ **Security warning logging** - Proper security notifications
- ✅ **ASGI authentication wrapper** - HTTP request authentication enforcement
- ✅ **OAuth 2.0 discovery endpoint validation** - Preliminary support for OAuth functionality
- ✅ **Multi-server architecture verification** - All three servers working together

**Test Markers:**
- `@pytest.mark.e2e` - End-to-end tests requiring real SafeBreach environments and AWS credentials
- `@pytest.mark.auth` - Authentication and authorization specific tests
- `@pytest.mark.deployment` - Deployment script authentication tests

**Running Authentication Tests:**
```bash
# Quick authentication test suite (recommended)
uv run python tests/run_auth_tests.py --quick

# Full authentication test suite with server startup tests
uv run python tests/run_auth_tests.py --verbose

# Authentication tests with coverage
uv run python tests/run_auth_tests.py --coverage

# Individual test files
uv run pytest tests/test_external_authentication.py -v
```

## OAuth 2.0 Implementation

The SafeBreach MCP servers include a complete OAuth 2.0 Authorization Server implementation for seamless Claude Desktop integration with `mcp-remote` client compatibility.

### OAuth 2.0 Endpoints

**Discovery Endpoints (Public Access):**
- `/.well-known/oauth-protected-resource` - OAuth 2.0 protected resource metadata
- `/.well-known/oauth-authorization-server/sse` - OAuth 2.0 authorization server metadata

**OAuth Flow Endpoints (Authenticated):**
- `/register` (POST) - Dynamic client registration endpoint
- `/auth` (GET) - Authorization endpoint (requires valid Bearer token)
- `/token` (POST) - Token endpoint (requires valid Bearer token)

### Security Model

**Discovery Security**: OAuth discovery endpoints are publicly accessible as required by OAuth 2.0 specification for client discovery.

**Flow Security**: Authorization and token endpoints require valid Bearer token authentication, ensuring only clients with existing valid tokens can complete the OAuth flow.

**Token Integration**: OAuth token endpoint returns the configured `SAFEBREACH_MCP_AUTH_TOKEN`, seamlessly integrating OAuth and Bearer token authentication systems.

### OAuth Metadata Response

```json
{
  "issuer": "http://server-host:port",
  "authorization_endpoint": "http://server-host:port/auth",
  "token_endpoint": "http://server-host:port/token", 
  "registration_endpoint": "http://server-host:port/register",
  "resource": "http://server-host:port/sse",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "scopes_supported": ["mcp"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post", "none"],
  "code_challenge_methods_supported": ["S256"],
  "registration_endpoint_auth_methods_supported": ["none"]
}
```

### PKCE Support

Full support for Proof Key for Code Exchange (PKCE) with S256 code challenge method for secure authorization flows without requiring client secrets.

## Authentication Debugging

### Investigation Tools

When debugging authentication issues, use these techniques:

**1. Enhanced Server Logging:**
```python
# Add to authenticated_asgi_app for detailed token comparison:
logger.info(f"🔍 AUTH DEBUG from {client_host}: received='{auth_header}' expected='{expected_auth}' equal={auth_header == expected_auth}")
```

**2. Claude Desktop Client Logs:**
Check Claude Desktop logs for actual mcp-remote command arguments:
```
# Look for logs showing exact command and arguments used
args: [
  'mcp-remote',
  'http://server:port/sse',
  '--skip-auth',  // ← Important flag behavior
  '--headers',
  '{"Authorization": "Bearer token"}'
]
```

**3. Server Log Analysis:**
```bash
# Monitor authentication attempts in real-time
sudo journalctl -u safebreach-mcp.service -f | grep -E "(OAuth|Bearer|Auth|🚫|✅)"
```

### Common Authentication Scenarios

**Mixed Success/Failure Patterns**: Normal behavior where mcp-remote tries multiple connection strategies:
- Some attempts succeed with valid Bearer tokens
- Some attempts fail due to missing headers or wrong tokens
- OAuth attempts may fail while regular SSE connections succeed

**Skip-Auth Flag Behavior**: The `--skip-auth` flag in mcp-remote can cause:
- Configured headers to be bypassed
- Alternative authentication mechanisms to be used
- Cached or derived tokens to be used instead of configured ones

**Security Validation Status**: 
- ✅ Authentication system working correctly
- ✅ OAuth endpoints properly secured  
- ✅ Mixed authorized/unauthorized attempts are expected client behavior
- ✅ No authentication bypass vulnerabilities exist

## Architecture Overview

This is a Model Context Protocol (MCP) server that bridges AI agents with SafeBreach's Breach and Attack Simulation platform. The architecture has been refactored from a monolithic design to a **multi-server architecture** with specialized domains:

### Multi-Server Architecture (Recommended)

**Core Shared Components:**
- **`safebreach_mcp_core/`**: Shared components used by all servers
  - `safebreach_auth.py`: Centralized authentication for all servers
  - `safebreach_base.py`: Base class providing common MCP server functionality
  - `datetime_utils.py`: Shared datetime conversion utilities
  - `environments_metadata.py`: Configuration registry for SafeBreach environments
  - `secret_utils.py`: Factory facade for secure credential management
  - `secret_providers.py`: Pluggable secret provider interface

**Specialized Servers:**
- **`safebreach_mcp_config/`**: Config Server (Port 8000)
  - `config_server.py`: FastMCP server for simulator operations
  - `config_functions.py`: Business logic for simulator management
  - `config_types.py`: Data transformations for simulator data
  - **Tools**: `get_console_simulators`, `get_simulator_details`

- **`safebreach_mcp_data/`**: Data Server (Port 8001)
  - `data_server.py`: FastMCP server for test and simulation data
  - `data_functions.py`: Business logic for test/simulation operations
  - `data_types.py`: Data transformations for test/simulation data
  - **Tools**: `get_tests_history`, `get_test_details`, `get_test_simulations`, `get_simulation_details`, `get_security_controls_events`, `get_security_control_event_details`, `get_test_findings_counts`, `get_test_findings_details`, `get_test_drifts`

- **`safebreach_mcp_utilities/`**: Utilities Server (Port 8002)
  - `utilities_server.py`: FastMCP server for utility functions
  - **Tools**: `convert_datetime_to_epoch`, `convert_epoch_to_datetime`

- **`safebreach_mcp_playbook/`**: Playbook Server (Port 8003)
  - `playbook_server.py`: FastMCP server for playbook attack operations
  - `playbook_functions.py`: Business logic for playbook attack management
  - `playbook_types.py`: Data transformations for playbook attack data
  - **Tools**: `get_playbook_attacks`, `get_playbook_attack_details`

**Multi-Server Launchers:**
- **`start_all_servers.py`**: Concurrent multi-server launcher


## Key Design Patterns

**Multi-Server Architecture**: The system uses domain-specific servers that can be deployed independently or together, allowing for:
- **Horizontal Scaling**: Each server can be scaled independently based on demand
- **Domain Separation**: Clear separation of concerns between config, data, and utility operations
- **Fault Isolation**: Issues in one server don't affect others
- **Flexible Deployment**: Deploy all servers together or only what's needed

**Shared Core Components**: All servers inherit from `SafeBreachMCPBase` and use shared components:
- **Centralized Authentication**: `SafeBreachAuth` class handles API authentication across all servers
- **Consistent Error Handling**: Common error handling patterns and timeout configurations
- **Shared Utilities**: datetime conversion functions available to all servers
- **Unified Configuration**: Single source of truth for environment configuration

**Environment Configuration**: SafeBreach environments are configured in `safebreach_mcp_core/environments_metadata.py` with URL, account mappings, and secret storage configuration. Each environment specifies its secret provider (AWS SSM by default) and parameter location. This allows for flexible secret storage backends while maintaining backward compatibility.

**Secret Management**: The system uses a pluggable secret provider interface defined in `secret_providers.py`. Currently supports:
- **AWS SSM Parameter Store** (default): Stores API tokens as secure parameters
- **AWS Secrets Manager**: Alternative for organizations preferring Secrets Manager
- **Extensible Design**: Easy to add new providers (HashiCorp Vault, Kubernetes secrets, etc.)

**Factory Pattern**: `secret_utils.py` acts as a factory facade, automatically selecting the appropriate provider based on environment configuration and providing a simple `get_secret_for_console(console)` interface.

**Caching Strategy**: The system implements intelligent caching with separate caches per server:
- **Config Server**: Simulator data cached per console (1-hour TTL)
- **Data Server**: Test history and simulation data cached per console/test (1-hour TTL)
- **Cache Isolation**: Each server maintains its own cache to prevent interference

**Error Handling**: Functions include timeout configurations (120 seconds for API calls) and comprehensive logging for debugging SafeBreach API interactions.

**Data Pagination**: All listing operations use `PAGE_SIZE = 10` with proper pagination handling for large datasets.

## MCP Tools Available

### Multi-Server Distribution

**Config Server (Port 8000):**
1. `get_console_simulators` ✨ **Enhanced** - Filtered simulator retrieval with status, name, label, OS type, and criticality filtering plus customizable ordering
2. `get_simulator_details` - Get detailed simulator information  

**Data Server (Port 8001):**
3. `get_tests_history` ✨ **Enhanced** - Filtered and paginated test execution history with advanced filtering options (test type, time windows, status, name patterns) and customizable ordering
4. `get_test_details` ✨ **Enhanced** - Full details for specific tests with optional simulation statistics including drift counts
5. `get_test_simulations` ✨ **Enhanced** - Filtered and paginated simulations within a test with status, time window, playbook attack filtering, and drift analysis filtering
6. `get_simulation_details` ✨ **Enhanced** - Detailed simulation results with optional MITRE techniques, attack logs, and drift analysis information
7. `get_security_controls_events` - Security control events with filtering
8. `get_security_control_event_details` - Detailed security event with verbosity levels
9. `get_test_findings_counts` - Findings summary by type with filtering
10. `get_test_findings_details` - Detailed findings with comprehensive filtering
11. `get_test_drifts` ✨ **NEW** - Advanced drift analysis between test runs with comprehensive drift type classification and security impact assessment

**Playbook Server (Port 8003):**
12. `get_playbook_attacks` ✨ **NEW** - Filtered and paginated playbook attacks from SafeBreach attack knowledge base with comprehensive filtering (name, description, ID range, date ranges) and pagination
13. `get_playbook_attack_details` ✨ **NEW** - Detailed attack information with verbosity options (fix suggestions, tags, parameters) for specific attack techniques

**Utilities Server (Port 8002):**
14. `convert_datetime_to_epoch` - Convert ISO datetime strings to Unix epoch timestamps for API filtering
15. `convert_epoch_to_datetime` - Convert Unix epoch timestamps to readable datetime strings


## Filtering and Search Capabilities

The `get_console_simulators`, `get_tests_history`, and `get_test_simulations` functions now support comprehensive filtering:

**Enhanced Simulator Filtering (`get_console_simulators`):**
- **Status**: Filter by "connected", "disconnected", "enabled", "disabled"
- **Name Patterns**: Case-insensitive partial matching on simulator names
- **Label Filtering**: Case-insensitive partial matching on simulator labels
- **OS Type**: Filter by operating system type (e.g., "Linux", "Windows")
- **Criticality**: Filter for critical simulators only (True/False)
- **Custom Ordering**: Sort by name, id, version, isConnected, isEnabled (ascending/descending)

**Enhanced Test History Filtering (`get_tests_history`):**
- **Test Type**: Filter by "validate" (BAS tests) or "propagate" (ALM tests)
- **Time Windows**: Filter by start/end dates (Unix timestamps)
- **Status**: Filter by "completed", "canceled", "failed"
- **Name Patterns**: Case-insensitive partial matching on test names
- **Custom Ordering**: Sort by end_time, start_time, name, or duration (ascending/descending)

**Enhanced Test Details (`get_test_details`):**
- **Basic Details**: Returns standard test information (name, ID, start/end times, duration, status)
- **Optional Simulation Statistics**: Set `include_simulations_statistics=True` to get detailed breakdown of simulation results by status (missed, stopped, prevented, reported, logged, no-result) and drift counts
- **Drift Analysis**: Statistics include count of simulations that completed with different results compared to previous executions with identical parameters
- **Backward Compatibility**: Statistics are not included by default to maintain existing behavior

**Enhanced Simulation Filtering (`get_test_simulations`):**
- **Status**: Filter by simulation status ("missed", "stopped", "prevented", "reported", "logged", "no-result")
- **Time Windows**: Filter by start/end times (Unix timestamps) with safe type conversion for end_time field
- **Playbook Attack ID**: Filter by exact playbook attack ID match
- **Playbook Attack Name**: Case-insensitive partial matching on playbook attack names (e.g., "file", "network", "credential")
- **Drift Analysis**: Set `drifted_only=True` to filter only simulations that have drifted from previous results with identical parameters

**Enhanced Simulation Details (`get_simulation_details`):**
- **Basic Details**: Returns standard simulation information
- **Optional MITRE Techniques**: Set `include_mitre_techniques=True` to get MITRE ATT&CK technique details
- **Optional Attack Logs**: Set `include_full_attack_logs=True` to get detailed attack logs by host
- **Optional Drift Analysis**: Set `include_drift_info=True` to get comprehensive drift analysis information including drift type, security impact, description, and tracking code for correlation
- **Robust Error Handling**: Improved handling of different data structure formats

All filters work in combination and include pagination support. The response includes metadata about applied filters and total result counts.

## Drift Analysis Functionality

The SafeBreach MCP Data Server includes comprehensive drift analysis capabilities to help identify changes in security posture between test executions.

### Understanding Drift

**Drift Definition**: A drift occurs when two simulations with identical parameters (same attack ID, attacker host, target host, protocol, etc.) produce different final results. Simulations with identical parameters share the same `drift_tracking_code` for correlation.

**Common Causes**: 
- Heuristic behavior of security controls
- Timing issues and varying host loads
- Environmental changes (e.g., user logged into target host)
- Security control configuration modifications

### Drift Types and Security Impact

The system recognizes various drift types with their security implications:

**Positive Security Impact Drifts:**
- `success-fail`: Attack was blocked in later execution (security improvement)
- `stopped-prevented`: Better security control reporting (stopped → prevented)
- `logged-detected`: Enhanced detection capabilities (logged → detected)
- `missed-logged`: Improved logging coverage (missed → logged)

**Negative Security Impact Drifts:**
- `fail-success`: Attack succeeded in later execution (security degradation)
- `prevented-stopped`: Reduced security control effectiveness (prevented → stopped)
- `detected-logged`: Reduced detection capabilities (detected → logged)
- `logged-missed`: Loss of logging coverage (logged → missed)

**Neutral Impact Drifts:**
- `result_improvement`: Technical failure resolved in later execution
- `fail-internal_fail`: Internal failures in both executions
- `success-internal_fail`: Technical failure in later execution

### Using Drift Analysis

**Filter Drifted Simulations:**
```bash
# Get only simulations that have drifted from previous results
get_test_simulations(console="demo", test_id="123", drifted_only=True)
```

**Get Detailed Drift Information:**
```bash
# Include comprehensive drift analysis in simulation details
get_simulation_details(
    console="demo", 
    test_id="123", 
    simulation_id="sim456",
    include_drift_info=True
)
```

**Track Drift Statistics:**
```bash
# Include drift counts in test statistics
get_test_details(console="demo", test_id="123", include_simulations_statistics=True)
```

### Drift Information Structure

When `include_drift_info=True`, the response includes:
- `type_of_drift`: Classification of the drift pattern
- `security_impact`: "positive", "negative", or "neutral"
- `description`: Human-readable explanation of the drift
- `hint_to_llm`: Guidance for further investigation
- `drift_tracking_code`: Correlation ID to find related simulations
- `last_drift_date`: When the most recent drift occurred (if available)

### Comprehensive Test Drift Analysis

The `get_test_drifts` tool provides advanced drift analysis between two test runs, comparing a current test with the most recent previous test that has the same name.

**Usage:**
```bash
# Analyze drift between current test and previous test with same name
get_test_drifts(console="demo", test_id="current-test-123")
```

**Enhanced Response Structure:**
```json
{
  "total_drifts": 15,  // Total count of all drift types found
  
  "drifts": {
    // Grouped by drift type for organized analysis
    "missed-reported": {
      "drift_type": "missed-reported",
      "security_impact": "negative", 
      "description": "Attack missed in baseline but reported in current test - potential security degradation",
      "drifted_simulations": [
        {
          "drift_tracking_code": "attack_123_hostA_hostB",
          "former_simulation_id": "baseline_sim_001",
          "current_simulation_id": "current_sim_001"
        }
        // ... more simulations with this drift pattern
      ]
    },
    "prevented-stopped": {
      "drift_type": "prevented-stopped", 
      "security_impact": "positive",
      "description": "Attack prevented in baseline but stopped in current - improved blocking",
      "drifted_simulations": [ /* ... */ ]
    }
    // ... additional drift types found
  },
  
  "_metadata": {
    "console": "demo",
    "current_test_id": "current-test-123",
    "baseline_test_id": "baseline-test-456", 
    "test_name": "Weekly Security Assessment",
    "baseline_simulations_count": 150,
    "current_simulations_count": 148,
    "shared_drift_codes": 145,
    "simulations_exclusive_to_baseline": ["baseline_sim_099"],  // Only in baseline
    "simulations_exclusive_to_current": ["current_sim_147", "current_sim_148"],  // Only in current 
    "status_drifts": 12,  // Count of simulations with status changes
    "analyzed_at": 1703891234.56
  }
}
```

**Key Features:**
- **Automatic Baseline Detection**: Finds the most recent previous test with the same name
- **Three-Category Analysis**: Identifies simulations exclusive to baseline, exclusive to current, and shared with status changes
- **Drift Type Classification**: Groups similar drift patterns using the comprehensive `drift_types_mapping`
- **Security Impact Assessment**: Categorizes each drift type as positive, negative, or neutral security impact
- **Comprehensive Metadata**: Provides complete context about the analysis including simulation counts and exclusions
- **Organized Output**: Groups drifts by type for efficient analysis and reporting

**Error Handling:**
The tool provides detailed error messages for common scenarios:
- No previous test found with the same name
- Test details unavailable or missing required attributes  
- API connectivity issues during simulation retrieval

## External Connection Support

The SafeBreach MCP servers support optional external connections with HTTP Authorization security. By default, all servers bind to localhost (127.0.0.1) for maximum security.

### Security Model
- **Default**: Localhost-only binding (127.0.0.1) - no external access
- **External Access**: Optional with Bearer token authentication required
- **Authentication**: HTTP Authorization header for external connections
- **Localhost Bypass**: Local connections skip authentication automatically

### Configuration Environment Variables
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

### Command-Line Arguments
```bash
# Enable external connections for all servers
SAFEBREACH_MCP_AUTH_TOKEN="token" uv run start_all_servers.py --external

# Enable external connections for specific servers
SAFEBREACH_MCP_AUTH_TOKEN="token" uv run start_all_servers.py --external-data --external-utilities

# Custom bind host with external access
SAFEBREACH_MCP_AUTH_TOKEN="token" uv run start_all_servers.py --external --host 0.0.0.0

# Get comprehensive help
uv run start_all_servers.py --help
```

### Security Warnings
When external connections are enabled, servers log security warnings:
```
🚨 SECURITY WARNING: Server binding to 0.0.0.0:8001 - accessible from external networks!
🔒 HTTP Authorization required for external connections
🌐 External connections enabled for: Data Server, Utilities Server
🏠 Local connections only for: Config Server
✅ SAFEBREACH_MCP_AUTH_TOKEN configured
```

## Environment Setup

- Python 3.12+ required
- `uv` package manager for dependency management
- AWS credentials configured for SSM Parameter Store access
- OpenAI API key for running examples
- SafeBreach API tokens stored in AWS SSM Parameter Store (or Secrets Manager)
- SSH key configured with GitHub (for remote installation)

## Secret Configuration

Each SafeBreach environment in `environments_metadata.py` now includes a `secret_config` section:

```python
"demo": {
    "url": "demo.safebreach.com", 
    "account": "6311226704",
    "secret_config": {
        "provider": "env_var",                    # Provider type
        "parameter_name": "mcp-demo-apitoken"  # Secret location
    }
}
```

**Supported Providers:**
- `env_var`: Environment Variables (default)
- `aws_ssm`: AWS Systems Manager Parameter Store 
- `aws_secrets_manager`: AWS Secrets Manager

**Adding New Environments:**
```python
"new-environment": {
    "url": "new-env.safebreach.com",
    "account": "1234567890",
    "secret_config": {
        "provider": "aws_secrets_manager",
        "parameter_name": "safebreach/new-environment/api-token",
        "region_name": "us-west-2"  # Optional, defaults to us-east-1
    }
}

# Environment Variable Provider Example
"test-console": {
    "url": "test-console.safebreach.com",
    "account": "1234567890",
    "secret_config": {
        "provider": "env_var",
        "parameter_name": "test-console-apitoken"  # Will look for TEST_CONSOLE_APITOKEN env var
    }
}
```

**Backward Compatibility:** If `secret_config` is not specified, the system defaults to AWS SSM with the pattern `{console-name}-apitoken`.

## Dynamic Environment Loading

The MCP server supports loading additional SafeBreach environments from a JSON file at runtime. This allows you to add more consoles without modifying the codebase.

**Usage:**
```bash
# Set the environment variable to point to your JSON file
export SAFEBREACH_ENVS_FILE=/path/to/more_envs.json

# Start the server - it will automatically load environments from the JSON file
uv run start_all_servers.py
```

**JSON File Format (`more_envs.json`):**
```json
{
    "example-console": {
        "url": "example-console.safebreach.com",
        "account": "1234567890",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "example-console-apitoken"
        }
    },
    "my-custom-console": {
        "url": "my-console.safebreach.com",
        "account": "1234567890",
        "secret_config": {
            "provider": "aws_ssm",
            "parameter_name": "my-custom-console-token"
        }
    }
}
```

**Environment Variable Naming:**
When using the `env_var` provider, dashes in the `parameter_name` are converted to underscores but **remain lowercase**:
- `example-console-apitoken` → looks for `example_console_apitoken` environment variable

**⚠️ Important**: Environment API KEY variables must be lowercase with underscores, not uppercase!

**Setting Environment Variables:**
```bash
# For the example above (note lowercase)
export example_console_apitoken="your-api-token-here"
export console1_apitoken="another-api-token"
```

## Installation Options

**Local Development:**
```bash
git clone git@github.com:SafeBreach/safebreach-mcp.git
uv sync
```

**Remote Installation (SSH):**
```bash
uv tool install git+ssh://git@github.com/SafeBreach/safebreach-mcp.git/
```

**Remote Installation (HTTPS with App Password):**
```bash
uv tool install git+https://username:personal-access-token@github.com/SafeBreach/safebreach-mcp.git
```

## Package Information

The project provides multiple installation options with various entry points:

**Multi-Server Entry Points:**
- **`safebreach-mcp-all-servers`**: Concurrent multi-server launcher (recommended)
- **`safebreach-mcp-config-server`**: Config server only (Port 8000)
- **`safebreach-mcp-data-server`**: Data server only (Port 8001)
- **`safebreach-mcp-utilities-server`**: Utilities server only (Port 8002)


**Package Configuration:**
- **Package Name**: safebreach-mcp-server
- **Version**: 1.1.0
- **Dependencies**: boto3, requests, mcp (see pyproject.toml)
- **Installation**: Via git+ssh or git+https with subdirectory specification

## Claude Desktop Integration

Register the servers in Claude Desktop config at `/Library/Application Support/Claude/claude_desktop_config.json`:

**Multi-Server Configuration (Localhost - Recommended):**
```json
{
  "mcpServers": {
    "safebreach-config": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://127.0.0.1:8000/sse",
        "--transport",
        "http-first"
      ]
    },
    "safebreach-data": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://127.0.0.1:8001/sse",
        "--transport",
        "http-first"
      ]
    },
    "safebreach-utilities": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://127.0.0.1:8002/sse",
        "--transport",
        "http-first"
      ]
    },
    "safebreach-playbook": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://127.0.0.1:8003/sse",
        "--transport",
        "http-first"
      ]
    }
  }
}
```

**External Server Configuration (With Authentication):**
```json
{
  "mcpServers": {
    "safebreach-config-external": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://your-server-ip:8000/sse",
        "--transport",
        "http-first",
        "--headers",
        "{\"Authorization\": \"Bearer your-secure-token\"}"
      ]
    },
    "safebreach-data-external": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://your-server-ip:8001/sse",
        "--transport",
        "http-first",
        "--headers",
        "{\"Authorization\": \"Bearer your-secure-token\"}"
      ]
    },
    "safebreach-playbook-external": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://your-server-ip:8003/sse",
        "--transport",
        "http-first",
        "--headers",
        "{\"Authorization\": \"Bearer your-secure-token\"}"
      ]
    }
  }
}
```


### Validation Status

**Functional Testing Results:**
- ✅ **Config Server**: 5+ simulators accessible across multiple consoles
- ✅ **Data Server**: 60+ tests available from SafeBreach environments
- ✅ **Utilities Server**: Datetime conversion functions operational
- ✅ **API Integration**: All SafeBreach console APIs working correctly
- ✅ **Claude Desktop**: Remote MCP integration confirmed working

### External Connection Support Status

**✅ FULLY OPERATIONAL**: 
- External connections now working after MCP SDK upgrade and code updates
- **Servers bind to**: `0.0.0.0:8000`, `0.0.0.0:8001`, `0.0.0.0:8002` (all interfaces)
- **Authentication**: Bearer token authentication working correctly
- **Access**: Direct external network access with proper authentication

**Fixed Issues**:
- ✅ Resolved `'function' object has no attribute 'middleware'` error
- ✅ Updated MCP SDK from 1.11.0 to 1.12.1
- ✅ Deployed latest authentication wrapper code
- ✅ Configured proper external binding environment variables

**Current Access Methods**:
1. **External Access**: `curl -H "Authorization: Bearer token" http://10.10.10.10:8001/sse`
2. **Local Access**: `curl http://localhost:8001/sse` (no auth required for localhost)
3. **Claude Desktop**: Full external MCP integration with Bearer token authentication

### Deployment Troubleshooting

**Environment Variable Issues**:
```bash
# ✅ Correct casing for API tokens (lowercase with underscores)
console1_apitoken=token-value

# ✅ Correct casing for MCP variables (UPPERCASE)
SAFEBREACH_ENVS_FILE=/path/to/file
SAFEBREACH_MCP_AUTH_TOKEN=token-value

# ❌ Wrong casing (will cause failures)
safebreach_envs_file=/path/to/file   # Wrong - too low case

