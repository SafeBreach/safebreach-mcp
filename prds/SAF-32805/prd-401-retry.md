# PRD: bounded 401 retry-with-backoff on security-control-events — SAF-32805 (criterion 3)

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | Retry transient 401s on the SafeBreach API call path; raise a typed error on persistent failure instead of abandoning verification |
| **JIRA** | SAF-32805 (acceptance criterion 3; criteria 1 & 2 are in PR #68) |
| **Component** | `safebreach_mcp_data` (Data Server) |
| **Branch** | `feature/SAF-32805-401-retry` |

## 2. Problem

Security-control-event queries (`get_security_controls_events`) hit transient HTTP 401s with no retry. The fetch propagated the 401 as an exception, so the agent abandoned verification mid-analysis (SB-36136) — a transient auth blip read as "couldn't check," nudging false conclusions.

## 3. Root cause / why retry (not refresh)

Auth headers come from the **live per-request user credentials** (`get_auth_headers_for_console` → MCP `request_ctx`) — there is **no server-managed token to refresh**. A 401 here is typically transient (RBAC-gateway propagation / auth race). The only safe recovery is re-issuing the same request after a short backoff; a persistent 401 means genuinely-rejected creds.

## 4. Solution

A local helper `_get_with_auth_retry(url, headers, timeout)` in `data_functions.py`, used by the security-control-events fetch:
- On HTTP 401: retry up to `_AUTH_RETRY_ATTEMPTS` (default 3, env `SAFEBREACH_MCP_AUTH_RETRY_ATTEMPTS`) with exponential backoff (`_AUTH_RETRY_BACKOFF_SEC`, default 0.5s).
- On persistent 401: raise `TransientAuthError` — an explicit typed error, never a silent/empty result.
- Non-401 responses: unchanged — `check_rbac_response` (403 RBAC hint + `raise_for_status`).

Kept as a local helper calling `requests.get` (rather than a new shared module) to stay focused on the incident path and avoid disturbing the ~20 other call sites / their tests. Can be extracted to `safebreach_mcp_core` if a second call path needs it.

## 5. Tests

- `test_get_with_auth_retry_recovers_from_transient_401` — 401→200 retries and returns 200.
- `test_get_with_auth_retry_persistent_401_raises_typed` — all-401 raises `TransientAuthError` after N attempts.
- Full data suite green (477); existing security-control-events tests unaffected.

## 6. Acceptance criteria (SAF-32805)

- ✅ Transient 401s auto-recover (retry-with-backoff).
- ✅ Persistent 401s raise an explicit typed error, never silent-empty.
- (Criteria 1 & 2 — filter correctness + empty-match guard — delivered in PR #68.)
