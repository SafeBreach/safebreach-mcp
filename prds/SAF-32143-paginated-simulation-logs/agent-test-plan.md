# Agent Test Plan — SAF-32143 simulation-logs tools (behavioral / via the AI agent)

> **Execution record (2026-06-18, Claude Desktop → `staging`).** This plan was exercised through Claude Desktop against
> the `staging` console (the only reachable console with the SAF-32099 endpoints), using dual-script sim `3504301` in test
> `1781090503798.2`. The core result-first → severity-first → per-node → cross-sim flows all behaved as designed. The
> evaluation also surfaced a steering bug (`get_full_simulation_logs` told agents to "always retrieve" logs for
> stopped/no-result sims) plus an `IndexError` and a missing cap flag — all fixed in **Phase 9**. Full record, demo
> profile, verified flows, and findings→disposition: see **`prd.md` §10**.

Goal: verify the AI agent that consumes this MCP follows the intended **result-first, logs-last** investigation flow,
picks the **right** log tool, and uses the filters smartly. This tests the *tool descriptions / steering*, not the API
(API-level checks live in `manual-tests.md`).

How to run: issue each prompt to the agent (HELM via mcp-proxy) against a console whose `data` service has the
SAF-32099 endpoints. Observe the actual MCP tool calls (names + arguments + order). Score against "Expected tools" and
"Must NOT call". A test passes only if the agent both calls the right tools AND avoids the wrong ones.

## Setup — pick real ids first (use the agent or get_* tools)
- `TEST_ID` — a recent test (`get_tests`).
- `FAILED_SIM` — a simulation that ended missed/failed/no-result (`get_test_simulations` status_filter=missed).
- `SUCCESS_SIM` — a prevented/stopped/logged simulation.
- `DUAL_SIM` — a dual-script attack (exfil / infiltration / lateral movement) → has distinct attacker & target nodes.
- `OLD_SIM` — an old-format simulation if available (its result reports `logsEmbedded=true`). Optional.

---

## A. Result-first — logs must NOT be pulled

| # | Prompt to the agent | Expected tools (in order) | Must NOT call | Pass criteria |
|---|---------------------|---------------------------|---------------|---------------|
| A1 | "What's the status and result of simulation `FAILED_SIM`?" | `get_test_simulation_details` | any `*_logs` tool | Answers from the result/`finalStatus` + steps alone; no logs call |
| A2 | "Summarize what happened in simulation `SUCCESS_SIM` — which steps ran?" | `get_test_simulation_details` | any `*_logs` tool | Reads `dataObj…SIMULATION_STEPS`; no logs call |
| A3 | "Did simulation `FAILED_SIM` drift from the previous run?" | `get_test_simulation_details` (include_drift_info=True) | any `*_logs` tool | Uses drift info, not logs |

## B. Escalate to logs only when the result is insufficient (severity-first)

| # | Prompt | Expected tools (in order) | Must NOT call | Pass criteria |
|---|--------|---------------------------|---------------|---------------|
| B1 | "Investigate the root cause of the failure in simulation `FAILED_SIM` — dig into the logs if the result isn't enough." | `get_test_simulation_details` → `get_paginated_simulation_logs(simulation_id=FAILED_SIM, min_level=ERROR)` (or `levels=ERROR`) | `search_simulation_logs`; `get_full_simulation_logs` (unless logsEmbedded=true) | Details first; logs call starts at ERROR severity, single sim |
| B2 | "Those errors aren't enough — what INFO-level context preceded them in `FAILED_SIM`?" | `get_paginated_simulation_logs(simulation_id=FAILED_SIM, min_level=INFO)` | — | Widens severity to INFO only on the follow-up |
| B3 | "Deep-dive `SUCCESS_SIM` execution logs." | `get_test_simulation_details` → `get_paginated_simulation_logs(simulation_id=SUCCESS_SIM, min_level=INFO)` | starting at DEBUG | Success path starts at INFO, not DEBUG |
| B4 | "Get the next page of those logs." | `get_paginated_simulation_logs(…, page=2)` | — | Increments `page`, keeps same filters |

## C. Pick the right tool — old-format routing (logsEmbedded)

| # | Prompt | Expected tools | Must NOT call | Pass criteria |
|---|--------|----------------|---------------|---------------|
| C1 | (OLD_SIM) "Show me the execution logs for simulation `OLD_SIM`." | `get_test_simulation_details` (sees `logsEmbedded=true`) → `get_full_simulation_logs` | `get_paginated_simulation_logs` / `search_simulation_logs` | Routes to full-logs because logs aren't in the index |
| C2 | "I need the entire ~40KB raw log blob for `FAILED_SIM`." | `get_full_simulation_logs` | paginated/search | Recognizes "full blob" → full-logs tool |
| C3 | (No prior details call) "Paginate the logs for `OLD_SIM`." → returns empty | `get_paginated_simulation_logs` → (empty + hint) → `get_full_simulation_logs` | — | Honors the empty-result hint and falls back |

## D. Per-node investigation (node_id)

| # | Prompt | Expected tools | Pass criteria |
|---|--------|----------------|---------------|
| D1 | "For the dual-script attack `DUAL_SIM`, show me only the ATTACKER side's error logs." | `get_test_simulation_details` (reads `attackerNodeId`) → `get_paginated_simulation_logs(simulation_id=DUAL_SIM, node_id=<attackerNodeId>, levels=ERROR)` | `node_id` set to the attacker node id from the result |
| D2 | "Now just the TARGET node's logs for `DUAL_SIM`." | `get_paginated_simulation_logs(simulation_id=DUAL_SIM, node_id=<targetNodeId>)` | `node_id` = target node id |

## E. Cross-simulation / fleet-wide search

| # | Prompt | Expected tools | Pass criteria |
|---|--------|----------------|---------------|
| E1 | "Across all simulations in the last 24 hours, find every ERROR mentioning 'timeout'." | `search_simulation_logs(levels=ERROR, message_contains=timeout, start_time=<24h ago>)` (no `simulation_ids`) | Cross-sim tool; tight filters; no jobIds scope |
| E2 | "How many simulations hit that timeout error in the last day?" | `search_simulation_logs(...)` then dedupe distinct `jobId` | Agent counts distinct `jobId`s (not raw line `total`); ideally notes the ~10k caveat |
| E3 | "Compare the errors of simulations `SIM_A` and `SIM_B`." | `search_simulation_logs(simulation_ids="SIM_A|SIM_B", levels=ERROR)` (or two paginated calls) | Scopes to the two ids |

## F. Filter fluency

| # | Prompt | Expected tools | Pass criteria |
|---|--------|----------------|---------------|
| F1 | "Show me only warnings and errors for `FAILED_SIM`." | `get_paginated_simulation_logs(simulation_id=FAILED_SIM, levels="WARNING\|ERROR")` | Uses explicit `levels`, pipe-delimited |
| F2 | "Show the raw command OUTPUT (not trace logs) for `FAILED_SIM`." | `get_paginated_simulation_logs(simulation_id=FAILED_SIM, log_type=OUTPUT)` | `log_type=OUTPUT` |
| F3 | "Show `FAILED_SIM` logs newest-first." | `get_paginated_simulation_logs(simulation_id=FAILED_SIM, sort_order=desc)` | `sort_order=desc` |
| F4 | "Include DEBUG lines for `FAILED_SIM`." | `get_paginated_simulation_logs(simulation_id=FAILED_SIM, min_level=DEBUG)` (or levels incl. DEBUG) | DEBUG only when explicitly asked |

## G. Guardrails (negative)

| # | Prompt | Expected behavior | Pass criteria |
|---|--------|-------------------|---------------|
| G1 | "Give me 5000 log lines per page for `FAILED_SIM`." | Tool errors (page_size ≤ 1000) | Agent reports the limit, retries with ≤1000 — doesn't loop |
| G2 | "Get me page 50 at 1000 per page." | Deep-page ceiling error (~10k) | Agent surfaces the hint and narrows filters instead of paging deeper |

---

## Scoring
- **Pass**: right tools, right order, right args, and none of the "Must NOT call" tools.
- **Soft-fail (steering tweak)**: correct answer but the agent jumped to logs when result+steps would do (A/B) → tighten
  the relevant tool description.
- **Hard-fail**: wrong tool for old-format (C), ignored `node_id` (D), counted raw `total` as simulations (E2),
  or looped on a guardrail error (G).

Record per row: tools actually called (with args), pass/soft/hard, and any description wording that misled the agent.
The soft-fails are the valuable output — they tell us exactly which description line to sharpen.
