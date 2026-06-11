# Context — MCP paginated/filterable simulation-logs tools (SAF-32099 companion)

| Item | Value |
|------|-------|
| Ticket | SAF-32143 — `safebreach-mcp` \| Add MCP tool(s) for paginated/filterable simulation logs |
| Project / Type | SAF / Task (companion to SAF-32099, context: SAF-32058 / SB-36091) |
| Repo / branch | `safebreach-mcp` / `feature/SAF-32143-paginated-simulation-logs` |
| Related (data side) | SAF-32099 — new `GET /data/v3/accounts/{accountId}/simulationLogs` (branch `feature/SAF-32099-paginate-simulation-logs-api`) |
| Solves (context) | SAF-32058 — HELM AI agent overflows the LLM token limit on the heavy embedded-logs blob |
| Status | Phase 5: Brainstorm |

## ⚠️ Contract correction (ground truth from the data branch)

The SAF-32143 description **and** the earlier `preparing-ticket` notes describe a per-simulation endpoint
`GET /data/v3/.../executionsHistoryResults/{id}/logs` keyed by a single `simulation_id` in the path. **That endpoint
does not exist.** The data branch (`feature/SAF-32099-paginate-simulation-logs-api`) consolidated to a single
collection endpoint (commit `ea2f0cb5d` "consolidate to a single /simulationLogs endpoint with optional jobIds").
The real contract — verified in code, not docs — is below and is the source of truth for this PRD.

## Real data API contract — `GET /data/v3/accounts/{accountId}/simulationLogs`

Source: `data` repo branch `feature/SAF-32099-paginate-simulation-logs-api`
- OpenAPI: `src/api/dashboardapi.json:2218-2341` (params), `:3687-3702` (response schema)
- Param normalization: `src/dashboardApi/api/executionsHistoryApi.js:34-69` (`buildSimulationLogOptions`)
- Handler: `executionsHistoryApi.js:71-78` → controller `executionsHistoryController.js:266-275`
- ES query / DAO: `src/common/dal/simulationLogsDao.js:24-106` (index `executions_simulations_logs`)
- PRD §5 (consumer contract): `data` repo `prds/feature-SAF-32099-paginate-simulation-logs-api/prd.md`

### Query parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `jobIds` | string[] (`collectionFormat: pipes`, e.g. `a\|b`) | omitted = **all** sims | The simulation id(s). Single sim = `jobIds=<id>`. Trimmed, **no** case change. **No `runId`/ownership check** — `jobId` is globally unique. |
| `page` | int | `1` | 1-based. `from = (page-1)*pageSize`. Coerced via `Number()`. |
| `pageSize` | int | `500` | **max 1000** (OpenAPI validator → HTTP 400 if exceeded; no app-side clamp). |
| `minLevel` | string | `INFO` | enum `DEBUG\|INFO\|WARNING\|ERROR`. Returns that level **and above** → DEBUG excluded by default. UPPERCASED server-side. |
| `levels` | string[] (pipes) | — | Explicit set; **overrides `minLevel`** when present. Each element trimmed + UPPERCASED. |
| `messageContains` | string | — | Case-insensitive substring (ES `*term*`). |
| `startTime` / `endTime` | string | — | ISO-8601 or epoch ms; inclusive range on `timestamp`. |
| `logType` | string | `LOGS` | enum `LOGS\|OUTPUT\|ALL`. UPPERCASED. `ALL` = no logType filter. |
| `sortOrder` | string | `asc` | enum `asc\|desc`. lowercased. Sort key = `timestamp`. |

### Response shape (200)

```jsonc
{
  "logs": [
    { "timestamp": "...", "level": "ERROR", "logType": "LOGS", "logger": "simulator",
      "sourceFile": "runner.py", "line": "212", "message": "...", "pid": "8123",
      "jobId": "4915971", "planRunId": "pr-77" }
  ],
  "total": 1234,        // total matches across all pages
  "page": 1,            // echoes request
  "pageSize": 500,      // echoes effective size
  "hasMore": true       // page*pageSize < total
}
```

### Errors
- **400** — bad enum or `pageSize > 1000` (OpenAPI validator, before app code).
- **401** — missing/invalid auth.
- **404** — endpoint not present on the target console's data version (old data build) → must surface a clear "endpoint
  not available / upgrade data service" message.
- No logs found (endpoint present) → **200** with `logs: []`, `total: 0`, `hasMore: false` (not a 404).

## Design decision — TWO tools (per Amir, 2026-06-11)

Split the single-sim "investigation" use case from the cross-sim "search" use case so each tool's signature and
description steer the model cleanly:

1. **`get_paginated_simulation_logs`** — single-simulation investigation.
   - Required `simulation_id` (str) → sent as `jobIds=<simulation_id>`.
   - Plus all filters: `page`, `page_size`, `min_level`, `levels`, `message_contains`, `start_time`, `end_time`,
     `log_type`, `sort_order`, `console`.
   - Closest to the ticket's AC#2 (single id, no `test_id`/`runId`). The primary SAF-32058 fix path.

2. **`search_simulation_logs`** — cross-/multi-simulation search (name TBD; alt: `get_cross_simulation_logs`).
   - Optional `simulation_ids` (**pipe-delimited** str `a|b`, matching the query-param style) → `jobIds=a|b`;
     **omit = search all sims**. `levels` is pipe-delimited too. No CSV at the MCP layer.
   - Same filter set. Description steers the model to investigative/forensic cross-sim queries (e.g. "all ERRORs in
     the last hour across every simulation").

Both are read-only (`readOnlyHint=True`), share one fetch/cache/mapping core, and differ only in how `jobIds` is built.
`get_full_simulation_logs` stays untouched as the full-blob / old-format (`logsEmbedded=true`) fallback.

## Investigation Findings (safebreach-mcp)

### Tool registration pattern
- Tools registered in `SafeBreachDataServer._register_tools()` — `safebreach_mcp_data/data_server.py` (logs tool at `:296-326`).
- Pattern: `@self.mcp.tool(name=..., annotations=ToolAnnotations(readOnlyHint=True), description="""...""")` on an async
  `..._tool(...) -> dict` wrapper that calls a `sb_*` impl in `data_functions.py`. Import the impl at top of `data_server.py`.

### Existing logs tool (the heavy path to relieve)
- `get_full_simulation_logs` → `sb_get_full_simulation_logs` (`data_functions.py:1731`), three-layer:
  `sb_*` → `_get_*_from_cache_or_api` (`:1795`) → `_fetch_*_from_api` (`:1841`).
- URL (v1): `f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults/{simulation_id}?runId={test_id}"`
  (`:1866`). `requests.get(url, headers, timeout=120)`. 404/401 → `ValueError`; else `check_rbac_response`.
- Cache: `full_simulation_logs_cache = SafeBreachCache(name="full_simulation_logs", maxsize=2, ttl=300)` (`:1728`).
  Cache key: `f"full_simulation_logs_{console}_{simulation_id}_{test_id}{get_cache_user_suffix()}"`. **Transform-then-cache.**
- Mapping `get_full_simulation_logs_mapping()` (`data_types.py:502`) — role-based (target/attacker) blob; not reused here.

### HTTP plumbing (reuse as-is)
- `get_api_base_url(console, 'data')`, `get_api_account_id(console)` — `safebreach_mcp_core/environments_metadata.py:91,143`.
- `get_auth_headers_for_console(console)` — `safebreach_mcp_core/secret_utils.py:92`; `check_rbac_response(response)` — `:77`.
- `is_caching_enabled("data")` + `get_cache_user_suffix()` (`safebreach_mcp_core/token_context.py`) gate/scope the cache.
- `SafeBreachCache(name, maxsize, ttl)` wraps `cachetools.TTLCache`, thread-safe (`safebreach_mcp_core/safebreach_cache.py:22`).

### Where the new code lives
- `data_functions.py`: shared `_fetch_simulation_logs_from_api(job_ids, filters…, console)` (`job_ids` = pipe-joined string or None) + `_..._from_cache_or_api`
  + two thin public `sb_get_paginated_simulation_logs(...)` / `sb_search_simulation_logs(...)` entry points that build `jobIds`.
- `data_types.py`: `get_simulation_logs_mapping(api_response)` → passthrough/normalized `{logs, total, page, pageSize, hasMore}`
  (snake_case the envelope keys to match repo style; keep per-line fields as the API returns them).
- `data_server.py`: import + two `@self.mcp.tool()` registrations after `get_full_simulation_logs_tool`.
- Tests: `safebreach_mcp_data/tests/test_data_functions.py` (unit), `test_data_types.py` (mapping),
  `tests/test_integration.py` (HTTP-mocked end-to-end). Patterns: `@patch('...requests.get')`, `Mock(status_code=…, json=…)`.
- Cache: `simulation_logs_cache = SafeBreachCache(name="simulation_logs", maxsize=3, ttl=600)` — cache key must include
  console + jobIds + every filter + page + user suffix.
- `CHANGELOG.md` (Keep-a-Changelog, "Added") and `CLAUDE.md` MCP-tools list updated.

## Problem Analysis
- **Problem:** MCP can only fetch simulation logs as one ~40KB embedded blob (`get_full_simulation_logs`, v1). No way to
  page or filter by level/type/time/message — size-sensitive consumers (HELM agent) pull far more than needed,
  contributing to the SAF-32058 token overflow (`1773108 tokens > 1000000 maximum`).
- **Affected:** `safebreach_mcp_data` only (two new tools + shared fetch/mapping + registration + tests + docs). No change
  to existing tools.
- **Dependency:** target console's data service must include the SAF-32099 `/simulationLogs` endpoint, else 404.
- **Edge cases:** (1) old data build → 404, clear message; (2) old-format sims (embedded logs, not in the index) → `/logs`
  empty, point to `get_full_simulation_logs`; (3) `pageSize > 1000` → surface 400 cleanly (optional client-side guard);
  (4) casing normalization (levels/logType UPPER, sortOrder lower) — mirror server, but server also normalizes;
  (5) `min_level` default INFO means DEBUG hidden unless asked — document in tool description.
- **Out of scope:** the data endpoint (SAF-32099, done); modifying `get_full_simulation_logs`; migrating other tools off v1.
