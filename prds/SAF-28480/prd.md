# SAF-28480: Add HTTP Streamable Transport Mode

## Overview

- **Task Type**: Enhancement
- **Purpose**: Allow the SafeBreach MCP servers to run in `streamable-http` transport mode in addition to the existing SSE transport
- **Target Consumer**: Any MCP client that prefers the streamable-http protocol (e.g., newer versions of Claude Desktop, mcp-remote, programmatic clients)
- **Originating Request**: SAF-28480 — requested to support clients that use HTTP Streamable MCP transport

## Problem

All five SafeBreach MCP servers (config, data, utilities, playbook, studio) use SSE transport exclusively via `FastMCP.sse_app()`. This requires clients to maintain a long-lived SSE connection (`/sse`) for receiving events, plus separate HTTP POST requests to `/messages/?session_id=...` for sending.

The MCP SDK (v1.12.1) provides a second transport, `streamable-http`, which uses a single `/mcp` HTTP endpoint for both sending and receiving. This is simpler for clients that prefer standard request/response semantics with optional streaming.

There was no way to configure the transport without code changes.

## Solution

Read the transport from a new environment variable `SAFEBREACH_MCP_TRANSPORT` in `run_server()` and select the appropriate FastMCP app:

| Value | FastMCP method | Endpoint |
|---|---|---|
| `sse` (default) | `FastMCP.sse_app()` | `/sse` + `/messages/` |
| `streamable-http` | `FastMCP.streamable_http_app()` | `/mcp` (or `$BASE_URL`) |

### Changes to `safebreach_mcp_core/safebreach_base.py`

**1. `run_server()` — resolve transport and select app:**

```python
transport = os.environ.get('SAFEBREACH_MCP_TRANSPORT', 'sse').strip().lower()
if transport not in ('sse', 'streamable-http'):
    logger.warning(f"Unknown SAFEBREACH_MCP_TRANSPORT value '{transport}', falling back to 'sse'")
    transport = 'sse'

if transport == 'streamable-http':
    endpoint_path = self.base_url if self.base_url != '/' else '/mcp'
    self.mcp.settings.streamable_http_path = endpoint_path
    mcp_app = self.mcp.streamable_http_app()
    app = mcp_app
    ...
else:
    # existing SSE code — unchanged
```

`self.mcp.settings.streamable_http_path` is mutated before calling `streamable_http_app()` so that `SAFEBREACH_MCP_BASE_URL` is honoured: when `base_url=/api/mcp`, the streamable-http endpoint becomes `/api/mcp` (not `/api/mcp/mcp`).

**2. `_create_concurrency_limited_app()` — add streamable-http session tracking:**

The method signature gains `transport` and `endpoint_path` parameters. A new branch handles streamable-http sessions, which are identified by the `Mcp-Session-Id` request header (versus SSE sessions which use the `session_id` query-string parameter):

```python
if transport == 'streamable-http' and path == endpoint_path:
    session_id = headers.get(b"mcp-session-id", b"").decode(...)
    if not session_id:
        return await original_app(scope, receive, send)  # initialize — pass through
    # lazy semaphore creation + rate limiting (identical logic to SSE branch)
```

The existing SSE paths (`/sse` and `/messages/`) are **unchanged**.

## New Environment Variable

| Variable | Values | Default |
|---|---|---|
| `SAFEBREACH_MCP_TRANSPORT` | `sse`, `streamable-http` | `sse` |

## Backward Compatibility

- Default value is `sse` — all existing deployments are unaffected
- Unknown values log a warning and fall back to `sse`
- No changes to `start_all_servers.py` or any individual server file

## Testing

```bash
# Verify SSE mode still works (regression)
uv run start_all_servers.py

# Verify streamable-http mode
SAFEBREACH_MCP_TRANSPORT=streamable-http uv run start_all_servers.py
# Endpoint: http://127.0.0.1:8001/mcp

# Verify with custom base URL
SAFEBREACH_MCP_TRANSPORT=streamable-http SAFEBREACH_MCP_BASE_URL=/api/mcp uv run start_all_servers.py
# Endpoint: http://127.0.0.1:8001/api/mcp

# Run unit tests
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ -m "not e2e"
```
