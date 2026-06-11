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
- An AI consumer can run a cross-simulation log search (e.g. "all ERRORs containing X in the last day", or "how many
  simulations hit error X" via `jobId` dedup) without naming every sim id.
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

### 3.2 Full parameter capability (MCP → API) — expose the API's complete power

**Design principle:** the tools expose the API's *full* filtering + pagination surface with no hidden simplifications and
**defaults identical to the API**, so the consumer (and the model) has complete control. MCP params are snake_case
scalars; multi-value params are **pipe-delimited** strings (`a|b`), matching the API's `collectionFormat: pipes`.

| MCP param | Type / default (= API) | → API param | Capability & build rule |
|-----------|------------------------|-------------|-------------------------|
| `simulation_id` (tool 1) | str, **required** | `jobIds` | Scope to exactly one simulation: `jobIds=<simulation_id>`. |
| `simulation_ids` (tool 2) | str, pipe-delimited, optional | `jobIds` | Scope to one/several sims (`a\|b`) or **all** when omitted. Trim segments, drop empties, re-join with `\|`; omit param entirely if empty. |
| `page` | int = `1` | `page` | 1-based page number. Offset = `(page-1)*page_size`. Subject to the ~10k ceiling (§3.7). |
| `page_size` | int = `500` | `pageSize` | Entries per page, **1–1000**. Validate `≤ 1000` client-side (clear error, avoid server 400). |
| `min_level` | str = `"INFO"` | `minLevel` | Severity **threshold** (inclusive), returns that level **and above**: `DEBUG<INFO<WARNING<ERROR`. `.upper()`. Ignored when `levels` given. |
| `levels` | str, pipe-delimited, optional | `levels` | **Explicit** level set, **overrides** `min_level`. e.g. `ERROR\|WARNING`. Uppercase + trim each segment, re-join with `\|`. |
| `message_contains` | str, optional | `messageContains` | Case-insensitive substring grep over `message` (ES `*term*`). |
| `start_time` | str, optional | `startTime` | Inclusive lower bound on `timestamp`. ISO-8601 **or** epoch millis. |
| `end_time` | str, optional | `endTime` | Inclusive upper bound on `timestamp`. ISO-8601 **or** epoch millis. |
| `log_type` | str = `"LOGS"` | `logType` | `LOGS` = trace lines, `OUTPUT` = raw command output, `ALL` = both. `.upper()`. |
| `sort_order` | str = `"asc"` | `sortOrder` | `asc` (oldest first) / `desc` (newest first); sort key = `timestamp`. `.lower()`. |
| `console` | str = `"default"` | — (path/auth) | selects base URL / account / auth; not sent as a query param. |

**Combining filters (all AND-ed server-side):** `jobIds` (scope) × level (`levels` *or* `min_level`) × `message_contains`
× `[start_time, end_time]` × `log_type`, then sorted by `sort_order` and paged by `page`/`page_size`. Every combination
is valid; omitted filters are no-ops. This is the full control surface — the tool must surface **all** of it.

> **Defaults = API parity (`page_size=500`, `min_level=INFO`, `log_type=LOGS`, `sort_order=asc`).** Token-bounding is
> achieved by the §3.6 *filter-first / severity-first / page-by-page* strategy and by the consumer lowering `page_size`
> when desired — **not** by crippling the default. The tool faithfully mirrors the API. *(Resolves prior open question #2.)*

> **Pipe style end-to-end.** `simulation_ids` and `levels` are pipe-delimited at the MCP-param level (matching the API's
> `collectionFormat: pipes`), so the tool passes them straight into the single `jobIds` / `levels` query string after
> trim/case-normalization. Do **not** pass a Python list to `requests` (it serializes as repeated `levels=A&levels=B`,
> which the server's pipe parser will not read) — always send one pipe-joined string.

> **Validate enums client-side** (`min_level`/`log_type`/`sort_order`) and `page_size ≤ 1000` for fast, friendly errors
> (the server also enforces these as 400 — §3.7). `levels` has no server enum, so an unknown level yields an empty
> result; optionally warn client-side.

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
- **Deep-page window error** (ES "result window too large" when `page*page_size > 10000`) → arrives as a 400/500/`default`
  error; catch and re-raise as a `ValueError` with the §3.7 hint (narrow filters / time window; ~10k offset ceiling).
  Optionally pre-guard client-side when `page * page_size > 10000`.
- Timeout / RequestException → caught, logged, re-raised as `ValueError`.

### 3.6 Investigation strategy (the core model-steering goal)

These tools are a **last resort, not a first step. In most investigations the logs are not needed at all.** The intended
flow — and what the tool descriptions must steer the model toward — is:

1. **Start with the raw simulation object and its simulation steps.** `get_simulation_details` (the result object +
   `simulation_steps`, optionally `include_mitre_techniques` / `include_basic_attack_logs` / `include_drift_info`), plus
   `get_test_simulations` / drift tools, explain the flow for the large majority of cases. **Only when the simulation
   object and steps are genuinely insufficient to understand the flow** — root cause still unclear, or an explicit deep
   dive into execution traces is required — should you reach for these log tools. Logs are large and token-heavy; treat
   pulling them as the exception, not the routine.
2. **When logs are needed, pull them *smartly* — severity-first, keyed on the simulation's status**, escalating only if
   the current level doesn't answer the question:
   - **Failed / not-blocked-as-expected / errored simulation** → start with **`levels=ERROR`** (errors only). If that's
     insufficient, widen to **`WARNING`/`INFO`** (`min_level=INFO`), and only then to **`DEBUG`** (`levels=DEBUG|INFO|...`).
   - **Successful simulation** → start at **`min_level=INFO`** (the default); escalate to `DEBUG` only if a deeper trace
     is genuinely needed.
3. **Page, don't dump.** Fetch one page (default `page_size=500`; lower it for tighter token control), read, and only
   request the next page (`has_more=true`) if the answer isn't there yet. Always prefer a `start_time`/`end_time` window
   and `message_contains` to narrow before paging deeper.

This severity-escalation ladder is the mechanism that keeps the SAF-32058 token overflow from recurring: the agent
converges on the relevant lines (usually a handful of ERRORs) instead of pulling the whole log.

#### Tool descriptions (embed the strategy above)
- `get_paginated_simulation_logs`: "Fetch ONE simulation's execution logs incrementally and filtered (level/type/time/
  message), page by page. **Logs are usually NOT needed — first inspect the raw simulation object and its simulation
  steps via `get_simulation_details`; reach for logs ONLY when that object + steps are insufficient to understand the
  flow (root cause unclear / explicit deep dive).** Pull smartly by severity: for a FAILED/errored simulation
  start with `levels=ERROR`, then widen to `min_level=INFO`, then `DEBUG` only if still unanswered; for a SUCCESSFUL
  simulation start at `min_level=INFO` (default) and escalate to `DEBUG` only if needed. Read one page before requesting
  the next (`has_more`). For the full embedded ~40KB blob or old-format sims (`logsEmbedded=true`), use
  `get_full_simulation_logs`. Results cached ~10 min."
- `search_simulation_logs`: "Search execution logs across many or all simulations (omit `simulation_ids` for all; or pass
  a pipe-delimited list like `id1|id2`). Built for **cross-simulation / fleet-wide investigation** — e.g. 'find every
  ERROR containing "<X>" in the last day', 'how many simulations hit error X', 'which sims logged a timeout this week'.
  Lead with the tightest filter — typically `levels=ERROR` + `message_contains=<X>` + a `start_time`/`end_time` window —
  then page. Each log line carries its `jobId` (and `planRunId`), so the consumer can **group/dedupe by `jobId` to count
  distinct simulations** (see the line-vs-simulation note below). Same pagination contract (`has_more`)."

> **Cross-investigation: counting *simulations* vs *log lines*.** The endpoint returns log **lines**, and `total` is the
> number of matching **lines**, not simulations. For a question like *"how many simulations ended with error X in the last
> day"*, the consumer must page through the matching `ERROR` lines (filtered by `message_contains` + time window) and
> **count distinct `jobId`s**. Each line includes `jobId`, so this works — but it's exact only while the result set fits
> within pagination and the ~10k offset ceiling (§3.7). The data API has **no server-side aggregation / distinct-`jobId`
> count / group-by**, so large-scale exact counts aren't available in one call. See open question #4 on whether a
> data-side aggregation (e.g. a `distinctJobIds`/terms-agg mode) is worth requesting on SAF-32099 for this use case.

### 3.7 Verified data-side behavior & limits (read from SAF-32099 code)

Confirmed by reading the branch (not docs): OpenAPI `src/api/dashboardapi.json:2218-2341`, normalization
`executionsHistoryApi.js:35-69`, ES query `simulationLogsDao.js:60-106`, filter helpers `sbBodyBuilder.js:64-76`.

- **`accountId` is an int32 path param**; `jobIds` + `levels` are real `collectionFormat: pipes` arrays (swagger-tools
  splits on `|`). Confirms pipe-delimited end-to-end.
- **Spec-level validation → HTTP 400** for: `pageSize > 1000`, and out-of-enum `minLevel` / `logType` / `sortOrder`
  (`minLevel` enum is `DEBUG|INFO|WARNING|ERROR`). So a bad `min_level` is a clean 400, *not* a silent all-levels return.
  ⇒ **MCP should validate the same enums + `page_size ≤ 1000` client-side** for fast, friendly errors before the call.
- **`levels` has NO enum** (free string array). An invalid level (e.g. `FOO`) is uppercased and `inFilter`'d →
  matches nothing → **empty result**, not an error and not "all". Worth a doc note / optional client-side validation.
- **Empty filters are no-ops** (`sbBodyBuilder` guards: `inFilter` skips empty arrays, `wildcardFilter` skips empty
  string). So omitting `message_contains` / `levels` / time bounds is safe.
- **⚠️ Offset-pagination ceiling (~10,000).** The DAO uses `from=(page-1)*pageSize` + `size=pageSize` with **no
  `track_total_hits` and no `max_result_window` override** (`simulationLogsDao.js:86-87,98`). Consequences for the consumer:
  1. Once `(page-1)*pageSize + pageSize > 10000` (e.g. `pageSize=1000`, `page=11`), Elasticsearch rejects the query →
     surfaces to MCP as a non-200 ("result window too large"). The MCP layer **must catch this and return a clear hint**:
     *"deep pagination is limited to ~10k matches — narrow with a time window / `levels` / `message_contains`."*
  2. `total` is read as `hits.total.value`, which ES **caps at 10,000** (relation `gte`) unless `track_total_hits` is set.
     For large/unfiltered `search_simulation_logs` queries, `total` is therefore a **lower bound**, and
     `has_more = page*page_size < total` can under-report past the cap. Document this; don't present `total` as exact.
  3. This is exactly why the §3.6 *filter-first, severity-first* strategy matters — it keeps result sets well under 10k.
- **Sort key is `timestamp` only** — no secondary tie-breaker. Lines sharing a timestamp may shift across page
  boundaries. Acceptable for triage; note it for strict forensic ordering.
- **Index**: `executions_simulations_logs` (alias `…-rollover-*`); per-line fields `_source` passed through verbatim.

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
  optional params, `page_size` clamp + enum validation (`min_level`/`log_type`/`sort_order`), empty-logs hint,
  400/401/404 messages, deep-page (`page*page_size > 10000`) ceiling error + hint, cache key uniqueness per filter combination.
- Run: `uv run pytest safebreach_mcp_data/tests/ -m "not e2e"`.

## 6. Risks
- **Console data version**: target console must have the SAF-32099 endpoint, else 404 — surfaced clearly.
- **Old-format sims**: logs embedded, not in the index → `/simulationLogs` empty; hint points to `get_full_simulation_logs`.
- **Unbounded cross-sim search**: omitting `jobIds` searches all sims; mitigated by description steering + server-side
  pageSize cap (max 1000) and `total`/`has_more` so the consumer sees the scale. Bounded further by the ~10k offset
  ceiling (§3.7) — beyond that the consumer must narrow filters; `total` may be a lower bound for huge result sets.
- **Param casing/format drift**: server also normalizes, but the tool normalizes client-side to keep cache keys stable.

## 7. Open questions for review
1. Cross-sim tool name: `search_simulation_logs` (chosen) vs `get_cross_simulation_logs`?
2. ~~MCP `page_size` default~~ — **resolved**: defaults mirror the API exactly (`page_size=500`, max 1000) for full
   control; token-bounding comes from the §3.6 strategy + consumer-chosen `page_size`, not a crippled default.
3. Should `search_simulation_logs` *require* a time window when `simulation_ids` is omitted, to prevent accidental
   all-sim scans? Current stance: keep it optional (full control) and steer via description + the ~10k ceiling hint.
4. **Cross-investigation counts** (e.g. "how many simulations ended with error X in the last day"): the API returns log
   *lines* and `total` counts lines, so distinct-simulation counts need client-side `jobId` dedup, exact only under the
   ~10k ceiling. Is a **data-side aggregation** worth requesting on SAF-32099 — a `distinctJobIds`/terms-agg or
   "count mode" that returns matching simulation count (and optionally per-`jobId` line counts) in one call? Would make
   fleet-wide "how many sims hit X" exact and cheap; out of scope for this MCP ticket but the natural follow-up.

## 8. Definition of Done
- [x] `get_simulation_logs_mapping()` added in `data_types.py` (envelope → snake_case, empty-logs hint).
- [x] Shared `_fetch_simulation_logs_from_api()` + `simulation_logs_cache` + cache wrapper in `data_functions.py`.
- [x] `sb_get_paginated_simulation_logs()` + `sb_search_simulation_logs()` with input validation.
- [x] Both tools registered in `data_server.py` (`readOnlyHint=True`) with the §3.6 steering descriptions.
- [x] Pipe-joining + casing normalization + omitted-param handling verified by tests.
- [x] Error handling: 400 (enum/pageSize), 401, 404 (endpoint-missing), deep-page ~10k ceiling — each with clear message.
- [x] Caching: key includes console + jobIds + every filter + page; gated on `is_caching_enabled("data")`.
- [x] Unit + integration tests pass: `uv run pytest safebreach_mcp_data/tests/ -m "not e2e"` (453 data tests green).
- [x] All existing tests pass (453 data tests green). *(No linter configured in this repo — tests are the gate.)*
- [x] `CHANGELOG.md` + `CLAUDE.md` updated.

## 9. Phase Status Tracking

| Phase | Name | Status | Completed | Commit | Notes |
|-------|------|--------|-----------|--------|-------|
| 1 | Shared fetch core + mapping | ✅ Complete | 2026-06-11 | (this branch) | `get_simulation_logs_mapping` + `_fetch_simulation_logs_from_api` + `_get_..._from_cache_or_api` + `simulation_logs_cache`; 15 new tests, 429 data tests green |
| 2 | Public entry points + tool registration | ✅ Complete | 2026-06-11 | (this branch) | `sb_get_paginated_simulation_logs` + `sb_search_simulation_logs` (validation: required id, page_size≤1000, deep-page ~10k guard, enum checks) + two `@mcp.tool` regs; 17 new tests, 446 data tests green |
| 3 | Integration + docs | ✅ Complete | 2026-06-11 | (this branch) | `TestSimulationLogsIntegration` (7 HTTP-mocked e2e tests) + CHANGELOG Unreleased + CLAUDE.md 12a/12b; 453 data tests green |
| 4 | Manual / E2E verification (optional) | ⏳ Pending | — | — | Real-env checks; optional, no code — needs a console with the SAF-32099 endpoint |

Status icons: ✅ Complete · 🔄 In Progress · ⏳ Pending · ❌ Blocked

## 10. Document Status
- **Last Updated:** 2026-06-11
- **Author:** Amir Rossert (planning via planning-dev-task)
- **Branch:** `feature/SAF-32143-paginated-simulation-logs`
