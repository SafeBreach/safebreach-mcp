# Context — MCP paginated simulation-logs tool (SAF-32099 companion)

| Item | Value |
|------|-------|
| Mode | Create new ticket |
| Project / Type | SAF / Task (relates to SAF-32099) |
| Repo | `safebreach-mcp` (`github.com/SafeBreach/safebreach-mcp`) |
| Related (data side) | SAF-32099 — new `GET /data/v3/.../executionsHistoryResults/{id}/logs` (merged/PR'd in `data`) |
| Solves (context) | SAF-32058 — HELM AI agent overflows LLM token limit on heavy embedded logs |
| Status | Phase 5: Problem Analysis Complete |

## Task Scope
Add a new MCP **data** tool that consumes the new paginated, filterable simulation-logs endpoint
`GET /data/v3/accounts/{accountId}/executionsHistoryResults/{id}/logs` (keyed by simulation id alone — no
runId / ownership check). Params: `page`(1), `pageSize`(300, max 1000), `minLevel`, `levels`(CSV),
`messageContains`, `startTime`, `endTime`, `logType`(LOGS|OUTPUT|ALL, default LOGS), `sortOrder`(asc|desc).
Response: `{ logs, total, page, pageSize, hasMore }`. This gives MCP/AI consumers an incremental, size-bounded
way to read logs instead of the current full-blob fetch.

## Investigation Findings (safebreach-mcp)

### Tool registration pattern
- Tools registered in `SafeBreachDataServer._register_tools()` — `safebreach_mcp_data/data_server.py:50-327`.
- Pattern: `@self.mcp.tool(name=..., annotations=ToolAnnotations(readOnlyHint=True), description="""...""")`
  on an async wrapper `..._tool(...) -> dict` that calls a `sb_*` impl in `data_functions.py`.

### Existing executionsHistoryResults usage (all **v1** today)
- `data_functions.py:1866` — GET `…/v1/…/executionsHistoryResults/{id}?runId={test_id}` → the existing
  **`get_full_simulation_logs`** tool (`data_server.py:296`, impl `data_functions.py:1731`). Returns the full
  ~40KB embedded per-node logs (role-based mapping in `data_types.py:502`). **This is the heavy path** that the
  new endpoint relieves.
- `data_functions.py:571 / 738 / 909 / 2755` — POST `…/v1/…/executionsHistoryResults` (list, for drift/paginated
  simulations).

### HTTP plumbing (reuse as-is)
- `base_url = get_api_base_url(console, 'data')`; `account_id = get_api_account_id(console)`
  (`safebreach_mcp_core/environments_metadata.py:91,143`).
- Auth: `**get_auth_headers_for_console(console)` (`safebreach_mcp_core/secret_utils.py:92`); `check_rbac_response(response)`.
- `requests.get(url, headers=headers, timeout=120)`; 404/401 → `ValueError`.

### Existing logs handling
- `get_full_simulation_logs` (full blob, v1) and `get_test_simulation_details(include_basic_attack_logs=True)`
  (summary-level). No paginated/level-filterable logs tool exists today.

### Where the new tool lives
- `data_functions.py`: `sb_get_simulation_logs()` + `_get_…_from_cache_or_api()` + `_fetch_…_from_api()`.
- `data_types.py`: `get_simulation_logs_mapping()` for `{ logs, total, page, pageSize, hasMore }`.
- `data_server.py`: import + `@self.mcp.tool()` registration (after `get_full_simulation_logs_tool`).
- `tests/test_integration.py`: mock `requests.get` + utils; assert shape/counts/filters (pattern at ~:125-150).
- Cache: `SafeBreachCache(name="simulation_logs", maxsize=…, ttl=600)` (existing logs cache ttl 300).

### Version / config constraints
- No explicit version gating; the tool just builds the `…/v3/…` URL. Console URL via `DATA_URL` /
  `SAFEBREACH_LOCAL_ENV`. Consistent 120s timeout.

## Problem Analysis
- **Problem scope:** MCP can only fetch simulation logs as one large embedded blob (`get_full_simulation_logs`,
  v1). There is no way to page through logs or filter by level/type/time/message — so size-sensitive consumers
  (the HELM agent) pull far more than they need, contributing to the SAF-32058 token overflow.
- **Affected areas:** `safebreach_mcp_data` (new tool + mapping + registration + tests). No change to existing
  tools; `get_full_simulation_logs` stays for full-blob use cases.
- **Dependencies:** the data-side v3 `/logs` endpoint (SAF-32099) must be deployed to the target console for the
  tool to work. The endpoint is keyed by simulation id only (no runId), so the new tool is simpler than
  `get_full_simulation_logs` (which requires test_id).
- **Risks / edge cases:** (1) consoles on a data version without the v3 `/logs` endpoint → 404; tool should give a
  clear error. (2) Old-format simulations whose logs are embedded (not in the logs index) return empty from
  `/logs` — the data result endpoint flags these via `logsEmbedded=true`; document that the full-blob tool is the
  fallback for those. (3) `pageSize` max 1000 enforced server-side → surface 400 cleanly. (4) levels/logType
  casing normalization should match the API contract (UPPER for levels/logType, lower for sortOrder).
- **Not in scope:** the data endpoint itself (SAF-32099, done); modifying `get_full_simulation_logs`; the
  MCP-side migration of other tools off v1.
