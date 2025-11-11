# Enhanced Filtering Design for SafeBreach MCP Multi-Server Architecture

> **Status: IMPLEMENTED** - This design document was used to implement the enhanced filtering capabilities in the multi-server architecture. All features described below are now fully implemented and tested.

## Implementation Analysis

The `get_tests_history` function in the Data Server now includes:
- ✅ Sorts by `end_time` in descending order (configurable)
- ✅ Has caching mechanism (1-hour TTL)
- ✅ Supports pagination
- ✅ **NEW:** Comprehensive filtering capabilities
- ✅ **NEW:** Custom ordering options
- ✅ **NEW:** Cache strategy optimized for filtering

## Implementation Details

### Function Signature (Data Server)
```python
def sb_get_tests_history( 
    page_number: int = 0,
    console: Optional[str] = "default",
    test_type: Optional[str] = None,           # "validate", "propagate", or None (all)
    start_date: Optional[int] = None,          # Unix timestamp
    end_date: Optional[int] = None,            # Unix timestamp
    status_filter: Optional[str] = None,       # "completed", "canceled", "failed", or None (all)
    name_filter: Optional[str] = None,         # Partial match on test name
    order_by: str = "end_time",                 # "end_time", "start_time", "name", "duration"
    order_direction: str = "desc"              # "desc" or "asc"
) -> dict:
```

### Filtering Logic

1. **Test Type Filtering:**
   - `"validate"` → Tests without "ALM" in systemTags (BAS tests)
   - `"propagate"` → Tests with "ALM" in systemTags (ALM tests)
   - `None` → All tests

2. **Time Window Filtering:**
   - `start_date` → Tests with end_time >= start_date
   - `end_date` → Tests with end_time <= end_date
   - Both support Unix timestamps for precision

3. **Status Filtering:**
   - Filter by test execution status
   - Common values: "completed", "canceled", "failed"

4. **Name Filtering:**
   - Case-insensitive partial match on test name
   - Useful for finding specific test campaigns

5. **Ordering Options:**
   - Multiple fields: end_time (default), start_time, name, duration
   - Ascending/descending support

### Cache Strategy

Current cache stores all tests without filter consideration. New approach:

1. **Base Cache:** Store all raw test data (unfiltered)
2. **Filter Application:** Apply filters to cached data when retrieving
3. **Cache Key:** Include console name only (filters applied post-cache)
4. **Benefits:** 
   - Single API call per console per hour
   - All filter combinations work from cache
   - Maintains performance while adding flexibility

### Backward Compatibility

- All new parameters are optional with sensible defaults
- Default behavior matches current implementation
- Existing callers continue to work unchanged

### Return Value Enhancement

```python
{
    "page_number": 0,
    "total_pages": 5,
    "total_tests": 47,                    # NEW: Total tests matching filter
    "tests_in_page": [...],
    "applied_filters": {                  # NEW: Shows what filters were applied
        "test_type": "validate",
        "start_date": 1640995200,
        "status_filter": "completed"
    }
}
```

## Implementation Status

✅ **Completed in Multi-Server Architecture:**
- **Phase 1:** Function signature updated with all filtering parameters in Data Server
- **Phase 2:** Comprehensive filtering logic implemented with helper functions
- **Phase 3:** Cache strategy updated to support filtering in Data Server
- **Phase 4:** MCP tool definition updated in Data Server
- **Phase 5:** Comprehensive test suite added (unit, integration, e2e)
- **Phase 6:** Documentation updated for multi-server architecture

## Example Usage

```python
# Current usage (unchanged)
tests = sb_get_tests_history("sample-console", 0)

# Filter for validation tests from last week
tests = sb_get_tests_history(
    console="sample-console",
    page_number=0,
    test_type="validate",
    start_date=int(time.time()) - (7 * 24 * 3600)  # Last 7 days
)

# Filter for failed propagate tests, ordered by name
tests = sb_get_tests_history(
    console="sample-console",
    test_type="propagate",
    status_filter="failed",
    order_by="name",
    order_direction="asc"
)

# Search for specific test campaign
tests = sb_get_tests_history(
    console="sample-console", 
    name_filter="quarterly"
)
```

---

# Enhanced get_test_simulations Design (Data Server)

## Implementation Analysis

The `get_test_simulations` function in the Data Server now includes:
- ✅ Pagination support
- ✅ Caching mechanism (1-hour TTL per test)
- ✅ Returns structured simulation data  
- ✅ **NEW:** Comprehensive filtering capabilities
- ✅ **NEW:** Safe type conversion for API inconsistencies
- ✅ **NEW:** Cache strategy optimized for filtering

## Implementation Details

### Function Signature (Data Server)
```python
def sb_get_test_simulations(
    test_id: str, 
    page_number: int = 0,
    console: Optional[str] = "default",
    status_filter: Optional[str] = None,           # Filter by simulation status
    start_time: Optional[int] = None,              # Filter simulations with end_time >= start_time
    end_time: Optional[int] = None,                # Filter simulations with end_time <= end_time
    playbook_attack_id_filter: Optional[str] = None,  # Filter by exact playbook attack ID
    playbook_attack_name_filter: Optional[str] = None  # Filter by partial playbook attack name
) -> dict:
```

### Filtering Logic

1. **Status Filtering:**
   - Filter by simulation execution status
   - Common values: "missed", "stopped", "prevented", "reported", "logged", "no-result"
   - Case-insensitive exact match

2. **Time Window Filtering:**
   - `start_time` → Simulations with end_time >= start_time
   - `end_time` → Simulations with end_time <= end_time
   - Unix timestamps for precision
   - **Note:** end_time field may come as string from API, requiring safe type conversion

3. **Playbook Attack ID Filtering:**
   - Exact match on playbook attack ID
   - Useful for finding specific attack techniques

4. **Playbook Attack Name Filtering:**
   - Case-insensitive partial match on playbook attack name
   - Useful for finding attacks by category (e.g., "file", "network", "credential")

### Cache Strategy

Similar to tests history approach:

1. **Base Cache:** Store all raw simulation data per test (unfiltered)
2. **Filter Application:** Apply filters to cached data when retrieving
3. **Cache Key:** Include console + test_id
4. **Benefits:** 
   - Single API call per test per hour
   - All filter combinations work from cache
   - Maintains performance while adding flexibility

### Data Type Handling

**Critical Issue:** The `end_time` field may come as string from the SafeBreach API instead of integer. The filtering logic includes safe type conversion:

```python
def safe_time_compare(s, compare_time, operator):
    end_time_val = s.get('end_time', 0)
    if isinstance(end_time_val, str):
        try:
            end_time_val = int(end_time_val)
        except (ValueError, TypeError):
            end_time_val = 0
    return operator(end_time_val, compare_time)
```

### Backward Compatibility

- All new parameters are optional with sensible defaults
- Default behavior matches current implementation
- Existing callers continue to work unchanged

### Return Value Enhancement

```python
{
    "page_number": 0,
    "total_pages": 3,
    "total_simulations": 28,              # Total simulations matching filter
    "simulations_in_page": [...],
    "applied_filters": {                  # Shows what filters were applied
        "status_filter": "missed",
        "start_time": 1640995200,
        "playbook_attack_name_filter": "file"
    },
    "hint_to_agent": "You can scan next page..."
}
```

## Implementation Status

✅ **Completed in Data Server:**
- Function signature updated with all 5 filtering parameters
- Helper functions implemented (`_get_all_simulations_from_cache_or_api`, `_apply_simulation_filters`)
- Safe type conversion for end_time field
- MCP Data Server tool definition updated
- Comprehensive E2E tests added
- Documentation updated for multi-server architecture

## Additional Enhancements Beyond Original Design

Beyond the filtering capabilities described in this design document, the following additional enhancements were implemented:

### Enhanced get_console_simulators (Config Server)
- **Status Filtering**: "connected", "disconnected", "enabled", "disabled"
- **Name/Label Filtering**: Case-insensitive partial matching
- **OS Type Filtering**: Filter by operating system type
- **Criticality Filtering**: Filter for critical simulators only
- **Custom Ordering**: Sort by name, id, version, connection/enable status
- **Simulator Caching**: 1-hour TTL per console with intelligent cache management

### Enhanced get_test_details (Data Server)
- **Optional Simulation Statistics**: Include detailed breakdown of simulation results by status
- **Backward Compatibility**: Statistics not included by default
- **Comprehensive Status Breakdown**: missed, stopped, prevented, reported, logged, no-result

### Enhanced get_simulation_details (Data Server)
- **Optional MITRE Techniques**: Include MITRE ATT&CK technique details
- **Optional Attack Logs**: Include detailed attack logs by host
- **Robust Error Handling**: Improved handling for different API response formats
- **Safe Type Conversion**: Handle both dict and list data structures

### Utility Tools (Utilities Server)
- **convert_datetime_to_epoch**: Convert ISO datetime strings to Unix timestamps
- **convert_epoch_to_datetime**: Convert Unix timestamps to readable datetime strings
- **Timezone Support**: Handle various timezone formats and conversions

## Example Usage

```python
# Current usage (unchanged)
simulations = sb_get_test_simulations("sample-console", "test-123", 0)

# Filter for missed simulations (successful attacks)
missed = sb_get_test_simulations(
    console="sample-console",
    test_id="test-123",
    page_number=0,
    status_filter="missed"
)

# Filter for file-related attacks from last 24 hours
day_ago = int(time.time()) - (24 * 3600)
file_attacks = sb_get_test_simulations(
    console="sample-console",
    test_id="test-123",
    page_number=0,
    start_time=day_ago,
    playbook_attack_name_filter="file"
)

# Filter for specific attack technique
specific_attack = sb_get_test_simulations(
    console="sample-console",
    test_id="test-123",
    page_number=0,
    playbook_attack_id_filter="ATT-1234"
)

# Combined filters: missed credential attacks from last week
week_ago = int(time.time()) - (7 * 24 * 3600)
results = sb_get_test_simulations(
    console="sample-console",
    test_id="test-123",
    page_number=0,
    status_filter="missed",
    start_time=week_ago,
    playbook_attack_name_filter="credential"
)
```

---

# Secret Management and Dynamic Environment Loading Enhancements

> **Status: IMPLEMENTED** - These features have been implemented and tested across all servers.

## Secret Provider System

The MCP multi-server architecture now supports three different secret providers through a pluggable architecture shared across all servers:

### Supported Providers

1. **AWS SSM Parameter Store (`aws_ssm`)** - Default provider
   - Stores secrets as SecureString parameters
   - Automatic decryption
   - Regional support

2. **AWS Secrets Manager (`aws_secrets_manager`)**
   - Full secret management features
   - Automatic rotation support
   - Regional support

3. **Environment Variables (`env_var`)** - New provider
   - Reads secrets from environment variables
   - Automatic dash-to-underscore conversion
   - No external dependencies

### Environment Variable Provider Design

The `env_var` provider includes several key features:

**Automatic Name Conversion:**
- Parameter names with dashes are converted to lowercase with underscores for environment variable lookup
- Example: `pentest-ewe-2181-apitoken` → looks for `pentest_ewe_2181_apitoken`

**Caching:**
- Local caching to avoid repeated environment variable lookups
- Same caching pattern as other providers

**Error Handling:**
- Proper validation for missing environment variables
- Validation for empty environment variables
- Comprehensive logging for debugging

**Implementation:**
```python
class EnvVarSecretProvider(SecretProvider):
    def get_secret(self, env_var_name: str) -> str:
        # Convert dashes to underscores for env var lookup (keeps lowercase)
        value = os.getenv(env_var_name.replace('-', '_'))
        
        if value is None:
            raise ValueError(f"Environment variable '{env_var_name}' not found")
        
        if not value.strip():
            raise ValueError(f"Environment variable '{env_var_name}' is empty")
        
        return value
```

**⚠️ Important Environment Variable Naming:**
- Parameter names with dashes (e.g., `mcp-demo-apitoken`) are converted to underscores but **remain lowercase**
- The environment variable must be `mcp_demo_apitoken` (lowercase with underscores)
- **NOT** `MCP_DEMO_APITOKEN` (uppercase) - this will not work
- This behavior is implemented in `secret_providers.py` line 170: `os.getenv(env_var_name.replace('-', '_'))`
```

## Dynamic Environment Loading

The system supports loading additional SafeBreach environments dynamically at runtime using two methods:

### Implementation

**Method 1: JSON File (SAFEBREACH_ENVS_FILE)**
```python
if os.environ.get('SAFEBREACH_ENVS_FILE'):
    with open(os.environ['SAFEBREACH_ENVS_FILE']) as f:
        safebreach_envs.update(json.load(f))
```

**Method 2: JSON String (SAFEBREACH_LOCAL_ENV) ✨ NEW**
```python
if os.environ.get('SAFEBREACH_LOCAL_ENV'):
    try:
        local_envs = json.loads(os.environ['SAFEBREACH_LOCAL_ENV'])
        safebreach_envs.update(local_envs)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in SAFEBREACH_LOCAL_ENV environment variable: {e}")
```

**Loading Priority:**
1. Hardcoded environments in `environments_metadata.py` (base)
2. `SAFEBREACH_ENVS_FILE` extends the base
3. `SAFEBREACH_LOCAL_ENV` extends and overrides all previous

**JSON File Format:**
```json
{
    "console-name": {
        "url": "console.safebreach.com",
        "account": "account_id",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "console-name-apitoken"
        }
    }
}
```

### Benefits

1. **No Code Changes**: Add new environments without modifying `environments_metadata.py`
2. **Flexible Deployment**: Different JSON files for different environments (dev, staging, prod)
3. **No File Dependencies**: `SAFEBREACH_LOCAL_ENV` eliminates need for file system access
4. **Container-Friendly**: JSON string method perfect for Docker and Kubernetes deployments
5. **Secret Provider Choice**: Can use any of the three providers per environment
6. **Runtime Configuration**: Environments loaded when server starts
7. **Override Capability**: Local environments can override file-based configurations

### Usage Examples

**Basic Setup:**
```bash
# Create environment file
cat > /path/to/my_envs.json << 'EOF'
{
    "my-console": {
        "url": "my-console.safebreach.com",
        "account": "1234567890",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "my-console-token"
        }
    }
}
EOF

# Set environment variables
export SAFEBREACH_ENVS_FILE=/path/to/my_envs.json
export MY_CONSOLE_TOKEN="your-api-token-here"

# Start server - will load custom environments
uv run start_all_servers.py
```

**JSON String Setup (Container-Friendly):**
```bash
# Set configuration directly as JSON string
export SAFEBREACH_LOCAL_ENV='{"my-console": {"url": "my-console.safebreach.com", "account": "1234567890", "secret_config": {"provider": "env_var", "parameter_name": "my_console_token"}}}'

# Set API token
export my_console_token="your-api-token-here"

# Start server - will load environments from JSON string
uv run start_all_servers.py
```

**Combined Usage (File + Override):**
```bash
# Load base environments from file
export SAFEBREACH_ENVS_FILE=/etc/safebreach/base_envs.json

# Override specific environments via JSON string
export SAFEBREACH_LOCAL_ENV='{"dev-console": {"url": "dev-override.safebreach.com", "account": "9999999999", "secret_config": {"provider": "env_var", "parameter_name": "dev_console_token"}}}'

# Set tokens
export dev_console_token="dev-token-override"

# Start server - dev-console will use override configuration
uv run start_all_servers.py
```

**Mixed Provider Setup:**
```json
{
    "dev-console": {
        "url": "dev.safebreach.com",
        "account": "1111111111",
        "secret_config": {
            "provider": "env_var",
            "parameter_name": "dev-console-token"
        }
    },
    "prod-console": {
        "url": "prod.safebreach.com",
        "account": "2222222222",
        "secret_config": {
            "provider": "aws_ssm",
            "parameter_name": "prod-console-secure-token"
        }
    }
}
```

## Factory Pattern Implementation

The secret provider system uses a factory pattern for extensibility:

```python
class SecretProviderFactory:
    _providers = {
        'aws_ssm': AWSSSMSecretProvider,
        'aws_secrets_manager': AWSSecretsManagerProvider,
        'env_var': EnvVarSecretProvider,
    }
    
    @classmethod
    def create_provider(cls, provider_type: str, **kwargs) -> SecretProvider:
        if provider_type not in cls._providers:
            raise ValueError(f"Unsupported provider type: {provider_type}")
        
        provider_class = cls._providers[provider_type]
        return provider_class(**kwargs)
```

This design makes it easy to add new secret providers in the future (e.g., HashiCorp Vault, Kubernetes secrets, etc.) by implementing the `SecretProvider` interface and registering the provider in the factory.

---

# External Connection Support Architecture

> **Status: IMPLEMENTED** - This section documents the external connection support architecture implemented across all SafeBreach MCP servers.

## Overview

The SafeBreach MCP multi-server architecture now supports optional external connections while maintaining secure localhost-only defaults. This enhancement enables deployment scenarios requiring remote access while preserving security through HTTP Authorization authentication.

## Security-First Design Principles

### Default Security Posture
- **Localhost-Only Default**: All servers bind to `127.0.0.1` by default - no external access possible
- **Explicit Opt-In**: External connections require explicit configuration through environment variables or command-line arguments
- **No Accidental Exposure**: Impossible to accidentally expose servers externally without deliberate configuration

### Authentication Model
- **Bearer Token Authentication**: HTTP Authorization header with Bearer token required for external connections
- **Localhost Bypass**: Local connections (127.0.0.1, ::1, localhost) automatically bypass authentication
- **Token Validation**: Comprehensive token validation with proper error responses for unauthorized requests
- **Security Warnings**: Extensive logging when external access is enabled

## Architecture Components

### Core Infrastructure (`safebreach_mcp_core/safebreach_base.py`)

The base class `SafeBreachMCPBase` provides external connection support to all servers:

**Key Methods:**
```python
async def run_server(self, port: int = 8000, host: str = "127.0.0.1", allow_external: bool = False) -> None:
    # Determine bind address based on configuration
    bind_host = self._determine_bind_host(host, allow_external)
    
    # Add authentication middleware for external connections
    if allow_external:
        self._add_authentication_middleware()
        self._log_external_binding_warning(port)
```

**Authentication Middleware:**
```python
def _add_authentication_middleware(self) -> None:
    # FastAPI middleware for HTTP Authorization validation
    @self.mcp.sse_app.middleware("http")
    async def authenticate_external_request(request, call_next):
        # Skip authentication for localhost connections
        client_host = request.client.host if request.client else "unknown"
        if client_host in ["127.0.0.1", "::1", "localhost"]:
            return await call_next(request)
        
        # Require Authorization header for external connections
        auth_header = request.headers.get("Authorization")
        expected_auth = f"Bearer {auth_token}"
        
        if not auth_header or auth_header != expected_auth:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})
```

**Conditional FastAPI Imports:**
```python
try:
    from fastapi import Request
    from fastapi.responses import JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
```

This design prevents breaking existing installations that don't have FastAPI installed while enabling external connection features when needed.

### Individual Server Enhancements

All three specialized servers implement external configuration parsing:

**Configuration Pattern:**
```python
def parse_external_config(server_type: str) -> bool:
    # Check global flag first
    global_external = os.environ.get('SAFEBREACH_MCP_ALLOW_EXTERNAL', 'false').lower() == 'true'
    
    # Check server-specific flag
    server_specific = os.environ.get(f'SAFEBREACH_MCP_{server_type.upper()}_EXTERNAL', 'false').lower() == 'true'
    
    return global_external or server_specific

async def main():
    # Parse external configuration
    allow_external = parse_external_config("config")  # or "data", "utilities"
    custom_host = os.environ.get('SAFEBREACH_MCP_BIND_HOST', '127.0.0.1')
    
    # Start server with appropriate configuration
    await config_server.run_server(port=8000, host=custom_host, allow_external=allow_external)
```

**Servers Enhanced:**
- **Config Server** (`safebreach_mcp_config/config_server.py`) - Port 8000
- **Data Server** (`safebreach_mcp_data/data_server.py`) - Port 8001
- **Utilities Server** (`safebreach_mcp_utilities/utilities_server.py`) - Port 8002

### Multi-Server Launcher Enhancement (`start_all_servers.py`)

The multi-server launcher provides comprehensive external connection support:

**Command-Line Interface:**
```bash
# Global external access
--external                    # Enable external connections for all servers
--external-config            # Enable external connections for Config server only
--external-data              # Enable external connections for Data server only
--external-utilities         # Enable external connections for Utilities server only
--host HOST                  # Custom bind host (default: 127.0.0.1)
```

**Configuration Precedence:**
1. Command-line arguments (highest priority)
2. Environment variables
3. Secure defaults (localhost-only)

**Enhanced Launcher Features:**
```python
class MultiServerLauncher:
    def _determine_external_config(self) -> dict:
        # Merge environment variables with command-line arguments
        # Command-line arguments take precedence
    
    def _log_connection_summary(self, server_configs):
        # Log which servers have external access enabled
        # Validate authentication token configuration
        # Provide security warnings and status updates
```

## Configuration System

### Environment Variables

**Global Configuration:**
```bash
SAFEBREACH_MCP_ALLOW_EXTERNAL=true          # Enable external access for all servers
SAFEBREACH_MCP_AUTH_TOKEN="your-token"      # Authentication token for external connections
SAFEBREACH_MCP_BIND_HOST=0.0.0.0            # Custom bind host (default: 127.0.0.1)
```

**Server-Specific Configuration:**
```bash
SAFEBREACH_MCP_CONFIG_EXTERNAL=true         # Config server external access
SAFEBREACH_MCP_DATA_EXTERNAL=true           # Data server external access
SAFEBREACH_MCP_UTILITIES_EXTERNAL=true      # Utilities server external access
```

### Command-Line Arguments

**Multi-Server Launcher:**
```bash
# Enable external connections for all servers
SAFEBREACH_MCP_AUTH_TOKEN="token" uv run start_all_servers.py --external

# Enable external connections for specific servers
SAFEBREACH_MCP_AUTH_TOKEN="token" uv run start_all_servers.py --external-data --external-utilities

# Custom bind host
SAFEBREACH_MCP_AUTH_TOKEN="token" uv run start_all_servers.py --external --host 0.0.0.0
```

## Security Implementation Details

### Authentication Flow

1. **Request Receives**: HTTP request arrives at server
2. **Client IP Check**: Extract client IP address from request
3. **Localhost Bypass**: If client IP is localhost (127.0.0.1, ::1, localhost), bypass authentication
4. **Authorization Header**: Extract Authorization header from request
5. **Token Validation**: Compare against expected Bearer token format
6. **Access Decision**: Allow or deny request with appropriate HTTP status codes

### Token Requirements

- **Format**: Bearer token format required (`Authorization: Bearer <token>`)
- **Environment Variable**: Must be set in `SAFEBREACH_MCP_AUTH_TOKEN`
- **Validation**: Exact string comparison for security
- **Error Handling**: 401 Unauthorized with descriptive error message

### Security Logging

**Connection Mode Logging:**
```
🏠 Local connections only for: Config Server
🌐 External connections enabled for: Data Server, Utilities Server
🔒 HTTP Authorization required for external connections
✅ SAFEBREACH_MCP_AUTH_TOKEN configured
```

**Security Warnings:**
```
🚨 SECURITY WARNING: Server binding to 0.0.0.0:8001 - accessible from external networks!
🔒 HTTP Authorization required for external connections
🔑 Set SAFEBREACH_MCP_AUTH_TOKEN environment variable for authentication
```

**Authentication Events:**
```
✅ Authorized external connection from 192.168.1.100
🚫 Unauthorized external connection attempt from 203.0.113.1
```

## Deployment Scenarios

### Development (Default - Secure)
```bash
# No configuration needed - localhost-only by default
uv run start_all_servers.py
```

### Production External Access
```bash
# All servers accessible externally with authentication
export SAFEBREACH_MCP_AUTH_TOKEN="production-secure-token"
export SAFEBREACH_MCP_ALLOW_EXTERNAL=true
uv run start_all_servers.py
```

### Hybrid Deployment
```bash
# Only data server externally accessible, config/utilities remain local
export SAFEBREACH_MCP_AUTH_TOKEN="secure-token"
export SAFEBREACH_MCP_DATA_EXTERNAL=true
uv run start_all_servers.py
```

### Container/Kubernetes Deployment
```bash
# Bind to all interfaces with authentication
export SAFEBREACH_MCP_AUTH_TOKEN="k8s-secret-token"
uv run start_all_servers.py --external --host 0.0.0.0
```

## Client Integration

### Claude Desktop Configuration

**Local Servers (Default):**
```json
{
  "mcpServers": {
    "safebreach-data": {
      "command": "npx",
      "args": ["mcp-remote", "http://127.0.0.1:8001/sse", "--transport", "http-first"]
    }
  }
}
```

**External Servers (With Authentication):**
```json
{
  "mcpServers": {
    "safebreach-data-external": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://your-server:8001/sse", 
        "--transport", "http-first",
        "--headers", "{\"Authorization\": \"Bearer your-secure-token\"}"
      ]
    }
  }
}
```

### HTTP Client Examples

**Local Connection (No Authentication):**
```bash
curl "http://localhost:8001/sse"
```

**External Connection (With Authentication):**
```bash
curl -H "Authorization: Bearer your-secure-token" "http://your-server:8001/sse"
```

## Risk Mitigation

The implementation follows the mission's "Risk 0" mitigation strategy:

### Minimal Code Changes
- **Base Class Enhancement**: Single base class provides external connection support to all servers
- **Conditional Imports**: FastAPI imports are conditional to avoid breaking existing installations
- **Backward Compatibility**: All existing entry points and main functions preserved
- **Default Behavior**: No changes to default localhost-only behavior

### Security Safeguards
- **Explicit Configuration Required**: External access impossible without deliberate configuration
- **Authentication Mandatory**: Bearer token required for all external requests
- **Comprehensive Warnings**: Extensive logging when external access is enabled
- **Localhost Bypass**: Development convenience with automatic authentication bypass for local connections

### Automated Testing
- **Full Test Coverage**: All 139 existing tests continue to pass
- **No Regressions**: Zero breaking changes to existing functionality
- **Conditional Feature Testing**: External connection features tested when FastAPI available

This architecture provides secure, flexible external connection capabilities while maintaining the security-first design principles and backward compatibility requirements specified in the mission.