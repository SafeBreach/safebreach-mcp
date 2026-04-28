# Per-User RBAC Enforcement in SafeBreach MCP Servers — SAF-29974

## 1. Overview

SafeBreach MCP servers previously used a single shared API key (`SB_API_KEY`) for all
backend API calls. Every user — regardless of role — executed tool calls with the same
admin-level credentials. This bypassed RBAC entirely: a restricted user could read
simulation data they shouldn't have access to, and audit logs couldn't trace actions to
individual users.

This change makes MCP servers **RBAC-aware**: each tool call uses the requesting user's
own auth credentials, so the backend (OPA at the ui-server) enforces per-user
permissions. The shared API key is no longer used for tool calls in embedded mode.

**Ticket**: [SAF-29974](https://safebreach.atlassian.net/browse/SAF-29974)
**Type**: Feature
**Priority**: High

---

## 2. Motivation

### The Problem

```
User A (restricted) ──► MCP tool call ──► backend API (shared SB_API_KEY) ──► 200 OK
User B (admin)       ──► MCP tool call ──► backend API (shared SB_API_KEY) ──► 200 OK
```

Both users get identical access because the backend sees the same credential. RBAC
enforcement at OPA (ui-server) never evaluates the actual user's permissions.

### The Goal

```
User A (restricted) ──► MCP tool call ──► backend API (User A's token) ──► 403 Forbidden
User B (admin)       ──► MCP tool call ──► backend API (User B's token) ──► 200 OK
```

Each tool call carries the requesting user's auth credentials. OPA evaluates per-user
permissions. Restricted users are denied access to resources outside their role.

### Business Value

1. Non-admin users gain MCP tool access with their native RBAC restrictions
2. Backend audit logs trace actions to individual users (not a shared service account)
3. Per-user cache isolation prevents cross-user data leakage

---

## 3. Deployment Modes

SafeBreach MCP servers have two deployment modes. This change must preserve both.

### Embedded Mode (inside SIMP/mcp-proxy)

The MCP servers run as asyncio tasks inside the mcp-proxy (SIMP) process. SIMP is the
gateway that sits between clients (AI agents, breach-genie) and the MCP servers.

- SIMP forwards user auth headers (`x-apitoken`, `x-token`, `cookie`) on every request
- Backend API calls route through `http://127.0.0.1:1990` (ui-server) where OPA
  enforces per-user RBAC
- `SAFEBREACH_LOCAL_ENV` is set by SIMP's `mcp_manager` — this is the signal that
  embedded mode is active
- **RBAC is enforced**: tool calls without valid user credentials are rejected

### Standalone Mode (external deployment)

The MCP server runs independently, connecting to a SafeBreach console via its external
URL. Users connect directly (e.g., from Claude Desktop).

- No SIMP gateway — no auth headers are forwarded
- API keys come from environment variables or secret providers
- `SAFEBREACH_LOCAL_ENV` is **not set**
- **RBAC is not enforced**: tool calls use the shared API key from env vars

### Mode Detection

`get_auth_headers_for_console()` uses `SAFEBREACH_LOCAL_ENV` as the discriminator:

```python
if os.environ.get('SAFEBREACH_LOCAL_ENV'):
    # Embedded mode — RBAC enforced, raise on missing auth
    raise AuthenticationRequired(...)
else:
    # Standalone mode — fall back to env-var API key
    return {'x-apitoken': get_secret_for_console(console)}
```

---

## 4. Design

### Auth Resolution Chain

`get_auth_headers_for_console(console)` is the single entry point for all tool
functions to obtain auth headers. It replaces direct calls to
`get_secret_for_console()`.

```
1. _user_auth_artifacts ContextVar
   └─ Set by ASGI middleware from request headers (works for streamable-http)

2. MCP SDK request_ctx (mcp.server.lowlevel.server.request_ctx)
   └─ Reads auth headers from the POST request that triggered the tool call
   └─ Works for BOTH SSE and streamable-http (SDK sets it on the tool handler's task)

3. Session store (_session_auth_artifacts[session_id])
   └─ Defensive tertiary fallback keyed by MCP session ID

4. Mode-dependent final fallback:
   └─ Embedded (SAFEBREACH_LOCAL_ENV set): raise AuthenticationRequired
   └─ Standalone (no SAFEBREACH_LOCAL_ENV): get_secret_for_console() → env-var API key
```

### Why Three Tiers?

The SSE transport has an async context isolation issue: `SseServerTransport.connect_sse`
uses `anyio.create_task_group()`. The tool handler runs in a different async context
than the `/messages/` POST ASGI middleware, so `_user_auth_artifacts` ContextVar (tier
1) is empty.

The MCP SDK's `request_ctx` (tier 2) solves this: it IS set on the same task as the
tool handler (`server.py:638-646`). The SDK passes the POST request via
`ServerMessageMetadata(request_context=request)` through the message stream. The
`_get_auth_from_mcp_request_ctx()` helper extracts auth headers from
`request_ctx.get().request.headers`.

The session store (tier 3) is a defensive fallback for edge cases.

### Key Discovery: MCP SDK request_ctx

The MCP Python SDK (v1.12.1) provides a `request_ctx` ContextVar at
`mcp.server.lowlevel.server:105`. It holds a `RequestContext` whose `.request`
attribute is the Starlette `Request` from the POST that triggered the tool call.

For **SSE**: `request.query_params.get('session_id')` gives the session ID.
For **streamable-http**: `request.headers.get('mcp-session-id')` gives the session ID.
For **both**: `request.headers` contains the auth headers SIMP forwarded.

This eliminates the need for any module-level global variable.

---

## 5. Approaches Considered

### A. Headers-First ContextVar + MCP SDK request_ctx (chosen)

Extract auth from ASGI headers on every request, with MCP SDK `request_ctx` as the
primary fallback for SSE transport. No tool signature changes needed.

- Pros: Minimal code changes, concurrency-safe, backward compatible
- Cons: Depends on MCP SDK's `request_ctx` internal (guarded with try/except)

### B. Explicit Token Parameter in Tool Functions

Add `api_token: Optional[str]` to every tool function signature.

- Pros: Explicit, no hidden state
- Cons: Dozens of signature changes, exposes token in MCP protocol messages
- **Rejected**: Too invasive, security concern

### C. Per-User MCP Server Sessions

Spawn dedicated MCP server instances per user with their token.

- Pros: Zero code changes in tool functions
- Cons: Massive resource overhead, port management, startup latency
- **Rejected**: Does not scale

### D. Module-Level Global Variable (_last_user_auth_bundle)

Store the most recent user's auth bundle in a module-level variable as fallback when
ContextVar doesn't propagate.

- Pros: Simple, works for single-user scenarios
- Cons: Cross-user credential contamination under concurrent sessions
- **Implemented in Slice 4, replaced in Slice 6**: Used as an interim bridge for SSE
  transport. Replaced by `request_ctx` approach once we discovered the SDK provides
  per-request context to tool handlers.

---

## 6. Changes

### 6.1. New Module: `safebreach_mcp_core/token_context.py`

Central module for per-request auth context. Contains:

| Function | Purpose |
|----------|---------|
| `_user_auth_artifacts` ContextVar | Per-request auth bundle (primary source) |
| `_session_auth_artifacts` dict | Session-keyed backup store with TTL |
| `extract_auth_bundle(scope)` | Extract auth headers from ASGI scope |
| `_get_auth_from_mcp_request_ctx()` | Read auth from MCP SDK's `request_ctx` |
| `_get_session_id_from_mcp_ctx()` | Extract session ID from `request_ctx` |
| `get_cache_user_suffix()` | SHA-256 hash prefix for per-user cache keys |
| `_keep_only_cookie()` | Cookie scrubbing (keep X-Token + __secure-Fgp only) |
| `cleanup_stale_artifacts()` | TTL-based eviction (1 hour, runs every 10 minutes) |

### 6.2. Modified: `safebreach_mcp_core/secret_utils.py`

- `get_auth_headers_for_console(console)` — new function, 4-tier resolution chain
- `check_rbac_response(response)` — replaces `raise_for_status()` with 403
  `hint_to_llm` for LLM-friendly permission denial messages
- `AuthenticationRequired` exception class
- `get_secret_for_console()` unchanged — still used by startup paths and standalone mode

### 6.3. Modified: `safebreach_mcp_core/safebreach_base.py`

Extended `_create_concurrency_limited_app()` ASGI wrapper:

- **All requests**: Headers-first auth bundle extraction via `extract_auth_bundle(scope)`
- **SSE GET**: Stores bundle in `_session_auth_artifacts` under middleware session ID,
  migrates to real session ID when captured from response body
- **SSE POST**: Stores bundle in session store, sets ContextVar as fallback
- **Streamable-HTTP**: Stores bundle in session store keyed by `Mcp-Session-Id` header
- **Cleanup**: Evicts auth artifacts on SSE disconnect and via periodic TTL sweep

### 6.4. Modified: `safebreach_mcp_core/environments_metadata.py`

- `get_api_base_url()` priority reordered: `SAFEBREACH_LOCAL_ENV` > env vars
- Unknown console names fall back to `'default'` entry in `SAFEBREACH_LOCAL_ENV`
  (prevents OPA bypass via unknown console name)

### 6.5. Tool Function Migration (all 4 server packages)

All 33 tool functions migrated from:
```python
apitoken = get_secret_for_console(console)
headers = {"x-apitoken": apitoken, "Content-Type": "application/json"}
```
to:
```python
headers = {**get_auth_headers_for_console(console), "Content-Type": "application/json"}
```

All `raise_for_status()` calls replaced with `check_rbac_response()` (35 sites).

| Package | Functions migrated | Cache keys updated |
|---------|-------------------|-------------------|
| `safebreach_mcp_data` | 10 | 8 |
| `safebreach_mcp_config` | 7 | 6 |
| `safebreach_mcp_studio` | 14 | 3 |
| `safebreach_mcp_playbook` | 1 | 1 |
| `safebreach_mcp_core` (suggestions) | 1 | 1 |

### 6.6. Per-User Cache Keys

All cache keys now include `get_cache_user_suffix()` — an 8-char SHA-256 hash of the
most stable auth artifact (priority: `x-apitoken` > `x-token` > cookie value).

Example: `tests_default` → `tests_default_a3f8b2c1`

Returns empty string in standalone mode (no user context), preserving existing behavior.

### 6.7. Dead Code Removed

- `SafeBreachAuth` class removed from `SafeBreachMCPBase.__init__` — its
  `get_base_url()` bypassed the RBAC gateway by resolving from `env['url']` directly

---

## 7. Cookie Handling

### Scrubbing

The incoming `cookie` header may contain dozens of cookies (analytics, CSRF, session
IDs). The middleware scrubs it to keep only:

- `X-Token` — the JWT (configurable via `SAFEBREACH_MCP_AUTH_COOKIE_NAME`)
- `__secure-Fgp` — the user fingerprint cookie required for JWT validation

### JWT Fingerprint

The ui-server's JWT validation requires the `__secure-Fgp` cookie alongside the JWT.
Without it, `x-token` auth returns 401. This was discovered during implementation and
the cookie scrubbing was updated to preserve it.

---

## 8. Security Considerations

### OPA Bypass via Unknown Console Name (Fixed)

A caller could specify `console='anything'` in a tool call. If the console name wasn't
in `SAFEBREACH_LOCAL_ENV`, `get_api_base_url()` fell through to direct-port env vars,
bypassing OPA. Fixed: unknown console names fall back to the `'default'` entry.

### Concurrency Safety

The initial implementation used `_last_user_auth_bundle` (a module-level global) as
fallback for SSE transport. This was a **cross-user credential contamination** bug:
concurrent users would overwrite each other's credentials.

Replaced with per-request auth extraction from the MCP SDK's `request_ctx`. Each tool
call reads its own POST's headers — zero shared mutable state, zero race conditions.

### Health Check Placeholder

breach-genie's MCPClient health check uses `x-apitoken: internal-health-check` to pass
SIMP's auth gate. This is safe because `listTools` doesn't make backend API calls.

---

## 9. Test Coverage

### Unit Tests: `tests/test_auth_concurrency.py` (21 tests)

| Category | Tests | Verifies |
|----------|-------|----------|
| `_get_auth_from_mcp_request_ctx` | 7 | Header extraction, cookie scrubbing, None guards |
| `_get_session_id_from_mcp_ctx` | 4 | SSE query param, streamable-http header, precedence |
| Concurrent session isolation | 2 | Two sessions with different tokens get own credentials |
| `get_cache_user_suffix` | 3 | MCP fallback, empty context, ContextVar priority |
| `_last_user_auth_bundle` removed | 1 | Variable no longer exists |
| `get_auth_headers_for_console` | 4 | Embedded mode rejection, standalone fallback, copy safety |

### Unit Tests: Existing suites updated

| Suite | Tests | Status |
|-------|-------|--------|
| `tests/` (core + concurrency + environments) | 62 | Pass |
| `safebreach_mcp_data/tests/` | 134 | Pass |
| `safebreach_mcp_config/tests/` | 44 | Pass |
| `safebreach_mcp_playbook/tests/` | 140 | Pass |
| `safebreach_mcp_studio/tests/` | 330 | Pass |
| **Total** | **710** | **All pass** |

### Test Isolation Fix

`test_environments_metadata.py` mutated the module-level `safebreach_envs` dict via
`SAFEBREACH_LOCAL_ENV` re-imports. Other modules holding references to the dict saw
stale entries, breaking E2E tests when run in the same pytest session. Fixed by
snapshotting and restoring the dict in-place (clear + update) in setUp/tearDown.

### E2E Tests (via mcp-proxy repo, both transports)

| Test | User | Tool | Expected | SSE | Streamable |
|------|------|------|----------|-----|------------|
| No auth | none | — | 401 | Pass | Pass |
| Tests_viewer | restricted | get_tests_history | success | Pass | Pass |
| Admin | admin | get_test_simulations | success | Pass | Pass |
| Integrations_reader | restricted | get_test_simulations | 403 | Pass | Pass |
| **Same user +/-** | Tests_viewer | tests → OK, simulations → 403 | **per-endpoint RBAC** | Pass | Pass |
| No auth (POST) | none | — | 401 | Pass | Pass |

---

## 10. Files Changed

| File | Lines | Description |
|------|-------|-------------|
| `safebreach_mcp_core/token_context.py` | +200 | New module: ContextVar, session store, MCP request_ctx helpers, cookie scrubbing |
| `safebreach_mcp_core/secret_utils.py` | +60 | `get_auth_headers_for_console()`, `check_rbac_response()`, `AuthenticationRequired` |
| `safebreach_mcp_core/safebreach_base.py` | +80 | Auth extraction in ASGI wrapper, session store writes, cleanup |
| `safebreach_mcp_core/environments_metadata.py` | +30 | URL priority reorder, OPA bypass fix |
| `safebreach_mcp_data/data_functions.py` | ~50 | 10 tool migrations + cache keys |
| `safebreach_mcp_config/config_functions.py` | ~40 | 7 tool migrations + cache keys |
| `safebreach_mcp_studio/studio_functions.py` | ~60 | 14 tool migrations + cache keys |
| `safebreach_mcp_playbook/playbook_functions.py` | ~10 | 1 tool migration + cache key |
| `safebreach_mcp_core/suggestions.py` | ~5 | 1 migration + cache key |
| `conftest.py` | +62 | Root conftest with session-scoped ContextVar fixture for E2E |
| `tests/test_auth_concurrency.py` | +290 | 21 concurrency safety tests |
| `tests/test_environments_metadata.py` | +15 | Test isolation fix for safebreach_envs dict |

---

## 11. Known Limitations

- **JWT expiry**: JWTs expire after 30 minutes. Long-running MCP sessions may hit 401
  on tool calls after expiry. The client must reconnect with a fresh token.
- **OPA subject `general`**: The `testsummaries` endpoint uses OPA subject `general`
  which all roles have. Test listing cannot be restricted via OPA. Only endpoints with
  specific subjects (`simulationResults`, `testResults`) have per-role enforcement.
- **`AppController` in breach-genie**: The `/apps/:appName/stream` endpoint does not
  yet thread user auth. Deferred until app streaming uses MCP tools.
- **Cache key rotation**: JWTs rotate on re-login, causing cache misses for the same
  user across sessions. This is acceptable — it's safer than sharing caches.
