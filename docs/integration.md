# SafeBreach MCP Integration with SIMP

This document describes how the SafeBreach MCP servers integrate with **SIMP (SafeBreach Internal MCP Proxy)** when deployed within SafeBreach management consoles. It is intended for developers working on either the MCP servers or the SIMP proxy layer.

## Overview

In production deployments, the SafeBreach MCP servers run inside SIMP, which acts as a gateway and orchestrator. SIMP is responsible for:

1. Starting and managing all MCP server instances
2. Dynamically configuring the MCP servers with the correct account ID and service URLs
3. Proxying requests from external clients to the internal MCP servers
4. Providing health check and status endpoints

## Architecture

### Full Request Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        SafeBreach Management Console                             │
│                                                                                  │
│   ┌───────────┐                                                                  │
│   │  External │                                                                  │
│   │  Clients  │──────────────┐                                                   │
│   │  (HTTPS)  │              │                                                   │
│   └───────────┘              ▼                                                   │
│                    ┌──────────────────┐                                          │
│                    │      NGINX       │                                          │
│                    │   (TLS Termination)                                         │
│                    │      :443        │                                          │
│                    └────────┬─────────┘                                          │
│                             │                                                    │
│                             ▼                                                    │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                    ui-server Container (sbui)                             │  │
│   │                           Port 1990                                       │  │
│   │                                                                           │  │
│   │   app.js:160  →  app.use('/api/mcp', authMiddleware, mcpProxyHandler())  │  │
│   │                                                                           │  │
│   │   Features:                                                               │  │
│   │   • Authentication middleware (JWT/API token validation)                  │  │
│   │   • SSE support (compression disabled, no timeout)                        │  │
│   │   • WebSocket support                                                     │  │
│   │   • CSP header injection                                                  │  │
│   └────────────────────────────────┬──────────────────────────────────────────┘  │
│                                    │                                             │
│                                    │ HTTP Proxy                                  │
│                                    │ /api/mcp/* → localhost:4150                 │
│                                    ▼                                             │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                    SIMP Container (mcp-proxy)                             │  │
│   │                           Port 4150                                       │  │
│   │                                                                           │  │
│   │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │  │
│   │   │   Gateway   │    │ MCP Manager │    │  SB Client  │                  │  │
│   │   │  (FastAPI)  │    │             │    │             │                  │  │
│   │   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                  │  │
│   │          │                  │                  │                          │  │
│   │          │    Starts & Configures              │ Retrieves                │  │
│   │          │         ▼                           │ Account ID               │  │
│   │          │  ┌───────────────────────────────────────────────────────┐    │  │
│   │          │  │              MCP Servers (localhost)                   │    │  │
│   │          │  │                                                        │    │  │
│   │          │  │  ┌────────────┐  ┌────────────┐  ┌────────────┐       │    │  │
│   │          │  │  │   Config   │  │  Utilities │  │    Data    │       │    │  │
│   │          │  │  │   :8000    │  │   :8001    │  │   :8002    │       │    │  │
│   │          │  │  └─────┬──────┘  └────────────┘  └─────┬──────┘       │    │  │
│   │          │  │        │                               │              │    │  │
│   │          │  │  ┌────────────┐                                       │    │  │
│   │          │  │  │  Playbook  │                                       │    │  │
│   │          │  │  │   :8003    │                                       │    │  │
│   │          │  │  └─────┬──────┘                                       │    │  │
│   │          │  └────────┼───────────────────────────────────┼──────────┘    │  │
│   └──────────┼───────────┼───────────────────────────────────┼───────────────┘  │
│              │           │                                   │                   │
│              ▼           ▼                                   ▼                   │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │                    SafeBreach Backend Services                            │  │
│   │                                                                           │  │
│   │   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │  │
│   │   │   Config   │  │    Data    │  │  Playbook  │  │    SIEM    │        │  │
│   │   │   :5000    │  │   :3123    │  │   :5100    │  │  :10010    │        │  │
│   │   └────────────┘  └────────────┘  └────────────┘  └────────────┘        │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Request Path Summary

| Step | Component | Port | Action |
|------|-----------|------|--------|
| 1 | NGINX | 443 | TLS termination, routes to ui-server |
| 2 | ui-server | 1990 | Authentication, proxies `/api/mcp/*` to SIMP |
| 3 | SIMP | 4150 | Routes to internal MCP servers |
| 4 | MCP Server | 8000-8003 | Processes request, calls backend services |
| 5 | Backend | 3123/5000/5100/10010 | Returns data |

## ui-server Component

The **ui-server** (sbui container) is the main web application server that handles all user-facing HTTP traffic. It proxies MCP requests to SIMP with special handling for SSE (Server-Sent Events).

### MCP Proxy Configuration

**Configuration in `server.conf`:**
```json
{
  "MCP_PROXY_PORT": 4150,
  "MCP_PROXY_HOST": "localhost"
}
```

**Endpoint mapping in `endpointsMap.js`:**
```javascript
mcp: {
  host: cfg.get('MCP_PROXY_HOST'),
  port: cfg.get('MCP_PROXY_PORT')
}
```

### MCP Proxy Handler

The MCP proxy handler (`endpointHandlers.js:758-786`) is specifically designed for MCP traffic:

```javascript
this.mcpProxyHandler = function() {
  const mcpProxy = httpProxy.createProxyServer({
    target: `http://${cfg.get('MCP_PROXY_HOST')}:${cfg.get('MCP_PROXY_PORT')}`,
    changeOrigin: true,
    ws: true,           // WebSocket support
    xfwd: true,         // Forward X-headers
    proxyTimeout: 0,    // No timeout (for SSE)
    timeout: 0,         // No timeout (for SSE)
    insecureHTTPParser: true
  });
  // ... error handling and CSP headers ...
};
```

### SSE Support

MCP uses Server-Sent Events (SSE) for streaming responses. The ui-server has special handling:

1. **Compression disabled** for `/api/mcp/*` routes (`app.js:108-113`):
   ```javascript
   app.use((req, res, next) => {
     if (req.path.startsWith('/api/mcp')) {
       return next();  // Skip compression
     }
     compress()(req, res, next);
   });
   ```

2. **No timeouts** on proxy connections to allow long-lived SSE streams

3. **X-Accel-Buffering: no** header added to prevent nginx buffering

### Authentication

MCP routes use the standard auth middleware (`app.js:160`):
```javascript
app.use('/api/mcp', authMiddleware, endpointHandlers.mcpProxyHandler());
```

This validates:
- JWT tokens (cookie-based or header-based)
- API tokens
- OPA policy authorization

## SIMP Components

SIMP consists of the following key components:

### 1. Configuration (`cfg.py`)

Reads configuration from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SB_URL` | `None` | SafeBreach console URL (uses localhost if not set) |
| `SB_API_KEY` | `None` | API key for SafeBreach authentication |
| `SIMP_PORT` | `4150` | Port for SIMP gateway |
| `MCP_BASE_PORT` | `8000` | Base port for MCP servers |
| `MCP_HOST` | `127.0.0.1` | Host for MCP servers |

### 2. SafeBreach Client (`sb_client.py`)

Retrieves the account ID from the SafeBreach configuration service:

```python
# Queries localhost:5000/api/config/v1/accounts
# Falls back to '123456789' if retrieval fails
```

**Important**: If account ID retrieval fails at startup, all subsequent API calls will use the wrong account ID and return empty results.

### 3. MCP Manager (`mcp_manager.py`)

Orchestrates the MCP servers:

1. **Builds dynamic configuration** via `SAFEBREACH_LOCAL_ENV`
2. **Sets environment variables** for each server
3. **Starts all MCP servers** as background tasks
4. **Manages server lifecycle** (startup/shutdown)

### 4. Gateway (`gateway.py`)

Proxies requests to internal MCP servers:

- Validates and sanitizes request paths
- Routes requests to correct MCP server
- Handles SSE streaming responses
- Provides security against path traversal attacks

### 5. Server (`server.py`)

Main FastAPI application:

- Manages application lifespan (startup/shutdown)
- Exposes `/status` endpoint for health checks
- Includes MCP management routes

## Startup Sequence

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           SIMP Startup Sequence                           │
└──────────────────────────────────────────────────────────────────────────┘

1. SIMP Container Starts
         │
         ▼
2. Read Configuration (SB_URL, SB_API_KEY from environment)
         │
         ▼
3. Initialize SB Client
         │
         ├─── Success ───► Account ID retrieved (e.g., ***1234)
         │
         └─── Failure ───► Fallback to '123456789' ⚠️ WARNING
                          (All API calls will return empty results!)
         │
         ▼
4. Build SAFEBREACH_LOCAL_ENV Configuration
         │
         ▼
5. Start MCP Servers (configuration, utilities, data, playbook)
         │
         ▼
6. Initialize Gateway
         │
         ▼
7. SIMP Ready on Port 4150
```

## Dynamic Configuration

SIMP creates the `default` console configuration dynamically at startup. This configuration is **not** defined in `environments_metadata.py`.

### SAFEBREACH_LOCAL_ENV Structure

```json
{
  "default": {
    "url": "localhost",
    "urls": {
      "config": "http://localhost:5000/",
      "data": "http://localhost:3123/",
      "playbook": "http://localhost:5100/",
      "siem": "http://localhost:10010/"
    },
    "account": "<retrieved-account-id>",
    "secret_config": {
      "provider": "env_var",
      "parameter_name": "SB_API_KEY"
    }
  }
}
```

### Environment Variables Set by SIMP

For each MCP server, SIMP sets:

| Variable | Value | Description |
|----------|-------|-------------|
| `SAFEBREACH_LOCAL_ENV` | JSON config | Dynamic console configuration |
| `SAFEBREACH_CONSOLE_NAME` | `default` | Console name for single-tenant mode |
| `SAFEBREACH_MCP_BASE_URL` | `/api/mcp/<server>` | Base URL for MCP endpoints |
| `ACCOUNT_ID` | Retrieved value | SafeBreach account ID |
| `DATA_URL` | `http://localhost:3123` | Data service URL |
| `CONFIG_URL` | `http://localhost:5000` | Config service URL |
| `SB_API_KEY` | From env or `'empty'` | API key for authentication |

## Service Dependencies

SIMP and the MCP servers depend on SafeBreach backend services being available:

| Service | Port | Used By | Purpose |
|---------|------|---------|---------|
| sbconfiguration | 5000 | SIMP, Config MCP | Account ID retrieval, simulator data |
| sbdata | 3123 | Data MCP | Test history, simulation results |
| sbplaybook | 5100 | Playbook MCP | Attack playbook data |
| sbsiem | 10010 | Data MCP | Security control events |

### Critical Dependency: sbconfiguration

The `sbconfiguration` service (port 5000) must be available **before** SIMP starts. If it's not ready:

1. Account ID retrieval fails
2. SIMP uses fallback account ID `123456789`
3. All MCP API calls use the wrong account ID
4. All queries return empty results (0 simulators, 0 simulations, etc.)

## Port Mapping

### MCP Servers in SIMP

| Server | Port | Module |
|--------|------|--------|
| Configuration | 8000 | `safebreach_mcp_config.config_server` |
| Utilities | 8001 | `safebreach_mcp_utilities.utilities_server` |
| Data | 8002 | `safebreach_mcp_data.data_server` |
| Playbook | 8003 | `safebreach_mcp_playbook.playbook_server` |

### Gateway Routes

SIMP exposes these routes on port 4150:

| Route Pattern | Target |
|---------------|--------|
| `/api/mcp/configuration/*` | `http://127.0.0.1:8000/api/mcp/configuration/*` |
| `/api/mcp/utilities/*` | `http://127.0.0.1:8001/api/mcp/utilities/*` |
| `/api/mcp/data/*` | `http://127.0.0.1:8002/api/mcp/data/*` |
| `/api/mcp/playbook/*` | `http://127.0.0.1:8003/api/mcp/playbook/*` |

## Console Name Resolution

In SIMP-hosted deployments:

- **Console name is always `default`**
- The `default` console is created dynamically by SIMP
- It is **not** defined in `environments_metadata.py`
- API tokens use `SB_API_KEY` environment variable

When the MCP code calls `get_environment_by_name('default')`, it finds the configuration that SIMP injected via `SAFEBREACH_LOCAL_ENV`.

## Troubleshooting

### Checking SIMP Health

```bash
# Check container status
sudo docker ps --filter name=mcp-proxy

# Check SIMP logs for startup
sudo docker logs mcp-proxy 2>&1 | head -50

# Check account ID retrieval
sudo docker logs mcp-proxy 2>&1 | grep -E "(account|Initialized|Failed)"
```

### Healthy Startup Logs

```
Starting SIMP (SafeBreach Internal MCP Proxy)...
Configuration: SB_URL=localhost (default), SB_API_KEY=<not_configured>
Initialized successfully for management http://localhost:5000 account: ***1234
Retrieved account ID from SafeBreach: ***1234
Set SAFEBREACH_LOCAL_ENV with account ID: 1234567890, using URLs: ...
SafeBreach MCP Configuration Server started on port 8000
SafeBreach MCP Utilities Server started on port 8001
SafeBreach MCP Data Server started on port 8002
SafeBreach MCP Playbook Server started on port 8003
All 4 SafeBreach MCP servers started successfully
SIMP service ready on port 4150
```

### Unhealthy Startup Logs (Account ID Retrieval Failed)

```
Starting SIMP (SafeBreach Internal MCP Proxy)...
Configuration: SB_URL=localhost (default), SB_API_KEY=<not_configured>
WARNING - Failed to retrieve account ID: HTTPConnectionPool(host='localhost', port=5000):
          Max retries exceeded (Caused by NewConnectionError: Connection refused)
Retrieved account ID from SafeBreach: ***6789  ← FALLBACK VALUE - THIS IS WRONG!
Set SAFEBREACH_LOCAL_ENV with account ID: 123456789
```

**Symptoms of wrong account ID:**
- All API calls return empty results
- 0 simulators, 0 simulations, 0 tests
- No error messages in logs (API calls succeed but return no data)

### Fix: Restart After Services Are Ready

```bash
# Ensure sbconfiguration is running
sudo docker ps | grep sbconfiguration

# Restart mcp-proxy
sudo docker restart mcp-proxy

# Verify correct account ID
sudo docker logs mcp-proxy 2>&1 | grep "Retrieved account ID"
# Should show real account ID, NOT ***6789
```

### Verifying API Connectivity

```bash
# Test config service (should return account data)
sudo docker exec mcp-proxy wget -q -O- http://localhost:5000/api/config/v1/accounts

# Test data service (should return test summaries)
sudo docker exec mcp-proxy wget -q -O- \
  "http://localhost:3123/api/data/v1/accounts/<account-id>/testsummaries?size=1"
```

## Development Considerations

### When Developing MCP Servers

1. **The `default` console is special**: In SIMP deployments, it's created dynamically and won't exist in `environments_metadata.py`

2. **Handle missing configuration gracefully**: The MCP servers should work when `SAFEBREACH_LOCAL_ENV` provides the configuration

3. **Don't assume port numbers**: SIMP controls which ports the servers run on

4. **Caching considerations**: In SIMP deployments, caching is typically disabled because data services are co-located

### When Developing SIMP

1. **Ensure startup ordering**: Account ID retrieval must succeed before starting MCP servers

2. **Consider retry logic**: Add retries with backoff for account ID retrieval to handle startup timing issues

3. **Validate account ID**: Don't silently use fallback values that will cause all API calls to fail

4. **Log configuration clearly**: Make it easy to diagnose configuration issues from logs

## Related Files

### In safebreach-mcp Repository

| File | Purpose |
|------|---------|
| `safebreach_mcp_core/environments_metadata.py` | Environment configuration and URL resolution |
| `safebreach_mcp_core/secret_utils.py` | Secret retrieval using configured providers |
| `safebreach_mcp_core/cache_config.py` | Cache enable/disable configuration |

### In SIMP (mcp-proxy container)

| File | Purpose |
|------|---------|
| `/src/simp/server.py` | Main FastAPI application |
| `/src/simp/mcp_manager.py` | MCP server orchestration |
| `/src/simp/sb_client.py` | Account ID retrieval |
| `/src/simp/gateway.py` | Request proxying |
| `/src/simp/cfg.py` | Configuration management |

### In ui-server (sbui container)

| File | Purpose |
|------|---------|
| `src/server/app.js` | Main Express application, MCP route registration |
| `src/server/controllers/endpointHandlers.js` | MCP proxy handler with SSE support |
| `src/server/controllers/endpointsMap.js` | Service endpoint configuration including MCP |
| `server.conf` | Default configuration (MCP_PROXY_HOST, MCP_PROXY_PORT) |

## Version History

| Date | Change |
|------|--------|
| 2026-01-21 | Added ui-server component documentation and full request flow |
| 2026-01-20 | Initial documentation based on production investigation |
