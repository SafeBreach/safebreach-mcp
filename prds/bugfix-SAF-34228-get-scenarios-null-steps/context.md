# Ticket Context: SAF-34228

## Status
Phase 3: Context Initialized

## Mode
Improving

## Original Ticket

- **Key**: SAF-34228 — https://safebreach.atlassian.net/browse/SAF-34228
- **Summary**: `test_mcp_operation[list_simulations]: get_scenarios crashes with NoneType len() on null steps field`
- **Type**: Bug | **Priority**: Medium | **Status**: To Do
- **Reporter**: Boris Ifraimov | **Assignee**: Noam Sagiv
- **Labels**: CTEM-dev, automation, prod, test-failure
- **Created**: 2026-07-29 | **Updated**: 2026-08-03
- **Origin**: filed automatically via `/investigate-test-failure` from a post-merge CI failure

### Description (as filed)

Failing test `tests/ui/sanity/sb_mcp/test_mcp_sanity.py::test_mcp_operation[list_simulations]` in the
scheduled `Automation-staging-sanity` pipeline against `staging.sbops.com`. The MCP `get_scenarios`
tool (config server) fails server-side with:

```
Failed to get scenarios: object of type 'NoneType' has no len()
```

Traced to `safebreach_mcp_config/config_types.py` (pinned at tag `1.8.0` via `mcp-proxy`'s
`requirements.txt`):

```python
"step_count": len(scenario.get("steps", [])),   # get_reduced_scenario_mapping
"step_count": len(plan.get("steps", [])),       # get_reduced_plan_mapping
```

`dict.get(key, default)` returns `default` only when the key is **missing** — not when the key is
present with value `null`. A record with `"steps": null` yields `None`, and `len(None)` raises
`TypeError`. `sb_get_scenarios` wraps this in a broad `except Exception`, producing the
`"Failed to get scenarios: ..."` error payload that the sanity test flags as a broken response shape.

Not a code regression — `git blame` traces the pattern to `b7ce727` (SAF-29966, 2026-04-16), with zero
commits to `config_types.py`/`config_functions.py` between tags `1.7.0` and `1.8.0`. No commits landed in
automation, craft, mcp-proxy, configuration, or safebreach-mcp between last-good build #1861
(2026-07-28 20:33 UTC) and first-bad #1862 (2026-07-29 07:32 UTC). Reproduced across builds #1862 and
#1863 — deterministic, not flaky.

Ticket's suggested fix: replace `scenario.get("steps", [])` / `plan.get("steps", [])` with
`scenario.get("steps") or []` / `plan.get("steps") or []` in both mapping functions (matching the
existing safe pattern already used for `tags`), and audit the staging `default` console for the
offending record.

CI reference: https://butler.sbops.com/job/Automation-staging-sanity/1863/

### Comment (Sebastian Altheim, 2026-07-29) — the trigger identified

Of 475 scenarios on the console, exactly 2 have `"steps": null`:

| Scenario | id | createdBy | createdAt (UTC) | updatedAt (UTC) |
|---|---|---|---|---|
| Adversary Reconnaissance | 278b6968-676e-4940-bbd2-59c933437238 | SafeBreach | 2026-07-29 06:45:57 | 07:19:06 |
| Adversary Propagation | aa0ab29d-7bb3-4b9b-8c79-b43bd9c6060c | SafeBreach | 2026-07-29 06:53:52 | 07:18:50 |

Timeline fits exactly:

```
2026-07-28 20:33  build #1861  PASS  (last good)
2026-07-29 06:45  <- Adversary Reconnaissance created
2026-07-29 06:53  <- Adversary Propagation created
2026-07-29 07:32  build #1862  FAIL  (first bad)
```

Both are the two newest records in the entire collection by nearly a week (next newest 2026-07-23).
Nothing else in the window. Assigned to Noam Sagiv to decide whether stepless scenarios are expected
or whether these two records should have steps.

## Task Scope

Two questions are entangled in this ticket and must be separated:

1. **Data question (NOT this ticket's work, assigned to Noam Sagiv)** — is `steps: null` a legal
   scenario shape? If a stepless scenario is valid, `step_count: 0` is a correct projection and the
   data is fine. If invalid, content-manager should reject it at write time.
2. **MCP resilience (this ticket's work, our repo)** — regardless of the answer above, the MCP must
   not turn one malformed upstream record into a total failure of the whole tool. This is the scope
   being prepared here.

Scope (final — deliberately narrowed to the reported bug; see note below):

1. Make `step_count` null-safe in the two mapping functions the ticket names
   (`config_types.py:197`, `:230`).
2. Make `sb_get_scenarios` survive a record it cannot map: skip it, return the rest, and surface the
   skipped count via a top-level field + `hint_to_agent`.

Explicitly out of scope:

- The upstream content-manager write path, and auditing/repairing the staging data records (on the
  ticket for Noam Sagiv).
- Every other finding in the Phase 4 audit below. The audit was run repo-wide and turned up ~40
  null-unsafe expressions and 11 structurally identical mapping sites, including two that are
  arguably more severe than this bug (`get_minimal_simulator_mapping`, and `run_scenario`'s evaluate
  path breaking on these same two records). **None of that is this ticket.** It is retained below as
  reference material to seed separate tickets, not as work items here.

**Note on the Phase 4 section**: it is broader than the scope above by design — it was an exploratory
audit, and it over-reached for a single bug ticket. Read it as background, not as a task list. The
only findings this ticket acts on are items 1-2 above.

## Repositories Under Investigation

- `/Users/sebastian.altheim/safebreach-mcp` (this repo — `SafeBreach/safebreach-mcp`, GitHub)

Branch: `bugfix/SAF-34228-get-scenarios-null-steps` (off `main`; this repo has no `develop`)

## Investigation Findings

### Pre-investigation (verified directly on `main`, before Phase 4 fan-out)

The ticket's code citations are against tag `1.8.0`; all were re-verified against current `main`.

1. **Both cited sites still present**: `config_types.py:197` (`get_reduced_scenario_mapping`) and
   `config_types.py:230` (`get_reduced_plan_mapping`).

2. **`len()` is the only crash point for this record shape.** The two other helpers that consume
   `steps` already tolerate `None`:
   - `compute_is_ready_to_run` (`config_types.py:129-131`) — `steps = scenario.get('steps', [])`
     followed by `if not steps: return False`
   - `_compute_total_attack_count` (`config_types.py:149-157`) — `if not steps: return 0`

   So the ticket's suggested fix does resolve this specific crash. It also means the safe pattern is
   **already this codebase's own convention** (also `queue_state.py:103`, `entry.get('steps') or []`,
   and the `tags` handling the ticket mentions). `len(x.get(k, []))` is the outlier, not the norm.

3. **The ticket misses two further instances of the identical pattern:**
   - `safebreach_mcp_studio/studio_functions.py:2964` — `len(scenario.get('steps', []))` in
     `run_scenario`'s evaluate path. Worse, `:2940` passes `scenario['steps']` directly into
     `_get_scenario_statistics()`, which has no null guard (`:2400-2425`). The same two staging
     records are therefore likely broken for **evaluate/run**, not just listing — a larger blast
     radius than the reported symptom, and outside the ticket's stated fix.
   - `safebreach_mcp_studio/studio_types.py:336` — `len(execution.get('simulationEvents', []))`,
     same shape, awaiting the same trigger.

4. **The all-or-nothing failure mode is the deeper defect.** `sb_get_scenarios`
   (`config_functions.py:620-632`) maps all 475 records inside a single `try`, under a broad
   `except Exception` (`:673-678`) that collapses any per-record mapping error into a whole-tool
   failure returning `{"error": ..., "console": ...}`. Consequences:
   - One malformed record out of 475 blacks out the entire scenario catalog for the console; the 473
     healthy records are discarded.
   - The agent receives a string in an `error` key, so it cannot route around the problem or report
     "473 scenarios, 2 unreadable" — it only sees the tool as down.
   - The failure does not present as an exception, unlike the rest of the repo's tools, which is
     precisely why CI caught it as a *response-shape* assertion rather than an error.
   - It will recur with the next unanticipated upstream shape. Patching `len()` sites per incident is
     a treadmill.
   - The same error-dict pattern exists at `config_functions.py:132` (`get_console_simulators`).

### Phase 4 (parallel repo audit)

Two parallel Explore audits: (A) null-unsafe projection patterns repo-wide, (B) error-handling
contract + resilience precedent + structural blast radius. High-impact claims were re-verified by hand
against `main` (noted below); the rest are agent-reported and marked as needing confirmation before
any code change relies on them.

#### A. There is no central fix point — `map_reduced_entity` propagates nulls

**VERIFIED** (`config_types.py:34`, and the twin at `data_types.py:61`):

```python
return {new_key: entity[old_key] for new_key, old_key in mapping.items() if old_key in entity}
```

The `if old_key in entity` guard makes it **KeyError-safe but null-propagating**: a present-but-`null`
upstream value is copied through verbatim, relocating the defect one hop downstream to whatever next
calls `.get(new_key, default)` on the reduced dict. This is the confirmed bug's shape, indirected
through a rename.

One counter-example exists: `data_types.py:422` `map_security_control_event` **does** drop nulls
(`if value is not None`). It is a one-off used only for security-control events. So the codebase
already contains the null-safe mapping idea but has not generalized it.

**Implication**: every call site must be patched individually, OR `map_reduced_entity` gains a
null-drop to match `map_security_control_event`. The latter is a contract change (turns "key present
with null" into "key absent") and needs its own decision — not a free win.

#### B. Highest-severity finding is NOT in this ticket: `get_minimal_simulator_mapping`

**VERIFIED** (`config_types.py:37-85`). Worse than the reported bug:

- **`:41`** — `map_reduced_entity(simulator_entity['nodeInfo']['MACHINE_INFO']['OS'], ...)`: a triple
  unguarded subscript. Any simulator missing `nodeInfo`, or with `nodeInfo`/`MACHINE_INFO`/`OS`
  explicitly `null` (a disconnected or newly-registered agent that has not reported system info),
  crashes the **entire** `get_console_simulators` listing for that console.
- **`:69-77`** — nine consecutive unguarded direct subscripts (`labels`, `isEnabled`, `id`, `name`,
  `isConnected`, `isCritical`, `externalIp`, `internalIp`, `version`). Zero `.get()` calls. Any record
  missing any one field raises `KeyError` and takes down the whole listing.
- `get_full_simulator_mapping:96-100` guards only `INSTALLED_SOFTWARE`, and only for `KeyError` — a
  `null` intermediate raises `TypeError`, which that handler does not catch. It also calls the
  unguarded minimal mapping first (`:93`), so the guard is moot.

This is the same bug class as SAF-34228, in the same server, on the most frequently listed entity in
the product — and it is one malformed simulator record away from an identical incident.

#### C. Additional null-unsafe sites (agent-reported, high-confidence, spot-checked)

Same tool as the ticket (`get_scenarios` / `get_scenario_details`):

- `config_types.py:182-184` — `for cat_id in scenario.get('categories', [])`: null `categories`
  raises `TypeError`. Same function, same listing, missed by the ticket.
- `config_types.py:196` — `"name": scenario.get("name")` (no default) feeds
  `filter_scenarios_by_criteria:254` and `apply_scenario_ordering:298,305`, all doing
  `s.get('name', '').lower()` → `AttributeError` on a null name. **`order_by='name'` is the default**,
  so this is on the default path.
- `config_types.py:503-511` + `_simplify_step:381-383` — the detail-view sibling of the list-view bug,
  reachable from `get_scenario_details`.
- `config_functions.py:183` — `logger.info(..., simulator['name'])` on a **raw** record, before mapping.

Elsewhere (proves the pattern is a repo-wide inconsistency, not a one-off):

- `data_types.py:194` — `"ALM" in test_summary_entity.get('systemTags', [])` → `TypeError` on null.
  **VERIFIED**, and its sibling `get_reduced_queued_test_mapping:162` does it correctly
  (`pending_entry.get('systemTags') or []`) — right pattern, same file, missed here.
- `data_functions.py:405,410` and `_apply_ordering:447` — `t.get('status','').lower()` /
  `t.get('name','').lower()` unguarded, while `:241` in the *same file* is guarded as
  `(t.get('status','') or '').lower()`. **VERIFIED.**
- `data_functions.py:1304-1343` — six unguarded chained `.get('fields', {}).get(...)` on **raw** SIEM
  events in `_apply_security_control_events_filters`.
- `data_types.py:893-920`, `1047-1051`, `1120` — unguarded `record.get("from"/"to", {})` chains on raw
  drift records; direct sibling of the confirmed bug.
- `studio_types.py:340` — `_parse_simulation_steps(execution.get('simulationEvents', []))`: a
  **second** crash point on the same field as `:336`. Patching only the `len()` at `:336` leaves this.
- `studio_functions.py:1993` — `_apply_step_overrides` does `len(steps)` with no `if not steps` guard,
  unlike its siblings `compute_scenario_readiness`/`diagnose_scenario_readiness`.

#### D. Error contract: the error-dict style is the exception, not the rule

Agent-inventoried across 34 public `sb_*` functions:

| Style | Count | Where |
|---|---|---|
| (a) returns `{"error": ...}` | **2** | `config_functions.py:129-134` (`get_console_simulators`), `:673-678` (`get_scenarios`) |
| (b) raises / propagates | **29** | all of data, playbook, studio, plus `config_functions.py:331` |
| (c) inline narrow "not-found" dicts *inside* the try | 3 | deliberate expected-condition returns; those functions still re-raise unexpected errors |

Plus a fourth flavor at the **server** layer, **VERIFIED**: `playbook_server.py` (`:167-169`, `:286-288`,
`:348-350`) and `studio_server.py` (12 sites) wrap every tool in `except Exception: return f"Error ..."`,
returning a formatted **string** — swallowing even deliberate `ValueError`s from the function layer.
`config_server.py`/`data_server.py` are thin pass-throughs that let exceptions propagate to FastMCP.

`ToolError` precedent exists (`rate_limiter.py:90,106`; `safebreach_base.py:204`) but is scoped to
rate limiting, not data/mapping errors.

**Constraint for the fix**: two existing tests lock the error-dict contract in —
`test_config_functions.py:284` (`test_sb_get_console_simulators_error`) and `:658`
(`test_api_failure_returns_error_dict`) assert `"error" in result`. A fix must either deliberately
change that contract (updating these tests) or keep the error dict for the *fully unusable* case while
adding new fields for the *partially usable* case.

#### E. In-repo precedent to copy for graceful degradation (do not invent a new pattern)

The repo already has a consistent convention for incomplete data: **never silently drop; count what
was excluded; surface the count in a top-level field; add a `hint_to_agent` naming the number.**

Best structural match — `_bulk_result_summary` (`playbook_functions.py:580-617`): returns
`succeeded` / `failed_count` / `failures[]` plus a quantifying `hint_to_agent`.

Also: `sb_get_test_drifts` (`data_functions.py:2055-2147`) — `continue` on an excluded record plus
`hidden_no_result_drift_count` and a loud `WARNING:` hint; `get_simulation_logs_mapping`
(`data_types.py:707-767`) — `total_capped` flag + hint; best-effort enrichment isolated behind a
sentinel-returning helper (`user_lookup.py:31-86` → `{}`/`None`; `config_functions.py:440-442`,
`:487-489`; `data_functions.py:714-716` → `0`).

#### F. Structural blast radius: 11 sites share the all-or-nothing shape

Mapping an entire upstream list via one comprehension/loop, with no per-record isolation:

| # | Site | Feeds |
|---|---|---|
| 1-2 | `config_functions.py:625-627`, `:632` | `get_scenarios` — **the reported bug** |
| 3 | `config_functions.py:182-184` | `get_console_simulators` |
| 4 | `data_functions.py:334-336` | `get_tests` |
| 5-6 | `data_functions.py:803`, `1038-1040` | `get_simulations` |
| 7 | `data_functions.py:1411-1413` | `get_security_controls_events` |
| 8 | `data_functions.py:3579-3581` | `get_simulation_lineage` — **no try at all**, raises uncaught |
| 9-10 | `playbook_functions.py:165-168`, `324-327` | `get_playbook_attacks`, `..._by_tags` |
| 11 | `studio_functions.py:1516-1518` | `get_studio_attack_latest_result` |

Only sites 1-3 currently degrade to an error dict; the other 8 surface as raw propagated exceptions.

## Problem Analysis
(Phase 5)

## Proposed Improvements
(Phase 6)
