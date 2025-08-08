# End-to-End (E2E) Testing Setup

E2E tests require access to real SafeBreach environments and should only be run by developers with appropriate access.

## 🚨 Security Requirements

**NEVER commit real environment information to the public repository!**

All real SafeBreach environment details (console names, URLs, account IDs, test IDs, API tokens) must be:
- Stored in private local files only
- Loaded via environment variables
- Never included in committed code

## Setup Instructions

### 1. Create Private Environment File

```bash
# Copy the template
cp .vscode/set_env.sh.template .vscode/set_env.sh

# Edit with your REAL environment details
nano .vscode/set_env.sh
```

### 2. Configure Your Environment Variables

Edit `.vscode/set_env.sh` with your actual values:

```bash
#!/bin/bash
# Your REAL SafeBreach environment details

# API Tokens (get from SafeBreach console)
export console_a_apitoken="your-real-api-token-here"
export console_b_apitoken="your-real-api-token-here"

# E2E Test Configuration
export E2E_CONSOLE="your-real-console-name"
export E2E_CONSOLE_URL="your-console.safebreach.com" 
export E2E_CONSOLE_ACCOUNT="1234567890"

# Optional: Known test data for consistent E2E testing
export E2E_TEST_ID="your-known-test-id"
export E2E_SIMULATION_ID="your-known-simulation-id"

# MCP Authentication
export SAFEBREACH_MCP_AUTH_TOKEN="your-mcp-token"

# Additional environments file (optional)
export SAFEBREACH_ENVS_FILE="/path/to/your/environments.json"
```

### 3. Load Environment and Run Tests

```bash
# Load your private environment
source .vscode/set_env.sh

# Run E2E tests
uv run pytest safebreach_mcp_data/tests/test_e2e.py -v

# Run specific E2E test
uv run pytest safebreach_mcp_data/tests/test_e2e.py::TestDataServerE2E::test_get_tests_history_e2e -v
```

## Environment Variables Reference

### Required for E2E Tests:
- `E2E_CONSOLE` - Your SafeBreach console name 
- `{console_name}_apitoken` - API token for the console (lowercase with underscores)

### Optional (improves test reliability):
- `E2E_CONSOLE_URL` - Console URL (for validation)
- `E2E_CONSOLE_ACCOUNT` - Account ID (for validation)  
- `E2E_TEST_ID` - Specific test ID to use for testing
- `E2E_SIMULATION_ID` - Specific simulation ID to use for testing

### Additional Configuration:
- `SAFEBREACH_MCP_AUTH_TOKEN` - For testing external MCP access
- `SAFEBREACH_ENVS_FILE` - Path to additional environments JSON file

## Test Markers

E2E tests use pytest markers:

```bash
# Run all E2E tests (requires real environment)
uv run pytest -m "e2e"

# Run only unit tests (no real environment needed)
uv run pytest -m "not e2e"

# Skip E2E tests entirely
export SKIP_E2E_TESTS=true
uv run pytest
```

## Security Checks

The security framework will:
- ✅ **Block commits** containing real console names
- ✅ **Detect API tokens** in committed files
- ✅ **Prevent accidental exposure** of internal environment details
- ✅ **Allow private files** in `.vscode/set_env.sh` (git-ignored)

## Troubleshooting

### "Console not found" errors:
1. Check your console name matches exactly
2. Verify the API token is correct
3. Ensure environment variables are loaded: `env | grep -i console`

### "Authentication failed" errors:
1. Regenerate API token in SafeBreach console
2. Update your `.vscode/set_env.sh` file  
3. Reload environment: `source .vscode/set_env.sh`

### "No test data found" errors:
1. Use a console with existing test data
2. Set specific `E2E_TEST_ID` if you know a working test
3. Check console has completed tests: login to SafeBreach UI

## Best Practices

1. **Separate environments**: Use different consoles for development vs production testing
2. **Regular token rotation**: Update API tokens monthly
3. **Document test data**: Note which test IDs work reliably for E2E testing
4. **Clean test isolation**: E2E tests should not modify existing data
5. **Graceful failures**: Tests should handle missing/changed data appropriately

## VS Code Integration

The VS Code launch configurations automatically:
- Load `.vscode/set_env.sh` if present
- Set appropriate test markers
- Configure test discovery for E2E tests

Use "Run E2E Tests" configuration for end-to-end testing with your private environment.