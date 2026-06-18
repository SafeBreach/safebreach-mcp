# SAF-32359 — Take outbound auth only from the current request

## Summary

`get_auth_headers_for_console` (`safebreach_mcp_core/secret_utils.py`) could return a
**stale** proxy token for outbound backend calls (ui `/api/data`, `/api/config`,
`/api/orch`), causing those calls to fail with `401 Unauthorized` until the process was
restarted.

This change makes the function resolve auth **only from the current MCP request** — the
live `request_ctx` headers that SIMP forwards — instead of consulting a cached source that
can go stale.

## Why it is needed

The function previously resolved auth headers from three sources, in priority order:

1. the `_user_auth_artifacts` ContextVar
2. the live MCP request context (`_get_auth_from_mcp_request_ctx`)
3. the `_session_auth_artifacts` session store

The ContextVar (source 1) is set on the ASGI middleware task but does **not** propagate to
the tool-handler task under streamable-http, so it can hold a token captured from an
earlier request. Because source 1 was consulted first and only checked whether a token was
*present* (not whether it was still valid), a stale token there short-circuited the lookup
and was sent to the backend — producing the `401` once it expired (~15 min after a
(re)start), even though the current request carried a fresh token all along.

## The change

`get_auth_headers_for_console` now uses a single source — the current request:

```python
def get_auth_headers_for_console(console):
    bundle = _get_auth_from_mcp_request_ctx()   # the live request's forwarded headers
    if bundle:
        return dict(bundle)
    # no user auth on this request:
    #   embedded mode  -> raise AuthenticationRequired
    #   standalone     -> fall back to env-var API key
```

Removed:

- the `_user_auth_artifacts` ContextVar read (source 1),
- the `_session_auth_artifacts` session-store read (source 3),
- the `_needs_fresh_token` JWT-expiry helper (no longer needed — the request token is always
  the current one).

The per-request token is fresh by construction, so the expired-token failure mode cannot
occur. Embedded-mode rejection and standalone env-key fallback are unchanged.

## Tests

- Unit tests inject auth via the `_user_auth_artifacts` ContextVar. A single autouse fixture
  in `conftest.py` (`route_auth_ctxvar_to_request_ctx`) routes that injected value to the
  request reader when the ContextVar is set, falling back to the real reader otherwise — so
  existing injections keep working without per-test edits.
- The obsolete `test_session_store_fallback_isolates_sessions` (exercised the removed
  source 3) is deleted.
- Full non-e2e suite passes (pre-existing `test_disable_filtering` failures are unrelated).

## Scope

- File: `safebreach_mcp_core/secret_utils.py` (+ test harness `conftest.py`, one removed test).
- The `_user_auth_artifacts` ContextVar still exists for the rate limiter and cache-key
  scoping; fully removing it and the session store / SSE machinery is tracked in SAF-32387.
- No changes to breach-genie, mcp-proxy, ui, or the backend.
