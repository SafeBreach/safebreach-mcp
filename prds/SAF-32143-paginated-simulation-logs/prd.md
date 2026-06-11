# PRD — MCP paginated/filterable simulation-logs tools (SAF-32143)

| Field | Value |
|-------|-------|
| Ticket | [SAF-32143](https://safebreach.atlassian.net/browse/SAF-32143) — `safebreach-mcp` \| Add MCP tool(s) for paginated/filterable simulation logs |
| Type | Task |
| Repo / branch | `safebreach-mcp` / `feature/SAF-32143-paginated-simulation-logs` |
| Companion | [SAF-32099](https://safebreach.atlassian.net/browse/SAF-32099) (data v3 `/simulationLogs`, branch `feature/SAF-32099-paginate-simulation-logs-api`) |
| Context bug | [SAF-32058](https://safebreach.atlassian.net/browse/SAF-32058) / support SB-36091 (HELM LLM token overflow) |
| Status | Draft for review |

> **Authoritative contract note.** The SAF-32143 ticket text describes a per-sim path
> `…/executionsHistoryResults/{id}/logs`. That endpoint was **not** what shipped. The data side consolidated to a single
> collection endpoint `GET /data/v3/accounts/{accountId}/simulationLogs` with an optional pipe-delimited `jobIds` param.
> This PRD targets the real endpoint (verified in the SAF-32099 branch code — see `context.md`).

## 1. Problem & Goal

AI agents (HELM) retrieving simulation logs through `safebreach-mcp` blow the LLM token limit
(`prompt is too long: 1773108 tokens > 1000000 maximum`, SAF-32058) because the only logs tool today,
`get_full_simulation_logs`, returns the entire ~40KB embedded per-node blob in one shot. There is no way to page through
logs or filter them by level / type / time / message.

The data service (SAF-32099) now exposes a structured, paginated, filterable logs endpoint backed by the
`executions_simulations_logs` ES index. **Goal:** add read-only MCP data tools that consume it so AI consumers fetch logs
incrementally and filtered (token-bounded), while `get_full_simulation_logs` remains the full-blob / old-format fallback.

### Success criteria
- An AI consumer can fetch a single simulation's logs page-by-page, filtered to e.g. `ERROR`/`WARNING` only, with each
  response comfortably under the token limit.
- An AI consumer can run a cross-simulation log search (e.g. "all ERRORs in this window") without naming every sim id.
- No change to existing tools; no breaking change to any consumer.

## 2. Scope

**In scope**
- Two new read-only MCP tools in the **data** server (`safebreach_mcp_data`):
  1. `get_paginated_simulation_logs` — single-simulation investigation.
  2. `search_simulation_logs` — cross-/multi-simulation search.
- Shared fetch + cache + response-mapping core.
- Unit + integration tests; `CHANGELOG.md` + `CLAUDE.md` docs.

**Out of scope**
- The data endpoint itself (SAF-32099 — done).
- Modifying `get_full_simulation_logs` or migrating other MCP tools off v1.
- Auto-paging / streaming aggregation across pages inside the tool (consumer drives pagination via `hasMore`).

## 3. Design

### 3.1 Two tools, one core

Both tools call the same endpoint and differ only in how the `jobIds` query param is built:

| Tool | `jobIds` built from | Intended use |
|------|---------------------|--------------|
| `get_paginated_simulation_logs` | required `simulation_id` → `jobIds=<id>` | Drill into one simulation's logs |
| `search_simulation_logs` | optional `simulation_ids` (**pipe-delimited**, e.g. `a\|b`) → `jobIds=a\|b`; omitted → param dropped → **all sims** | Cross-sim / fleet-wide log search |

Shared internals in `data_functions.py`:
- `_fetch_simulation_logs_from_api(*, job_ids, page, page_size, min_level, levels, message_contains, start_time, end_time, log_type, sort_order, console)`
  — builds URL `f"{base_url}/api/data/v3/accounts/{account_id}/simulationLogs"`, assembles the `params` dict, GETs with
  `timeout=120`, handles 400/401/404, returns `response.json()`.
- `_get_simulation_logs_from_cache_or_api(...)` — cache wrapper (transform-then-cache).
- Public `sb_get_paginated_simulation_logs(...)` / `sb_search_simulation_logs(...)` — validate inputs, build `job_ids`,
  delegate to the cache layer.

### 3.2 Parameter mapping (MCP → API)

MCP tool params are snake_case scalars (MCP-friendly); the API uses camelCase with `collectionFormat: pipes`. Multi-value
params use **pipe-delimited** strings at the MCP layer too (`a|b`), matching the API's query-param style — no CSV.

| MCP param | Type / default | → API param | Build rule |
|-----------|----------------|-------------|------------|
| `simulation_id` (tool 1) | str, **required** | `jobIds` | `jobIds = simulation_id` |
| `simulation_ids` (tool 2) | str, **pipe-delimited**, optional | `jobIds` | trim segments, drop empties, re-join with `\|`; omit param entirely if empty |
| `page` | int = 1 | `page` | pass-through |
| `page_size` | int = **100** | `pageSize` | clamp/validate ≤ 1000 client-side (clear error, avoid server 400) |
| `min_level` | str = `"INFO"` | `minLevel` | `.upper()` |
| `levels` | str, **pipe-delimited**, optional | `levels` | uppercase + trim each segment, re-join with `\|`; overrides `min_level` server-side |
| `message_contains` | str, optional | `messageContains` | pass-through |
| `start_time` / `end_time` | str, optional | `startTime` / `endTime` | pass-through (ISO-8601 or epoch ms) |
| `log_type` | str = `"LOGS"` | `logType` | `.upper()` (enum `LOGS\|OUTPUT\|ALL`) |
| `sort_order` | str = `"asc"` | `sortOrder` | `.lower()` (enum `asc\|desc`) |
| `console` | str = `"default"` | — | selects base URL / account / auth |

> **`page_size` default = 100 (MCP) vs 500 (API).** Intentional. The MCP tools exist to bound tokens; a smaller default
> keeps the first call safe for the LLM. Consumers can raise it up to 1000. *(Open for review — raise to 200/500 if too
> chatty.)*

> **Pipe style end-to-end.** `simulation_ids` and `levels` are pipe-delimited at the MCP-param level (matching the API's
> `collectionFormat: pipes`), so the tool passes them straight into the single `jobIds` / `levels` query string after
> trim/case-normalization. Do **not** pass a Python list to `requests` (it serializes as repeated `levels=A&levels=B`,
> which the server's pipe parser will not read) — always send one pipe-joined string.

### 3.3 Response mapping — `get_simulation_logs_mapping(api_response)` (`data_types.py`)

Pass the envelope through with snake_case keys to match repo style; keep per-line fields as the API returns them:

```python
{
  "logs": [ {timestamp, level, logType, logger, sourceFile, line, message, pid, jobId, planRunId}, ... ],
  "total": int,
  "page": int,
  "page_size": int,     # from pageSize
  "has_more": bool,     # from hasMore
}
```
Empty/missing `logs` → return `{"logs": [], "total": 0, "page": <req>, "page_size": <req>, "has_more": False}` plus a
`hint_to_agent` ("no logs matched / sim may be old-format with embedded logs — try get_full_simulation_logs").

### 3.4 Caching

`simulation_logs_cache = SafeBreachCache(name="simulation_logs", maxsize=3, ttl=600)` (data-server cache TTL convention).
Cache key must include **every** input that changes the result:
`f"simulation_logs_{console}_{job_ids or 'ALL'}_{page}_{page_size}_{min_level}_{levels}_{message_contains}_{start_time}_{end_time}_{log_type}_{sort_order}{get_cache_user_suffix()}"`.
Gate on `is_caching_enabled("data")`. Transform-then-cache (cache the mapped result), mirroring `get_full_simulation_logs`.

### 3.5 Errors
- 400 → `ValueError` with the server message (e.g. invalid enum / pageSize too large); pre-validate `page_size ≤ 1000`.
- 401 → `ValueError("Authentication failed for console '<console>'")`.
- 404 → `ValueError` explaining the data service may predate SAF-32099 (`/simulationLogs` not available) — distinct from
  "no logs" (which is a 200 with empty list).
- 403 → `check_rbac_response` raises `PermissionError` with RBAC hint.
- Timeout / RequestException → caught, logged, re-raised as `ValueError`.

### 3.6 Investigation strategy (the core model-steering goal)

These tools are a **last resort, not a first step.** The intended investigation flow — and what the tool descriptions
must steer the model toward — is:

1. **Investigate the result *without* logs first.** Use the lightweight simulation result and existing tools
   (`get_simulation_details`, `get_test_simulations`, drift tools, etc.). Logs are large and token-heavy; only reach for
   them when the result alone leaves a real gap — missing root cause, or an explicit deep-dive is required.
2. **When logs are needed, pull them *smartly* — severity-first, keyed on the simulation's status**, escalating only if
   the current level doesn't answer the question:
   - **Failed / not-blocked-as-expected / errored simulation** → start with **`levels=ERROR`** (errors only). If that's
     insufficient, widen to **`WARNING`/`INFO`** (`min_level=INFO`), and only then to **`DEBUG`** (`levels=DEBUG|INFO|...`).
   - **Successful simulation** → start at **`min_level=INFO`** (the default); escalate to `DEBUG` only if a deeper trace
     is genuinely needed.
3. **Page, don't dump.** Fetch one page (default `page_size=100`), read, and only request the next page (`has_more=true`)
   if the answer isn't there yet. Always prefer a `start_time`/`end_time` window and `message_contains` to narrow.

This severity-escalation ladder is the mechanism that keeps the SAF-32058 token overflow from recurring: the agent
converges on the relevant lines (usually a handful of ERRORs) instead of pulling the whole log.

#### Tool descriptions (embed the strategy above)
- `get_paginated_simulation_logs`: "Fetch ONE simulation's execution logs incrementally and filtered (level/type/time/
  message), page by page. **Use only after inspecting the simulation result (`get_simulation_details`) — pull logs solely
  when the result leaves a gap or a deep dive is required.** Pull smartly by severity: for a FAILED/errored simulation
  start with `levels=ERROR`, then widen to `min_level=INFO`, then `DEBUG` only if still unanswered; for a SUCCESSFUL
  simulation start at `min_level=INFO` (default) and escalate to `DEBUG` only if needed. Read one page before requesting
  the next (`has_more`). For the full embedded ~40KB blob or old-format sims (`logsEmbedded=true`), use
  `get_full_simulation_logs`. Results cached ~10 min."
- `search_simulation_logs`: "Search execution logs across many or all simulations (omit `simulation_ids` for all; or pass
  a pipe-delimited list like `id1|id2`). Best for cross-sim/forensic queries like 'all ERRORs in a time window'. Use after
  result-level analysis, and lead with the tightest filter — typically `levels=ERROR` plus a `start_time`/`end_time`
  window — widening severity only if needed. Same pagination contract (`has_more`)."

## 4. Implementation Phases (TDD)

### Phase 1 — Shared fetch core + mapping (red→green)
- `data_types.py`: `get_simulation_logs_mapping()` + unit tests in `tests/test_data_types.py` (full envelope, empty logs,
  missing keys, `hasMore`→`has_more`).
- `data_functions.py`: `_fetch_simulation_logs_from_api(...)` + `simulation_logs_cache` + `_get_..._from_cache_or_api(...)`.
- Unit tests in `tests/test_data_functions.py`: URL/params construction (assert `jobIds`/`levels` pipe-joining, casing
  normalization, omitted params), 200 mapping, 400/401/404 handling, cache hit/miss (key correctness).

### Phase 2 — Public entry points + tool registration
- `data_functions.py`: `sb_get_paginated_simulation_logs(...)`, `sb_search_simulation_logs(...)` (input validation:
  required `simulation_id`; `page_size ≤ 1000`; trim/normalize pipe-delimited `simulation_ids`/`levels`).
- `data_server.py`: import both + register two `@self.mcp.tool(... readOnlyHint=True ...)` wrappers after
  `get_full_simulation_logs_tool`, with the steering descriptions from §3.6.
- Tests in `tests/test_data_server.py` (tool registered, read-only) + `sb_*` unit tests (single-sim → `jobIds=<id>`;
  multi-sim piped `a|b` → `jobIds=a|b`; empty `simulation_ids` → param omitted).

### Phase 3 — Integration + docs
- `tests/test_integration.py`: HTTP-mocked end-to-end for both tools — pagination (`has_more` across pages), each filter
  (levels, min_level, message_contains, time window, log_type, sort_order), casing normalization, cache hit/miss,
  404/401. Mirror existing patterns (`@patch('...requests.get')`, `Mock(status_code, json)`).
- `CHANGELOG.md` "Added" entries; `CLAUDE.md` data-server tool list (items 12a/12b near `get_full_simulation_logs`).

### Phase 4 — Manual / E2E verification (optional, real env)
- Against a console whose data service includes SAF-32099: single-sim paging, cross-sim search, 404 on an old console.

## 5. Testing strategy
- **Unit**: mapping (`test_data_types.py`), fetch/cache/param-build + `sb_*` validation (`test_data_functions.py`).
- **Integration**: HTTP-mocked both tools (`test_integration.py`).
- **Coverage must include**: pipe-joining of `jobIds`/`levels`, casing (UPPER levels/logType, lower sortOrder), omitted
  optional params, `page_size` clamp, empty-logs hint, 400/401/404 messages, cache key uniqueness per filter combination.
- Run: `uv run pytest safebreach_mcp_data/tests/ -m "not e2e"`.

## 6. Risks
- **Console data version**: target console must have the SAF-32099 endpoint, else 404 — surfaced clearly.
- **Old-format sims**: logs embedded, not in the index → `/simulationLogs` empty; hint points to `get_full_simulation_logs`.
- **Unbounded cross-sim search**: omitting `jobIds` searches all sims; mitigated by description steering + server-side
  pageSize cap (max 1000) and `total`/`has_more` so the consumer sees the scale.
- **Param casing/format drift**: server also normalizes, but the tool normalizes client-side to keep cache keys stable.

## 7. Open questions for review
1. Cross-sim tool name: `search_simulation_logs` (chosen) vs `get_cross_simulation_logs`?
2. MCP `page_size` default: 100 (chosen, token-safe) vs 200/500?
3. Should `search_simulation_logs` *require* a time window when `simulation_ids` is omitted, to prevent accidental
   all-sim scans? (Currently optional + steered by description.)
