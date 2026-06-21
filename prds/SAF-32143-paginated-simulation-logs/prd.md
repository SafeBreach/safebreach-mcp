# PRD — MCP paginated/filterable simulation-logs tools (SAF-32143)

| Field | Value |
|-------|-------|
| Ticket | [SAF-32143](https://safebreach.atlassian.net/browse/SAF-32143) — `safebreach-mcp` \| Add MCP tool(s) for paginated/filterable simulation logs |
| Type | Task |
| Repo / branch | `safebreach-mcp` / `feature/SAF-32143-paginated-simulation-logs` |
| Companion | [SAF-32099](https://safebreach.atlassian.net/browse/SAF-32099) (data v3 `/simulationLogs`, branch `feature/SAF-32099-paginate-simulation-logs-api`) |
| Context bug | [SAF-32058](https://safebreach.atlassian.net/browse/SAF-32058) / support SB-36091 (HELM LLM token overflow) |
| Status | Implemented (Phases 1–3 + scope additions 5–8); Phase 4 E2E verification complete; in Code Review. |

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
- An AI consumer can fetch a single simulation's logs page-by-page, filtered to e.g. `ERROR`/`WARNING` only (and scoped to
  a single attack node), with each response comfortably under the token limit.
- An AI consumer can run a cross-simulation log search (e.g. "all ERRORs containing X in the last day", or "how many
  simulations hit error X" via `jobId` dedup) without naming every sim id.
- The agent investigates **result-first**: `get_test_simulation_details` returns the raw simulation result + steps (no
  logs), and the agent only pulls logs when those are insufficient.
- Backward-compatible at the data layer (v3 with v1 fallback). Two existing tools change deliberately (see §2): the
  `get_test_simulation_details` response shape change is the one intended breaking change for MCP consumers.

## 2. Scope

**In scope** (final, including scope additions made during implementation)
- Two new read-only MCP tools in the **data** server (`safebreach_mcp_data`):
  1. `get_paginated_simulation_logs` — single-simulation investigation (incl. `node_id` per-node scoping — Phase 7).
  2. `search_simulation_logs` — cross-/multi-simulation search (incl. `node_id`).
- Shared fetch + cache + response-mapping core.
- **`get_full_simulation_logs` migrated to the v3 result endpoint** (`includeLogs=true`, v1 fallback) and now exposes
  `logs_embedded` (Phase 5).
- **`get_test_simulation_details` returns a curated hybrid result without logs** — the flat snake_case envelope PLUS
  `simulation_steps_by_node` + `logs_embedded` (Phase 6, revised by Phase 8). Result-first investigation entry point.
- **Phase 8 (scope addition) — hybrid revision of Phase 6:** Phase 6 originally relayed the *entire raw v3 document*.
  Phase 8 replaces that with a curated envelope + nested per-node steps (see §3.8 for the design and reasoning).
- Unit + integration tests; `CHANGELOG.md` + `CLAUDE.md` docs.

**Out of scope**
- The data endpoint itself (SAF-32099 — done).
- Migrating other MCP tools off v1. Verified in the data repo that no other MCP-consumed endpoint embeds logs (the v1
  list endpoint behind `get_test_simulations` whitelists `_source` and excludes `dataObj`), so no other migration is needed.
- Auto-paging / streaming aggregation across pages inside the tool (consumer drives pagination via `hasMore`).
- Server-side distinct-`jobId` aggregation for exact fleet-wide counts (data-side follow-up — see §7 Q4).

## 3. Design

### 3.1 Two tools, one core

Both tools call the same endpoint and differ only in how the `jobIds` query param is built:

| Tool | `jobIds` built from | Intended use |
|------|---------------------|--------------|
| `get_paginated_simulation_logs` | required `simulation_id` → `jobIds=<id>` | Drill into one simulation's logs |
| `search_simulation_logs` | optional `simulation_ids` (**pipe-delimited**, e.g. `a\|b`) → `jobIds=a\|b`; omitted → param dropped → **all sims** | Cross-sim / fleet-wide log search |

Shared internals in `data_functions.py`:
- `_fetch_simulation_logs_from_api(*, job_ids, node_id, page, page_size, min_level, levels, message_contains, start_time, end_time, log_type, sort_order, console)`
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
| `node_id` (both tools) | str, optional | `nodeId` | Scope to a single simulator node of the attack (e.g. attacker vs target). Exact match, trimmed, no casing. Id comes from `get_test_simulation_details` (`attackerNodeId`/`targetNodeId` or `dataObj.data[..].id`). Omit = all nodes. |
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
Cache key must include **every** input that changes the result (incl. `node_id`):
`f"simulation_logs_{console}_{job_ids or 'ALL'}_{node_id or 'ALLNODES'}_{page}_{page_size}_{min_level}_{levels}_{message_contains}_{start_time}_{end_time}_{log_type}_{sort_order}{get_cache_user_suffix()}"`.
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

1. **Start with the raw simulation object and its simulation steps.** `get_test_simulation_details` returns the raw v3
   result (logs excluded) including per-node `dataObj.data[..].details.SIMULATION_STEPS` and the `logsEmbedded` hint
   (optionally `include_mitre_techniques` / `include_basic_attack_logs` / `include_drift_info`), plus
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
  steps via `get_test_simulation_details`; reach for logs ONLY when that object + steps are insufficient to understand the
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

### 3.8 `get_test_simulation_details` shape — curated hybrid (Phase 8, supersedes the Phase 6 raw passthrough)

**What Phase 6 shipped first.** Phase 6 replaced the curated simulation entity with the *entire raw v3 result document*
(`includeLogs=false`): raw camelCase/Pascal_Case fields, `dataObj.data[..].details.SIMULATION_STEPS`, and `logsEmbedded`.
The driver was sound: the old curated entity exposed **no execution steps**, so an investigating agent had nothing
between "final status" and "dump the 40KB log blob" — which is exactly the gap that produced the SAF-32058 overflow.

**Why raw-passthrough was the wrong delivery (reasoning).** Returning the whole raw doc as the top-level shape carried
four costs:
1. **Contradicts our own design principle** — detail tools should *explain to the LLM (reduce/simplify)*, not *relay raw
   payload* (recorded design feedback; `get_scenario_details` precedent). Phase 6 conflated the two in one tool.
2. **Token cost rises for the common path** — ironic for a token-reduction ticket: an agent that just needs "was this
   blocked?" receives a large raw document instead of ~25 curated fields. (Still far cheaper than logs.)
3. **Brittle contract** — couples every MCP consumer to the data service's internal ES/v3 schema and casing; a curated
   mapping is a stable interface, "whatever v3 returns" is not.
4. **Silent breaking change** — top-level `simulation_id`/`status`/`attacker_node_id` disappeared; any consumer reading
   them breaks with no migration path. (Our own E2E assertions were the canary — 5 failures, see §9 Phase 8.)

   The capability (steps) is essential; the raw envelope is not. The fix is **both**, not either/or.

**Phase 8 hybrid shape.** `get_test_simulation_details` returns a curated, LLM-friendly envelope **plus** the forensic
middle tier:
- **Curated flat fields** (snake_case) — rebuilt from the existing `full_simulation_results_mapping` via
  `get_full_simulation_result_entity(...)`: `simulation_id`, `status`, `test_id`, `playbook_attack_name`, `attack_plan`,
  `attacker_node_id`/`target_node_id` (+ names/OS), `result_details`, security-control fields, plus the optional
  `mitre_techniques` / `basic_attack_logs_by_hosts` / `drift_info` enrichments merged into the same envelope.
- **`simulation_steps_by_node`** — a flat list, one entry per simulator node, each tagged with its `role`
  (`attacker` / `target` / `host` / `unknown`) and carrying `node_id`, `node_name`, `state`, `task_status`, `error`,
  and `simulation_steps`. **Heavy per-node LOGS/OUTPUT blobs are excluded** (steps only) — deep log retrieval stays in
  `get_paginated_simulation_logs` / `get_full_simulation_logs`. Built by `build_simulation_steps_by_node()` in
  `data_types.py` from `dataObj.data[0]`, with role assignment mirroring `get_full_simulation_logs_mapping`'s
  attacker/target/host logic.
- **`logs_embedded`** — snake_case routing flag (was raw `logsEmbedded`): `false` → escalate to
  `get_paginated_simulation_logs`; `true` → old-format sim, use `get_full_simulation_logs`; `None` → unknown (v1 fallback).
- **`hint_to_agent`** — steers result-first, severity-first per §3.6.
- **Older consoles (no v3 result endpoint)** → curated list row + **empty** `simulation_steps_by_node` + explanatory hint.

**Net effect.** Keeps 100% of the Phase 6 capability (per-node steps → the middle tier that prevents SAF-32058) while
eliminating all four costs: the curated snake_case contract is restored (no silent break), token cost for the common
path drops, consumers no longer couple to the raw schema, and the tool re-aligns with the "explain to the LLM" principle.
The raw v3 document is **not** relayed; it remains reachable only through the dedicated logs tools when truly needed.

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
- See `manual-tests.md` (API-level) and `agent-test-plan.md` (behavioral — prompts → expected tool calls).

### Phase 5 — `get_full_simulation_logs` → v3 result endpoint (scope addition)
- Fetch via `GET …/v3/…/executionsHistoryResults/{id}?runId=&includeLogs=true`; fall back to v1 on 404 (older consoles).
- Expose `logs_embedded` in the mapped response; add the `logsEmbedded` routing rule to all three logs-tool descriptions.

### Phase 6 — `get_test_simulation_details` → raw v3 result without logs (scope addition; superseded by Phase 8)
- Replace the curated entity with the raw v3 result (`includeLogs=false`): full doc + `SIMULATION_STEPS` + `logsEmbedded`,
  LOGS/OUTPUT excluded server-side. Merge optional enrichments (mitre/basic logs/drift) on top; list-row fallback on old
  consoles. `hint_to_agent` routes to paginated logs (`logsEmbedded=false`) or full logs (`true`). **Breaking shape change.**
- **Superseded by Phase 8** — raw-passthrough delivery was reverted to a curated hybrid (see §3.8 for the reasoning).

### Phase 7 — `node_id` per-node filter (scope addition)
- data added a `nodeId` filter to `/simulationLogs` (merged to develop). Thread `node_id` through the fetch core, cache
  key, and both `sb_*` entry points + tool wrappers; descriptions explain scoping to the attacker vs target node.

### Phase 8 — `get_test_simulation_details` curated hybrid shape (scope addition; revises Phase 6)
- Stop relaying the raw v3 document. Build the curated flat envelope via `get_full_simulation_result_entity(...)` and
  attach `simulation_steps_by_node` (new `build_simulation_steps_by_node()` in `data_types.py`, role-tagged, heavy
  LOGS/OUTPUT excluded) + snake_case `logs_embedded` + `hint_to_agent`. See §3.8 for the full design and reasoning.
- Restores the curated snake_case contract (`simulation_id`/`status`/node ids), so the Phase 4 E2E assertions pass again
  while additionally verifying the new `simulation_steps_by_node` / `logs_embedded` fields.

## 5. Testing strategy
- **Unit**: mapping (`test_data_types.py`), fetch/cache/param-build + `sb_*` validation (`test_data_functions.py`).
- **Integration**: HTTP-mocked both tools (`test_integration.py`).
- **Coverage must include**: pipe-joining of `jobIds`/`levels`, casing (UPPER levels/logType, lower sortOrder), omitted
  optional params, `node_id` present-when-given / omitted-when-empty + per-node cache-key uniqueness, `page_size` clamp +
  enum validation (`min_level`/`log_type`/`sort_order`), empty-logs hint, 400/401/404 messages, deep-page
  (`page*page_size > 10000`) ceiling error + hint, cache key uniqueness per filter combination.
- **Existing-tool changes**: `get_full_simulation_logs` v3 URL + v1 fallback + `logs_embedded`; `get_test_simulation_details`
  curated hybrid (Phase 8) — curated flat fields present, `simulation_steps_by_node` role-tagged with steps and **no**
  heavy LOGS/OUTPUT, `logs_embedded` snake_case, v3-404 list-row fallback (empty steps), routing hint.
- **Phase 8 coverage**: `build_simulation_steps_by_node()` (host single-node, dual-script attacker/target roles,
  unknown-id role, empty/missing `dataObj`); `sb_get_simulation_details` hybrid shape (curated fields + steps +
  `logs_embedded`, no `dataObj`/raw camelCase passthrough); `logsEmbedded=true` old-format hint.
- Run: `uv run pytest safebreach_mcp_data/tests/ -m "not e2e"` — **471 data tests green** (467 + 4 new helper tests).

## 6. Risks
- **Console data version**: target console must have the SAF-32099 endpoint, else 404 — surfaced clearly.
- **Old-format sims**: logs embedded, not in the index → `/simulationLogs` empty; hint points to `get_full_simulation_logs`.
- **Unbounded cross-sim search**: omitting `jobIds` searches all sims; mitigated by description steering + server-side
  pageSize cap (max 1000) and `total`/`has_more` so the consumer sees the scale. Bounded further by the ~10k offset
  ceiling (§3.7) — beyond that the consumer must narrow filters; `total` may be a lower bound for huge result sets.
- **Param casing/format drift**: server also normalizes, but the tool normalizes client-side to keep cache keys stable.

## 7. Open questions for review
1. ~~Cross-sim tool name~~ — **resolved**: shipped as `search_simulation_logs`.
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
- [x] Caching: key includes console + jobIds + `node_id` + every filter + page; gated on `is_caching_enabled("data")`.
- [x] `node_id` per-node filter threaded through both tools (Phase 7).
- [x] `get_full_simulation_logs` on v3 result endpoint (`includeLogs=true`, v1 fallback) exposing `logs_embedded` (Phase 5).
- [x] `get_test_simulation_details` returns a curated hybrid result (Phase 8, supersedes Phase 6 raw-passthrough):
  curated flat fields + `simulation_steps_by_node` (role-tagged, no heavy logs) + `logs_embedded` + enrichments +
  list-row fallback; CHANGELOG + CLAUDE.md updated for the hybrid shape.
- [x] `build_simulation_steps_by_node()` added in `data_types.py` with unit coverage (Phase 8).
- [x] Unit + integration tests pass: `uv run pytest safebreach_mcp_data/tests/ -m "not e2e"` (471 data tests green).
- [x] All existing tests pass (471 data tests green; 1204 cross-server non-e2e green). *(No linter configured — tests are the gate.)*
- [x] `CHANGELOG.md` + `CLAUDE.md` updated.
- [x] Phase 4 real-env verification — full E2E run against a SAF-32099 console (the 5 previously-failing
  `get_test_simulation_details` / `get_full_simulation_logs` E2E tests now assert + pass the hybrid shape).

## 9. Phase Status Tracking

| Phase | Name | Status | Completed | Commit | Notes |
|-------|------|--------|-----------|--------|-------|
| 1 | Shared fetch core + mapping | ✅ Complete | 2026-06-11 | (this branch) | `get_simulation_logs_mapping` + `_fetch_simulation_logs_from_api` + `_get_..._from_cache_or_api` + `simulation_logs_cache`; 15 new tests, 429 data tests green |
| 2 | Public entry points + tool registration | ✅ Complete | 2026-06-11 | (this branch) | `sb_get_paginated_simulation_logs` + `sb_search_simulation_logs` (validation: required id, page_size≤1000, deep-page ~10k guard, enum checks) + two `@mcp.tool` regs; 17 new tests, 446 data tests green |
| 3 | Integration + docs | ✅ Complete | 2026-06-11 | (this branch) | `TestSimulationLogsIntegration` (7 HTTP-mocked e2e tests) + CHANGELOG Unreleased + CLAUDE.md 12a/12b; 453 data tests green |
| 4 | Manual / E2E verification | ✅ Complete | 2026-06-18 | (this branch) | Full E2E run against `pentest01` (SAF-32099 console): 107 passed initially; surfaced the Phase 6 stale-assertion gap (5 `simulation_id` failures) → fixed via Phase 8 hybrid; re-verified all 5 now pass |
| 5 | v3 migration of `get_full_simulation_logs` (scope addition) | ✅ Complete | 2026-06-11 | (this branch) | v3 result endpoint `includeLogs=true` + v1 fallback; `logs_embedded` exposed; logsEmbedded routing rule in all 3 logs-tool descriptions; 7 new tests, 460 green |
| 6 | `get_test_simulation_details` → raw v3 result without logs (scope addition) | ✅ Complete | 2026-06-11 | (this branch) | Replace curated entity with raw v3 result (`includeLogs=false`): full doc + SIMULATION_STEPS + logsEmbedded, LOGS/OUTPUT excluded server-side (ES `_source` excludes — no client strip needed); enrichments merged on top; list-row fallback for old consoles; hint routes to paginated logs / full logs by logsEmbedded; 462 tests green |
| 7 | `node_id` filter for per-node investigation (scope addition) | ✅ Complete | 2026-06-11 | (this branch) | data added `nodeId` to /simulationLogs (merged to develop); MCP threads `node_id` through fetch/cache/both entry points + tool wrappers; descriptions explain scoping to attacker vs target node (id from get_test_simulation_details); 467 tests green |
| 8 | `get_test_simulation_details` curated hybrid shape (scope addition; revises Phase 6) | ✅ Complete | 2026-06-18 | (this branch) | Reverted the Phase 6 raw-passthrough to a curated envelope + `simulation_steps_by_node` (role-tagged, heavy logs excluded) + snake_case `logs_embedded`; new `build_simulation_steps_by_node()` in data_types.py; restores the curated snake_case contract while keeping the forensic steps (see §3.8 for reasoning); 471 data / 1204 cross-server non-e2e green |
| 9 | Field-evaluation fixes (Claude Desktop report, staging) | ✅ Complete | 2026-06-18 | (this branch) | From a live Claude Desktop eval against staging: (1) rewrote `get_full_simulation_logs` description — call it ONLY when `logs_embedded=true` (old wording's "always retrieve for stopped/no-result" caused over-calling + ~40KB context dumps); (2) `get_test_simulation_details` returns a graceful `{error, hint}` for a non-existent sim id instead of `IndexError`; (3) added `total_capped` to the logs envelope so the ES 10k `total` cap is detectable programmatically (lower-bound hint). 475 data / 1208 cross-server non-e2e green; fixes verified live on staging |

Status icons: ✅ Complete · 🔄 In Progress · ⏳ Pending · ❌ Blocked

### Deferred field-evaluation items (other tools / data-side — not in SAF-32143 scope)
- **`get_simulation_result_drifts` / `get_simulation_status_drifts`** — `window_start`/`window_end` are marked
  `default: null` in the schema but are effectively required (clear error if omitted). Fix the schema (mark required) or
  add a server-side default. *(SAF-28330 drift tools — separate ticket.)*
- **`get_paginated_simulation_logs`** — attacker-node log lines lack `planRunId` (target lines have it). The MCP passes
  `_source` through verbatim, so this is a **data-side** index/field issue on SAF-32099, not an MCP fix.
- **`get_simulation_lineage`** — accepts only `tracking_code` (two-hop via `get_test_simulation_details`); consider a
  `simulation_id` shortcut. *(Separate tool/enhancement.)*
- **`get_test_simulation_details`** low-priority shape polish — `drift_info: {last_drift_date: null}` when not drifted is
  redundant; `mitre_techniques: []` is ambiguous (no mapping vs not fetched). Candidate for a follow-up cleanup.

## 10. Manual E2E verification record (Claude Desktop → live console)

This section records the real-environment verification (Phase 4) — both the automated E2E suite and the
agent-behavioral evaluation through Claude Desktop — and the reasoning behind what it changed.

### 10.1 Endpoint-availability journey — why **staging** was the only viable target

The SAF-32099 data API (`/simulationLogs` + the v3 `executionsHistoryResults` result endpoint) is merged to the data
`develop` branch but is **not deployed to most consoles**. Direct HTTP probing established this conclusively:

| Console | `/simulationLogs` probe | Meaning |
|---------|-------------------------|---------|
| pentest01, flat-carp, demo03 | **HTTP 404 "Cannot GET"** | route absent — data build predates SAF-32099 |
| zircon-piculet | 500 | backend unavailable |
| **staging** | **SAF-32099 JSON error / 200** | route **present** — build includes SAF-32099 |

Two consequences worth recording:
- **The automated E2E suite on pentest01 (112 passed) did NOT exercise the new v3 capability.** pentest01 has no v3
  endpoint, so `get_test_simulation_details` and `get_full_simulation_logs` ran their **v1/list-row fallback** paths; the
  tests are written to tolerate the fallback (present-key / list-type assertions), so they pass without proving the v3
  behavior. This is exactly why a console with SAF-32099 was required — and why the earlier flat-carp "raw v3 doc"
  observation was a red herring (the v1 list row carries the same Pascal-case fields, so it was also the fallback path).
- **Staging was mid-upgrade during verification** (backend `169.254.254.120:8181` `EHOSTUNREACH`, then a maintenance
  page). Verification proceeded once it stabilized; this is environment flakiness, not a tool issue.

### 10.2 Demo target (verified ground truth)

- Console `staging`, test `1781090503798.2` (*Step 1 – Fortify your Network Perimeter (Infiltration)*), simulation
  **`3504301`** (*Communication with APT (US-CERT AA23-025A) using HTTP*, status `no-result`).
- **Dual-script** infiltration: attacker node `3b6e04fb-…` (Linux CentOS7), target node `8d528fe8-…` (Ubuntu18).
- **Root cause (ground truth):** proxy DNS resolution failure — `cURL perform error: Could not resolve proxy:
  testproxy.sbops.com` (credentials masked `**********`). Having a known root cause let us verify the *result-first*
  flow actually lands the answer.
- **Log profile:** by level ERROR=4 / WARNING=4 / INFO=76 / DEBUG=118; by node attacker=68 / target=50; by type
  LOGS=106 / OUTPUT=12. Across the 10-sim test, `proxy`+ERROR matched all 10 sims (env-wide misconfig).

### 10.3 Flows exercised against the live SAF-32099 endpoint — all verified ✅

| Flow | Tool calls | Verified result |
|------|-----------|-----------------|
| Result-first | `get_test_simulation_details(3504301)` | Curated envelope; `simulation_steps_by_node` role-tagged (target ERROR/14 steps, attacker ERROR/8 steps); `logs_embedded=false`; **`result_details` surfaced the proxy root cause with no log call needed**. Leak-check: `dataObj`/`finalStatus` absent → raw doc not relayed |
| Severity-first | `get_paginated_simulation_logs(3504301, levels=ERROR)` | `total=4`, complete answer, zero noise — the SAF-32058 anti-overflow behavior in practice |
| Pagination / type | `…(log_type=OUTPUT)` / `min_level=DEBUG` | OUTPUT=12 isolated; DEBUG walks 118 lines across pages (`has_more` flips) |
| Per-node | `…(node_id=attacker)` / `…(node_id=target)` | attacker=68, target=50 (vs 118 all-nodes) — node scoping correct |
| Cross-sim search | `search_simulation_logs(message_contains=proxy, min_level=ERROR)` | 40 ERROR lines across 10 distinct `jobId`s — confirmed env-wide; unscoped query hit the 10k cap |

### 10.4 Findings → disposition (the reasoning)

The Claude Desktop evaluation confirmed the **design intent works** (result-first + per-node steps + severity-first
filtering replace the 40KB-dump pattern) and surfaced 8 issues. Disposition:

**Fixed in-scope (Phase 9) — because they live in this PRD's tools and directly affect the steering goal:**
- *High — `get_full_simulation_logs` "always retrieve" wording.* This is the most important finding: the description told
  the agent to **always** pull full logs for `stopped`/`no-result` sims — the exact opposite of the PRD's thesis, and a
  direct path back to the SAF-32058 token overflow. The whole value of the new tools is undone if the detail tool's
  sibling steers the model to dump 40KB anyway. Rewrote to: call **only** when `logs_embedded=true`. *(Reasoning: steering
  is the deliverable here, not just the endpoints.)*
- *High — `IndexError` on a non-existent sim id.* Surfaced because the eval queried a staging sim id against pentest01.
  Even though that's a console mismatch, a tool must not crash on "not found" — it returns a graceful `{error, hint}` now.
- *Medium — `total_capped` flag.* The ES 10k cap made `total` a silent lower bound; an agent reporting "10,000 errors"
  is wrong. Made it programmatically detectable rather than relying on the model to infer it from prose. *(Reasoning:
  correctness of agent-reported counts; cheap to expose, expensive to get wrong.)*

**Deferred — documented in §9; out of this PRD's surface:**
- Drift-tool `window_start` schema (SAF-28330, different feature). • `planRunId` missing on attacker log lines — the MCP
  relays `_source` verbatim, so this is a **data-side** SAF-32099 fix, not addressable in MCP. • `get_simulation_lineage`
  `simulation_id` shortcut (separate tool). • `drift_info`/`mitre_techniques` shape polish (low-priority follow-up).

**Net:** the report's verdict ("substantial improvement; core flow works as designed") matches the design intent, and the
one actively-harmful item was a steering-description bug — now corrected and re-verifiable via `agent-test-plan.md`.

## 11. Document Status
- **Last Updated:** 2026-06-18
- **Author:** Amir Rossert (planning via planning-dev-task); Phase 8 hybrid revision + E2E verification by Yossi Attas
- **Branch:** `feature/SAF-32143-paginated-simulation-logs`
- **Related test docs:** `manual-tests.md` (API-level), `agent-test-plan.md` (agent-behavioral), `context.md` (investigation notes).
