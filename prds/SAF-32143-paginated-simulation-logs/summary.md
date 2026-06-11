# Ticket Summary (proposed) — MCP paginated simulation-logs tool

- **Project / Type:** SAF / Task
- **Links:** relates to **SAF-32099** (data-side v3 `/logs` endpoint); context: SAF-32058
- **Repo / branch (on create):** `safebreach-mcp` / `feature/SAF-XXXXX-mcp-paginated-simulation-logs`

## Proposed Title
Add MCP tool for paginated/filterable simulation logs (consume data v3 `/logs` endpoint)

## Description
The `data` service added (SAF-32099) a new endpoint
`GET /data/v3/accounts/{accountId}/executionsHistoryResults/{id}/logs` — structured per-line simulation logs,
**keyed by simulation id alone** (no runId / ownership check), with offset pagination and level/type/time/message
filtering, returning `{ logs, total, page, pageSize, hasMore }`.

Add a new MCP **data** tool that consumes this endpoint. Today the only logs tool, `get_full_simulation_logs`
(`data_functions.py:1731`, v1 `…/{id}?runId=`), returns the entire ~40KB embedded blob — the heavy pattern that
contributed to the SAF-32058 LLM token overflow. The new tool lets MCP/AI consumers fetch logs incrementally and
filtered, keeping payloads (and token counts) bounded. `get_full_simulation_logs` remains for full-blob use cases
and for old-format simulations whose logs are still embedded.

## Acceptance Criteria
1. New read-only MCP tool (e.g. `get_simulation_logs`) registered in `data_server.py` that calls
   `GET /api/data/v3/accounts/{accountId}/executionsHistoryResults/{id}/logs`.
2. Params: `simulation_id` (required), `page`, `pageSize`, `minLevel`, `levels`, `messageContains`, `startTime`,
   `endTime`, `logType` (default `LOGS`), `sortOrder` (default `asc`), `console`. **No `test_id`/`runId`.**
3. Param normalization matches the API contract: `levels` CSV → trimmed UPPERCASE, `minLevel`/`logType` UPPER,
   `sortOrder` lower; `page`/`pageSize` coerced to int.
4. Returns `{ logs, total, page, pageSize, hasMore }` via a `get_simulation_logs_mapping()` in `data_types.py`.
5. Reuses existing plumbing: `get_api_base_url`/`get_api_account_id`/`get_auth_headers_for_console`/
   `check_rbac_response`; 120s timeout; clean errors for 404 (incl. "endpoint not available / no logs in index")
   and 401.
6. Caching consistent with existing logs cache (`SafeBreachCache`, ttl ~600s).
7. Tool description steers the model: use this for targeted/large logs; use `get_full_simulation_logs` for the
   full embedded blob / old-format sims (where the data result endpoint reports `logsEmbedded=true`).
8. Unit + integration tests (mirror `tests/test_integration.py`): pagination, each filter, casing normalization,
   cache hit/miss, 404/401 handling.
9. `CHANGELOG.md` / docs updated.

## Out of Scope
- The data-side endpoint (SAF-32099 — done).
- Modifying `get_full_simulation_logs` or migrating other MCP tools off v1.

## Notes / Risks
- Requires the target console's `data` service to include the SAF-32099 v3 `/logs` endpoint (else 404).
- Old-format sims have embedded logs (not in the logs index) → `/logs` returns empty; the full-blob tool is the
  fallback (data result endpoint signals this via `logsEmbedded=true`).
