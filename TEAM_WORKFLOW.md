# SafeBreach MCP Team Workflow Guide

## 🚀 Getting Started (New Team Members)

### Initial Setup (One-time)
```bash
# 1. Clone the repository
git clone <repository-url>
cd safebreach-mcp

# 2. Run security setup (installs all tools and hooks)
./setup-security.sh

# 3. Configure your environment
cp .env.template .env
# Edit .env with your actual API tokens (NEVER commit this file)
```

## 🤖 Daily Development Workflow

### ALWAYS Launch Claude Securely
```bash
# Instead of opening Claude Desktop directly, ALWAYS use:
./claude-launcher.sh
```

**What this gives Claude:**
- ✅ Complete project architecture knowledge
- ✅ Security best practices awareness  
- ✅ Current git status and branch info
- ✅ All available commands and test procedures
- ✅ Environment configuration details
- ✅ Pre-validated secure working environment

### Development Cycle
1. **Start work**: `./claude-launcher.sh`
2. **Make changes**: Claude has full context of security practices
3. **Test changes**: `uv run pytest safebreach_mcp_data/tests/ -m "not e2e"`
4. **Security check**: `pre-commit run --all-files`
5. **Commit**: Hooks automatically validate no secrets
6. **Push**: CI/CD runs additional security scans

## 🔒 Security-First Practices

### ✅ DO:
- Launch Claude with `./claude-launcher.sh`
- Use environment variables for secrets: `${API_TOKEN}`
- Use safe placeholders: `your-token-here`
- Test security regularly: `gitleaks detect --config .gitleaks.toml`
- Keep `.env` file local only

### ❌ NEVER:
- Hardcode real tokens in any committed file
- Commit `.env` files with real credentials
- Bypass pre-commit hooks
- Share API tokens in documentation
- Open Claude Desktop directly (missing security context)

## 📋 Common Tasks

### Running the Application
```bash
# Start all servers (recommended)
uv run start_all_servers.py

# With external access (requires auth token)
SAFEBREACH_MCP_AUTH_TOKEN="your-token" uv run start_all_servers.py --external
```

### Testing
```bash
# Unit and integration tests (recommended for development)
uv run pytest safebreach_mcp_data/tests/ -m "not e2e"

# E2E tests (requires real environment setup)
source .vscode/set_env.sh && uv run pytest safebreach_mcp_data/tests/test_e2e.py -v

# Test with coverage
uv run pytest --cov=. --cov-report=html
```

### Security Validation
```bash
# Full security scan
pre-commit run --all-files

# Just secret detection
gitleaks detect --config .gitleaks.toml

# Check specific files
detect-secrets scan path/to/file.py
```

## 🏗️ Architecture Overview for Claude Context

### Multi-Server Architecture:
- **Config Server** (Port 8000): Simulator operations
- **Data Server** (Port 8001): Test/simulation data and drift analysis  
- **Utilities Server** (Port 8002): Datetime conversion utilities
- **Playbook Server** (Port 8003): Attack knowledge base

### Core Components:
- `safebreach_mcp_core/`: Shared authentication and utilities
- `safebreach_mcp_data/`: Main business logic and data operations
- `safebreach_mcp_config/`: Simulator configuration management
- `safebreach_mcp_utilities/`: Utility functions
- `safebreach_mcp_playbook/`: Attack playbook operations

## 🚨 Security Incident Response

If Claude or anyone accidentally creates content with real secrets:

### Immediate Actions:
1. **DO NOT COMMIT** - Stop immediately
2. **Revoke tokens** in SafeBreach console  
3. **Clean working directory**: `git restore .`
4. **Generate new tokens**
5. **Update `.env` file** with new tokens
6. **Notify team** of the incident

### If Already Committed:
1. **Revoke tokens** immediately
2. **Clean git history**: Use `git filter-branch` or BFG
3. **Force push** to update remote
4. **Alert all team members**
5. **Monitor for unauthorized access**

## 📚 Documentation Standards

### Configuration Examples:
```json
{
  "mcpServers": {
    "safebreach-data": {
      "command": "npx",
      "args": [
        "mcp-remote", 
        "http://server:port/sse",
        "--headers",
        "{\"Authorization\": \"Bearer ${SAFEBREACH_TOKEN}\"}"
      ]
    }
  }
}
```

### Environment Variable Examples:
```bash
# Good - uses environment variable
export API_TOKEN="actual-secret-token"
curl -H "Authorization: Bearer ${API_TOKEN}" https://api.example.com

# Good - uses placeholder in docs
curl -H "Authorization: Bearer your-token-here" https://api.example.com
```

## 🔄 Code Review Checklist

Before approving any PR:
- [ ] No hardcoded secrets or real tokens
- [ ] Environment variables used correctly
- [ ] Documentation uses placeholders only
- [ ] Tests pass including security scans
- [ ] Pre-commit hooks are working
- [ ] `.env` files not included in changes
- [ ] Claude was launched with proper security context

## 🎯 Best Practices Summary

1. **Security First**: Always launch Claude with security context
2. **Template-Driven**: Use `.env.template` for configuration
3. **Automated Validation**: Trust the pre-commit hooks
4. **Environment Variables**: Never hardcode secrets
5. **Documentation Safety**: Use placeholders in all examples
6. **Regular Audits**: Monthly security reviews and token rotation

---

## Quick Reference

| Task | Command |
|------|---------|
| Launch Claude Securely | `./claude-launcher.sh` |
| Run Security Setup | `./setup-security.sh` |
| Start All Servers | `uv run start_all_servers.py` |
| Run Tests | `uv run pytest safebreach_mcp_data/tests/ -m "not e2e"` |
| Security Scan | `pre-commit run --all-files` |
| Check for Secrets | `gitleaks detect --config .gitleaks.toml` |

**Remember**: Security is everyone's responsibility, but automation makes it easy! 🛡️