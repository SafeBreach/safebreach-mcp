# Manual Test Plan — SAF-32143 paginated/filterable simulation-logs tools

Covers what unit/integration mocks **cannot**: real `data` v3 `/simulationLogs` behavior, auth/RBAC, real
pagination math, filter semantics against the live ES index, and the old-console 404 path. Run against a console whose
`data` service includes the SAF-32099 endpoint (and, for P1-6, one that does **not**).

**Setup:** run the data server (`uv run -m safebreach_mcp_data.data_server`) with a configured console; have a known
`simulation_id` (jobId) from a recent test (use `get_test_simulations`). Tools under test:
`get_paginated_simulation_logs`, `search_simulation_logs`.

## P0 — must pass (core contract)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| P0-1 | Single-sim happy path | `get_paginated_simulation_logs(simulation_id=<id>)` on a sim with logs | `{logs:[…], total, page:1, page_size:500, has_more}`; lines have `timestamp/level/message/jobId/planRunId`; all `jobId == <id>` |
| P0-2 | Pagination walk | call with `page_size=50`, then `page=2`, `page=3` while `has_more` | no duplicate/missing lines across pages; `has_more` flips to false on last page; `total` stable |
| P0-3 | `min_level` threshold | `min_level=ERROR` vs `min_level=INFO` on same sim | ERROR set ⊆ INFO set; DEBUG absent unless requested; default (no min_level) shows INFO+ (no DEBUG) |
| P0-4 | Explicit `levels` overrides | `levels="ERROR|WARNING"` (with `min_level=INFO`) | only ERROR+WARNING lines; min_level ignored |
| P0-5 | `message_contains` | pick a substring from a known line, e.g. `message_contains=timeout` | only lines whose message contains it (case-insensitive) |
| P0-6 | Old console → 404 | run against a console whose data predates SAF-32099 | clean `ValueError`: "endpoint not available / data service may predate…" — **not** a stack trace |

## P1 — should pass (filters, cross-sim, errors)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| P1-1 | Time window | `start_time`/`end_time` (try both ISO-8601 and epoch ms) bracketing part of the run | only in-window lines; both formats accepted |
| P1-2 | `log_type` | `log_type=OUTPUT`, then `ALL`, vs default `LOGS` | OUTPUT = command output only; ALL ≥ LOGS∪OUTPUT; LOGS = trace lines |
| P1-3 | `sort_order` | `sort_order=desc` vs `asc` | desc = newest first; asc = oldest first (by timestamp) |
| P1-4 | Cross-sim scoped | `search_simulation_logs(simulation_ids="<id1>|<id2>", levels="ERROR")` | lines only from those two jobIds; mixed `jobId` values present |
| P1-5 | Cross-sim ALL | `search_simulation_logs(levels="ERROR", start_time=<last 24h>)` (omit ids) | ERROR lines across many sims in the window; multiple distinct `jobId`s |
| P1-6 | Count distinct sims | from P1-5 result, dedupe `jobId` | matches the real number of sims that logged that error in-window (within ≤10k lines) |
| P1-7 | Empty result hint | filter that matches nothing (e.g. `message_contains=zzz-nope`) | `logs:[]`, `total:0`, `has_more:false`, `hint_to_agent` present pointing to get_full_simulation_logs / widen filters |
| P1-8 | Old-format sim | a sim flagged `logsEmbedded=true` in its result | `/simulationLogs` returns empty + hint; `get_full_simulation_logs` still returns the embedded blob |

## P2 — validation & guardrails (fast client-side errors, no API call)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| P2-1 | page_size cap | `page_size=5000` | `ValueError` mentioning page_size / 1000 |
| P2-2 | deep-page ceiling | `page=11, page_size=1000` (`>10000`) | `ValueError` about the ~10k ceiling suggesting narrowing — before any HTTP call |
| P2-3 | bad enums | `min_level=TRACE`; `log_type=STDERR`; `sort_order=up` (separately) | `ValueError` naming the offending param |
| P2-4 | invalid level in `levels` | `levels="ERROR|BOGUS"` | `ValueError` listing invalid level(s) |
| P2-5 | empty simulation_id | `get_paginated_simulation_logs(simulation_id="")` | `ValueError` "simulation_id … required" |
| P2-6 | RBAC / auth | low-privilege token (403) and bad token (401) | 403 → `PermissionError` with RBAC hint; 401 → `ValueError` "Authentication failed" |

## P3 — performance / caching (real env)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| P3-1 | Cache hit | enable data caching (`SB_MCP_CACHE_DATA=true`); identical call twice | 2nd is fast / no 2nd API call; ~10 min TTL |
| P3-2 | Cache isolation | same sim, different `min_level` (ERROR vs INFO) | distinct results (no cross-contamination from a shared key) |
| P3-3 | Token-bounding | large/verbose sim: default vs `levels=ERROR` + small `page_size` | ERROR-first + small page returns a token-manageable payload (the SAF-32058 goal) |

## Investigation-flow sanity (the steering intent)

- Confirm the tool descriptions actually steer an agent: given a failed sim, the agent should reach for
  `get_simulation_details` first and only call `get_paginated_simulation_logs` (ERROR-first) when the result/steps don't
  explain the failure. Spot-check with a real prompt to the connected MCP client.

## Notes
- `total` may be a lower bound for very large cross-sim searches (ES caps at 10k unless track_total_hits) — verify it is
  not presented as exact when `has_more` is true at the ceiling.
- Sort is by `timestamp` only (no tie-breaker); lines sharing a timestamp may reorder across pages — acceptable for triage.
