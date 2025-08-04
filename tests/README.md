# SafeBreach MCP Multi-Server Test Suite

This directory contains comprehensive unit and integration tests for the SafeBreach MCP multi-server architecture.

## Test Structure

**Multi-Server Architecture Tests:**
- `safebreach_mcp_config/tests/` - Config Server unit and integration tests
- `safebreach_mcp_data/tests/` - Data Server unit and integration tests  
- `safebreach_mcp_utilities/tests/` - Utilities Server unit and integration tests
- `safebreach_mcp_playbook/tests/` - Playbook Server unit and integration tests

**External Authentication Tests:**
- `test_external_authentication.py` - Unit tests for external connection authentication framework
- `run_auth_tests.py` - Comprehensive authentication test suite runner

## Running Tests

### Run all tests:
```bash
# Run all multi-server architecture tests
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/
```

### Run server-specific tests:
```bash
# Config Server tests
uv run pytest safebreach_mcp_config/tests/

# Data Server tests
uv run pytest safebreach_mcp_data/tests/

# Utilities Server tests
uv run pytest safebreach_mcp_utilities/tests/

# Playbook Server tests
uv run pytest safebreach_mcp_playbook/tests/

# Run authentication test suite
uv run python tests/run_auth_tests.py
```

### Run integration tests:
```bash
# Multi-server integration tests
uv run pytest safebreach_mcp_data/tests/test_integration.py
```

### Run with coverage:
```bash
# Comprehensive coverage across all multi-server components
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ --cov=. --cov-report=html


### Run specific test:
```bash
uv run pytest safebreach_mcp_config/tests/test_config_functions.py::TestConfigFunctions::test_sb_get_console_simulators_success
```

## Test Coverage

The test suite covers:

### Functions Tested

**Multi-Server Architecture Functions:**

**Config Server Functions:**
1. `sb_get_console_simulators` ✨ **Enhanced** - Filtered simulator retrieval with status, name, label, OS type, and criticality filtering
2. `sb_get_simulator_details` - Get detailed simulator information

**Data Server Functions:**
3. `sb_get_tests_history` ✨ **Enhanced** - Filtered and paginated test execution history with advanced filtering options
4. `sb_get_test_details` ✨ **Enhanced** - Full details for specific tests with optional simulation statistics
5. `sb_get_test_simulations` ✨ **Enhanced** - Filtered and paginated simulations within tests
6. `sb_get_simulation_details` ✨ **Enhanced** - Detailed simulation results with optional MITRE techniques and attack logs
7. `sb_get_security_controls_events` ✨ **New** - Filtered security control events with comprehensive filtering
8. `sb_get_security_control_event_details` ✨ **New** - Detailed security control event information with verbosity levels
9. `sb_get_test_findings_counts` ✨ **New** - Aggregated findings counts with filtering
10. `sb_get_test_findings_details` ✨ **New** - Detailed findings information with filtering and pagination

**Playbook Server Functions:**
11. `sb_get_playbook_attacks` ✨ **NEW** - Filtered and paginated playbook attacks with comprehensive filtering (name, description, ID range, date ranges)
12. `sb_get_playbook_attack_details` ✨ **NEW** - Detailed attack information with verbosity options (fix suggestions, tags, parameters)

**Utilities Server Functions:**
13. `convert_datetime_to_epoch` - Convert ISO datetime strings to Unix timestamps
14. `convert_epoch_to_datetime` - Convert Unix timestamps to readable datetime strings

**Data Transformation Functions (per server):**
- Config Server: Simulator mapping and transformation functions
- Data Server: Test, simulation, security events, and findings mapping functions
- Playbook Server: Playbook attack mapping and transformation functions
- Shared Core: Common utilities and authentication across all servers

### Test Scenarios
- **Success cases** - Normal operation with valid data
- **Error handling** - API errors, invalid responses, network timeouts
- **Cache behavior** - Cache hits, misses, expiration, isolation
- **Pagination** - Edge cases, large datasets, boundary conditions
- **Environment handling** - Multiple console environments
- **Data transformation** - Proper mapping and filtering
- **End-to-end workflows** - Real API calls testing complete functionality
- **Filter combinations** - Complex filtering scenarios with real data

### Mocking Strategy
- AWS SSM Parameter Store calls
- HTTP requests to SafeBreach APIs
- Time-based operations for cache testing
- Response data transformation functions

## Dependencies

The test suite requires:
- `pytest>=7.0.0` - Test framework
- `pytest-mock>=3.10.0` - Enhanced mocking capabilities
- `unittest.mock` - Python built-in mocking (from standard library)

## Test Data

Test fixtures provide:
- Sample simulator configurations
- Mock API responses
- Test and simulation data structures
- Cache state scenarios

## CI/CD Integration

**Unit and Integration Tests** are designed to run in CI/CD pipelines with:
- No external dependencies (fully mocked)
- Fast execution times
- Clear pass/fail indicators
- Detailed error reporting

**End-to-End Tests** require additional setup:
- **AWS credentials** for SSM Parameter Store access:
  - Configure via `aws configure` or environment variables
  - Must have `ssm:GetParameter` permission
  - Tests will auto-skip if credentials are invalid/missing
- **SafeBreach API token**: `{console-name}-apitoken` stored in AWS SSM Parameter Store
- **Network access** to the specified SafeBreach console
- **Console configuration**: Set `E2E_CONSOLE` environment variable to specify target console
- **Environment control**: Set `SKIP_E2E_TESTS=true` to disable in CI/CD environments

**Setting up AWS credentials:**
```bash
# Option 1: AWS CLI configuration
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

**Testing Multi-Server Architecture:**
The test suite validates that all four servers (Config, Data, Utilities, Playbook) work independently and together, with proper error handling, caching, and filtering capabilities.

## Test Coverage

The test suite provides comprehensive coverage:
- **Config Server Unit Tests**: 17 tests covering simulator functions and filtering
- **Data Server Unit Tests**: 72 tests covering test, simulation, security events, and findings functions
- **Utilities Server Unit Tests**: 10 tests covering datetime conversion functions
- **Playbook Server Unit Tests**: 25+ tests covering playbook attack functions and filtering
- **Integration Tests**: 16 tests covering complex multi-server workflows
- **End-to-End Tests**: 9+ tests covering real API interactions across servers
- **Total Tests**: 150+ tests with comprehensive coverage across all four servers