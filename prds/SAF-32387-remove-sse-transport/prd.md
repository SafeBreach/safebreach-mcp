# SAF-32387 — Remove SSE transport and session-store code (streamable-http only)

- **Type:** Tech-debt / cleanup (follow-up to SAF-32359)
- **JIRA:** https://safebreach.atlassian.net/browse/SAF-32387
- **Repo:** safebreach-mcp only. No changes to mcp-proxy, breach-genie, ui, or the backend.

## 1. Where we are today

safebreach-mcp still ships **two transports**, selected by `SAFEBREACH_MCP_TRANSPORT`:

| Value | FastMCP app | Endpoints | Status |
|---|---|---|---|
| `sse` (**code default**) | `sse_app()` | `GET /sse` + `POST /messages/?session_id=` | Legacy. Not used by any deployment. |
| `streamable-http` | `streamable_http_app()` | single `POST /mcp` (or `$SAFEBREACH_MCP_BASE_URL`) | What actually runs. |

Streamable-http was added as opt-in in SAF-28480 (default stayed `sse` for backward compatibility).
Since then every real launcher moved to streamable-http:

- **mcp-proxy** (SIMP, the only production launcher) pins `SAFEBREACH_MCP_TRANSPORT='streamable-http'`
  as a constant in `src/services/serverEnv.ts` and deliberately does not read the env var
  (scope decision 2026-06-11: "the legacy SSE transport is retired"). Its routes are
  `/api/mcp/{serverType}` — no `/sse` route exists.
- **breach-genie** talks to the proxy; its client code has no `SSEClientTransport` usage.
- **Local dev** (`.vscode/launch.json`, `.vscode/set_env.sh`) sets `streamable-http`.
- Runtime confirmed: `New concurrency bucket` / streamable-http logs in `safebreach_base.py`.

So the SSE code path is dead in every environment we run, but it still carries a lot of
machinery that exists **only** to make SSE work, and that machinery has already caused a
production bug (SAF-32359: stale token from a ContextVar that does not propagate under
streamable-http → `401` on outbound calls).

### 1.1 What SSE dragged in (and why it is now debt)

SSE splits one logical session across **two HTTP requests handled on different asyncio tasks**
(the long-lived `GET /sse` and each `POST /messages/`). Nothing set on the GET task is visible
on the POST task, so the code grew these workarounds:

1. **`_user_auth_artifacts` ContextVar** (`token_context.py`) — set by the ASGI middleware per
   request so tool code could read the caller's auth. Under streamable-http it does not
   propagate to the tool-handler task either, so it can hold a value from an *earlier* request.
   This is the exact stale-token bug fixed in SAF-32359 for the auth path. It is still read by
   the **rate limiter** (`rate_limiter.py:156`) and **cache-key scoping**
   (`get_cache_user_suffix`, `token_context.py:166`) — both are exposed to the same staleness.
2. **`_session_auth_artifacts` session store** + `_SESSION_ARTIFACTS_TTL` +
   `cleanup_stale_artifacts()` — a process-wide dict of `session_id → auth bundle` so a
   `POST /messages/` that arrived without headers could recover the user's auth from the
   `GET /sse` that opened the session. Streamable-http carries headers on every request, so
   the store is never read for it; it is only *written* (dead data, timed eviction every 10 min).
3. **`_get_session_id_from_mcp_ctx()`** — reads `query_params['session_id']` (SSE) with a
   fallback to the `mcp-session-id` header (streamable-http). Only the header branch is live.
4. **SSE session bookkeeping in `_create_concurrency_limited_app`** — `_mcp_session_id`
   ContextVar, middleware-generated UUID, `cleanup_send` that regex-scrapes the SSE body for the
   real `session_id` and *migrates* the semaphore + auth entry to the new key, and the
   `/messages/` branch with its ContextVar-then-query-string lookup (SAF-28585).
5. **Test bridge** — SAF-32359 left an autouse `route_auth_ctxvar_to_request_ctx` fixture in
   `conftest.py` that monkeypatches the request reader to also honour the ContextVar, so ~70
   existing `_user_auth_artifacts.set(...)` test injections kept working. That is a shim, not
   the target state.

## 2. Goal

safebreach-mcp serves **streamable-http only**. Everything that existed solely for SSE is
deleted, and no runtime behaviour (auth, rate limiting, cache scoping) depends on a ContextVar
that may be stale. Tests inject auth the way production delivers it: through the MCP request
context.

## 3. Non-goals

- No new features, no behaviour change for streamable-http clients.
- No change to the concurrency limiter's per-JWT bucketing semantics (SAF-29871/SAF-28585
  behaviour stays; only the SSE-specific session plumbing goes).
- No changes in other repos. `tools/mcps/bridge/staging_deployment/deploy_safebreach_mcp.py`
  (a separate tooling repo) still prints `/sse` URLs; flagged for a follow-up, not touched here.

## 4. Prerequisite (verified)

No consumer depends on `/sse` or `/messages/`:

- mcp-proxy pins streamable-http and routes only `/api/mcp/*` (see §1).
- breach-genie / breach-genie-copilot / breach-genie-quickrun source has no SSE client
  transport; the `/sse` hits there are in old unit-test fixtures only.
- ui `mcp.proxy` tests reference `/sse` as generic proxy fixtures, not as a live path.

## 5. Design decision: fate of the `_user_auth_artifacts` ContextVar

**Decision: remove it entirely.** Migrate its two remaining readers to
`_get_auth_from_mcp_request_ctx()` (the same single-source rule SAF-32359 applied to auth).

Why not keep it "only for those two consumers":
- It is set on the middleware task and read on the tool-handler task; under streamable-http
  that is the same non-propagation that produced the SAF-32359 bug. A rate-limit identity or a
  cache key computed from a stale bundle is a *cross-user* correctness issue (user A hitting
  user B's cache entry or rate bucket), which is worse than the auth 401 was.
- With auth already request-only, a second, weaker source for the *same* bundle is pure
  inconsistency.
- The rate limiter and cache suffix already fall back to `_get_auth_from_mcp_request_ctx()`
  today; removing the ContextVar read just deletes the first (unsafe) branch.

Consequence: E2E tests (which call tool functions directly, outside an ASGI request) can no
longer inject via the ContextVar. They will inject by setting the MCP SDK `request_ctx` with a
fake request carrying the auth headers (a small helper in `conftest.py`, see §6.4).

## 6. Scope of changes

### 6.1 `safebreach_mcp_core/safebreach_base.py`

| Area | Change | Why |
|---|---|---|
| `run_server()` | Delete transport env-var resolution and the `else` SSE branch (`sse_app()`, Starlette `Mount`, `/sse` logs). Always build `streamable_http_app()` with `endpoint_path = base_url or '/mcp'`. Update docstring. | Single transport. |
| `_create_concurrency_limited_app(original_app, transport, endpoint_path)` | Drop `transport` param. Delete the `path.endswith('/sse')` block (UUID session, `_mcp_session_id.set`, `cleanup_send`, semaphore/auth migration) and the `/messages/` block. Keep only the streamable-http block (`mcp-session-id` header → `_concurrency_key` → semaphore), minus the `_session_auth_artifacts[...] = ...` write. Delete the `_user_auth_artifacts.set(bundle)` at the top. | The middleware no longer needs to carry auth anywhere; tool code reads the live request. |
| Module globals | Delete `_mcp_session_id` ContextVar (only the SSE branch used it). Keep `_session_semaphores`, `_concurrency_limit`, `_SEMAPHORE_MAX_AGE`, `_concurrency_key`, `_send_concurrency_429`. | Semaphore buckets are still needed for per-JWT limiting. |
| `_cleanup_stale_semaphores()` | Remove the `cleanup_stale_artifacts(...)` call and the "SSE semaphore" wording. | Store is gone. |
| Imports from `token_context` | Reduce to `extract_auth_bundle` (still used for `_concurrency_key`) and `mask_artifacts` if still referenced. | Dead imports. |
| `_create_authenticated_asgi_app()` OAuth discovery | Replace `/.well-known/oauth-authorization-server/sse` with the streamable path and `"resource": ...{base_path}/sse` with the `/mcp` endpoint. | Discovery metadata must point at an endpoint that exists. |

### 6.2 `safebreach_mcp_core/token_context.py`

Delete: `_user_auth_artifacts`, `_session_auth_artifacts`, `_SESSION_ARTIFACTS_TTL`,
`cleanup_stale_artifacts()`, the `query_params` branch of `_get_session_id_from_mcp_ctx()`
(keep the `mcp-session-id` header read — the rate limiter's session fallback still uses it),
unused `time` import. `get_cache_user_suffix()` reads only `_get_auth_from_mcp_request_ctx()`.
Update the module docstring (no more "session store for SSE transport resilience").

### 6.3 `safebreach_mcp_core/rate_limiter.py`

`get_caller_identity()` reads only `_get_auth_from_mcp_request_ctx()`; drop the
`_user_auth_artifacts` import and read.

### 6.4 Tests

- **Delete** SSE-only tests: `tests/test_concurrency_limiter.py` SSE/`/messages/` cases
  (session creation, migration, cleanup-on-disconnect, ContextVar-across-tasks, query-string
  lookup), `tests/test_auth_concurrency.py::TestGetSessionIdFromMcpCtx` SSE cases and the
  `_session_auth_artifacts` cleanup fixture. In `test_memory_stress.py` §4 keep the tests
  (they exercise `_session_semaphores`) and only rename the "SSE semaphore" wording.
- **Rewrite** `tests/test_e2e_concurrency_limiter.py` (opens a raw-TCP `/sse` connection) to
  drive the limiter through `POST /mcp` with an `mcp-session-id` header, or fold it into the
  existing streamable-http limiter tests and delete the file. Decision at implementation
  time based on what the existing streamable-http tests already cover.
- **Migrate** the ~70 `_user_auth_artifacts.set({...})` injections
  (studio_functions 48, data_functions 8, test_auth_concurrency 5, config 4, playbook 1,
  suggestions 1, user_lookup 1, rate_limiting 1, data e2e 1) to a shared helper /
  fixture that sets the MCP SDK `request_ctx` with a fake request whose `.headers` carries the
  bundle — same shape `tests/test_auth_concurrency.py::_mock_request_ctx` already uses.
- **Remove** the `route_auth_ctxvar_to_request_ctx` autouse bridge from `conftest.py`; rewrite
  `set_e2e_auth_context`, `e2e_auth_for_console`, and `cancel_e2e_leftovers` to use the new
  request-ctx helper instead of the ContextVar.
- Keep/extend streamable-http limiter tests (`test_concurrency_limiter.py` bottom section) as
  the regression net for the middleware.

### 6.5 `start_all_servers.py`

Advertise `http://…:{port}/mcp` (or `$SAFEBREACH_MCP_BASE_URL`) instead of `/sse` in the
startup log lines.

### 6.6 Docs

- `CLAUDE.md`: remove "default is SSE" / `SAFEBREACH_MCP_TRANSPORT` examples and the
  env-var table row; replace `/sse` in client config examples with `/mcp`.
- `README.md`, `DESIGN.md`, `SECURITY_GUIDELINES.md`, `TEAM_WORKFLOW.md`: same `/sse` → `/mcp`
  replacement in client configs and curl examples; drop the "SSE Transport" feature bullet;
  fix the OAuth discovery path line.
- `CHANGELOG.md`: new **Removed** entry under `Unreleased` (see §8).
- `docs/integration.md` describes the ui-server's SSE proxying of *streaming responses*
  (streamable-http still streams via SSE-formatted bodies) — leave as is.

### 6.7 Env var `SAFEBREACH_MCP_TRANSPORT`

Stop reading it. mcp-proxy still sets it to `streamable-http`; an ignored env var is harmless
and lets the proxy drop it on its own schedule. Log nothing about it.

## 7. Implementation phases

1. **Runtime cleanup** — `safebreach_base.py`, `token_context.py`, `rate_limiter.py`,
   `start_all_servers.py`. Run the non-e2e suite; expect failures only in SSE tests and in
   tests relying on the ContextVar bridge.
2. **Test migration** — add the request-ctx auth helper, migrate injections file by file,
   delete SSE tests, remove the conftest bridge, rewrite/delete the SSE e2e limiter test.
   Suite green.
3. **Docs + changelog.**
4. **Manual verification** — `uv run start_all_servers.py`, confirm only `/mcp` is served
   (`curl -i localhost:8001/sse` → 404), run a tool call through mcp-proxy locally, confirm
   rate limiting and user-scoped cache keys still log a per-user identity.

## 8. Versioning / release

No version bump in this PR (decided 2026-09-03). Add a `### Removed` entry under an
`Unreleased` heading in `CHANGELOG.md` naming `/sse`, `/messages/`, and
`SAFEBREACH_MCP_TRANSPORT`; the release skill picks the version when it ships.

## 9. Acceptance criteria (from JIRA, made testable)

- [ ] `GET /sse` and `POST /messages/` return 404 on every server; `/mcp` (or base URL) works.
- [ ] `grep -rn "_session_auth_artifacts\|_user_auth_artifacts\|cleanup_stale_artifacts\|sse_app\|SAFEBREACH_MCP_TRANSPORT"` over non-`prds/` code returns nothing.
- [ ] `get_caller_identity()` and `get_cache_user_suffix()` derive identity only from the live MCP request.
- [ ] `conftest.py` has no `route_auth_ctxvar_to_request_ctx`; no test calls `_user_auth_artifacts.set`.
- [ ] Non-e2e suite green; e2e suite green against a private env (per `E2E_TESTING.md`).
- [ ] Docs contain no `/sse` client-config examples.

## 10. Risks

| Risk | Mitigation |
|---|---|
| An unknown external client still uses `/sse` | §4 audit found none; the changelog entry makes the removal explicit. |
| Rate-limit identity regresses to `anonymous` when `request_ctx` is unavailable | That path already exists today as the fallback chain; tests for `get_caller_identity` cover header → session → anonymous. |
| E2E tests lose auth once the ContextVar goes | Request-ctx fixture in `conftest.py` replaces it 1:1 (session-scoped, same env-var token resolution). |
| Large test diff hides a real regression | Phase 1 and Phase 2 are separate commits; Phase 1 must only break SSE/bridge-dependent tests. |
