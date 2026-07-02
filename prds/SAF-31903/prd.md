# PRD: HELM "Too many requests" crash — per-JWT concurrency limiting (SAF-31903)

## 1. Problem

With 3-4 users interacting with HELM on one console, the chat freezes. The client
surfaces `Too Many Requests: Concurrency limit of 5 exceeded` from
`StreamableHTTPClientTransport.send`. A single user rarely triggers it; concurrent
users reliably do.

## 2. Root cause

The MCP server limits concurrency with an `asyncio.Semaphore(_concurrency_limit)`
per **`mcp-session-id`** (`safebreach_base.py`). The intent was one limit per user —
but breach-genie holds a **single** `MCPClient` (`McpClientService.ts`), so there is
**one `mcp-session-id` per MCP server shared across every user**; per-user auth is
injected per-request by `authFetch` as an `x-token` header. So on the wire it's one
shared session id with a different JWT per user, and the "per-session" limit of N is
really **N concurrent total for the whole console** — a few data-heavy HELM turns from
different users blow past it and the client turns the 429 into a stuck chat.

Per-JWT identity already exists server-side and is used by the rate limiter
(`get_caller_identity` = hash of `x-apitoken > x-token > cookie`). The concurrency
limiter simply wasn't using it — it keyed on the shared transport session instead.

## 3. Fix

Key the concurrency semaphore on **caller identity (the JWT), not the transport
session** — the same axis the rate limiter already trusts, and which `authFetch`
guarantees is present on every request.

- New `_concurrency_key(bundle, session_id)`: returns `jwt:<sha256(token)[:16]>` when a
  token is present (priority `x-apitoken > x-token > cookie`, mirroring
  `get_caller_identity`); falls back to the raw `session_id`; then `None`.
- Both acquire paths (streamable-http `/mcp` and SSE `/messages/`) bucket the semaphore
  by this key. Each user gets an independent `Semaphore(_concurrency_limit)`.
- The `session_id` fallback keeps every no-token path (and the SSE session lifecycle)
  behaving exactly as before — only token-bearing requests (all of breach-genie's)
  switch to per-JWT.

The middleware already extracts the auth bundle (`extract_auth_bundle(scope)`), so the
token is in hand at the point the semaphore is keyed — this is also more robust than
the `mcp-session-id` ContextVar path (SAF-28585) because it reads from the request
scope, not a ContextVar that doesn't propagate across tasks.

## 4. Files changed

- `safebreach_mcp_core/safebreach_base.py` — `_concurrency_key` helper; both acquire
  paths key on it; the 429 response deduped into `_send_concurrency_429`.
- `tests/test_concurrency_limiter.py` — 3 new tests (see below).

## 5. Tests

- `test_key_prefers_jwt_and_is_session_independent` — token → `jwt:` key, stable across
  session ids; different tokens differ; no token → `session_id` fallback; neither → None.
- `test_two_jwts_have_independent_limits` — JWT A's bucket saturated → A gets 429, while
  JWT B on the **same** `mcp-session-id` still runs.
- `test_same_jwt_shares_bucket_across_sessions` — same token, **different** session id →
  same bucket → 429 (proves the JWT, not the session, is the axis).

All existing concurrency + e2e tests unchanged and green (no-token paths fall back to
`session_id`).

## 6. Out of scope / follow-up

- **Wait-for-slot (queue on contention)** instead of instant 429 — a separable
  robustness improvement for a single user's own > limit burst (and low-limit init
  bursts). Deferred to its own change.
- **Max queue depth** — only relevant if the wait-for-slot change lands.

## 7. Verification

- Unit: the 3 tests above.
- Live (pentest01): two `x-token`s over one `mcp-session-id` register two distinct
  `jwt:` concurrency buckets in the server log — grep `New concurrency bucket: jwt:`;
  one bucket per active user is the production signal that per-JWT limiting is working.
