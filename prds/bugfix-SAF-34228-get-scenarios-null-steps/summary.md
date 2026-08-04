# Ticket Summary: SAF-34228

## Overview

**Mode**: Improving existing
**Project**: SAF
**Repositories**: `SafeBreach/safebreach-mcp` (GitHub)
**Branch**: `bugfix/SAF-34228-get-scenarios-null-steps`

---

## Current State

**Summary**: `test_mcp_operation[list_simulations]: get_scenarios crashes with NoneType len() on null steps field`

The ticket is accurate and well-investigated — the root cause, the offending code, the non-regression
finding, and the exact data trigger (2 of 475 scenarios created with `steps: null` on 2026-07-29) are
all already established. Two things it does not cover:

1. It treats the crash as the whole defect. The `TypeError` is only the trigger; the reason a
   two-record data anomaly took down the entire tool is that `sb_get_scenarios` maps all 475 records
   inside one `try` under a broad `except Exception`, so any single unmappable record discards the
   other 474 and returns an error payload instead of a listing.
2. It leaves the data question and the MCP-robustness question entangled. They should be decoupled:
   whether `steps: null` is legal is for Noam Sagiv to rule on; the MCP must not fail this way either
   way, and that fix should not wait on the data decision.

---

## Investigation Summary

### safebreach-mcp

- Both cited sites confirmed present on current `main` (ticket cites tag `1.8.0`): `config_types.py:197`
  in `get_reduced_scenario_mapping`, `:230` in `get_reduced_plan_mapping`.
- `len()` is the **only** crash point for this record shape. The two other helpers that consume `steps`
  already tolerate `None`: `compute_is_ready_to_run` (`:129-131`, `if not steps: return False`) and
  `_compute_total_attack_count` (`:149-157`, `if not steps: return 0`). The ticket's suggested fix does
  therefore resolve the reported crash.
- The safe idiom is already this repo's own convention — the same file uses it elsewhere, as does
  `queue_state.py:103` (`entry.get('steps') or []`) and the `tags` handling the ticket cites.
  `len(x.get(k, []))` is the outlier, not the norm.
- `sb_get_scenarios` (`config_functions.py:620-632`, `except` at `:673-678`) has no per-record
  isolation — the structural cause of the total-outage blast radius.
- The repo already has an established convention for incomplete data: never drop silently, count what
  was excluded, surface the count top-level, warn via `hint_to_agent` (`_bulk_result_summary` in
  `playbook_functions.py:580-617`; `hidden_no_result_drift_count` in `data_functions.py:2055-2147`;
  `total_capped` in `data_types.py:707-767`). The fix copies this rather than inventing a pattern.
- The error-dict return style is used by only 2 of 34 public `sb_*` functions
  (`config_functions.py:132`, `:676`); the other 29 raise or propagate. Two tests assert the dict
  (`test_config_functions.py:284`, `:658`), so it is retained for global failures and not changed here.

Relevant files: `safebreach_mcp_config/config_types.py`, `safebreach_mcp_config/config_functions.py`,
`safebreach_mcp_config/tests/test_config_functions.py`, `safebreach_mcp_config/tests/test_config_types.py`

---

## Problem Analysis

### Problem Description

`dict.get(key, default)` returns `default` only when the key is **absent**. When the key is present
with value `null`, it returns `None`. `get_reduced_scenario_mapping` and `get_reduced_plan_mapping`
compute `"step_count": len(scenario.get("steps", []))`, so a record with `"steps": null` raises
`TypeError: object of type 'NoneType' has no len()`.

Because the whole mapping pass sits inside one `try`/`except Exception`, that single record's failure
is converted into a whole-tool failure: `get_scenarios` returns
`{"error": "Failed to get scenarios: object of type 'NoneType' has no len()", "console": "..."}` for
every call against the console, and the 473 healthy scenarios plus all custom plans are discarded.

### Impact Assessment

- **Agent-facing**: `get_scenarios` is unusable on any console holding one malformed record. The agent
  receives a string in an `error` key, so it cannot route around the problem or tell the user
  "473 scenarios available, 2 unreadable" — the tool simply appears to be down. Downstream flows that
  begin with scenario discovery (notably `run_scenario`) are blocked.
- **CI**: the scheduled `Automation-staging-sanity` pipeline fails deterministically
  (builds #1862, #1863+) on a response-shape assertion.
- **Recurrence**: the failure mode is generic. Any future unanticipated upstream shape in any mapped
  field reproduces the same total outage, so fixing only `steps` leaves the blast radius intact.

### Risks & Edge Cases

- **All records malformed** — must not report success with an empty list; needs an explicit signal.
- **Log noise** — a per-record `except` could emit hundreds of warnings; log per record at `warning`
  once and keep the aggregate in the response.
- **Unbounded skip list** — must not dump hundreds of IDs into the response; cap the sample.
- **Cache interaction** — the scenario/plan caches hold *raw* API payloads, so a malformed record
  persists for the cache TTL. Behavior must be stable across cached and uncached reads.
- **Contract stability** — new fields must be additive; the two tests asserting `"error" in result`
  for genuine API failures must keep passing.

---

## Proposed Ticket Content

### Summary (Title)

`get_scenarios: null steps crashes the whole listing — make step_count null-safe and isolate per-record mapping failures`

### Description

```markdown
### Background

The MCP `get_scenarios` tool (config server) fails on `staging.sbops.com` with
`Failed to get scenarios: object of type 'NoneType' has no len()`, breaking the scheduled
`Automation-staging-sanity` pipeline deterministically from build #1862 onward. Root cause, code
location, non-regression status and the exact data trigger are established in the original
description and comment: 2 of 475 scenarios were created with `steps: null` on 2026-07-29.

### Technical Context

* `dict.get(key, default)` returns `default` only when the key is MISSING, not when it is present
  with value `null`. `len(scenario.get("steps", []))` therefore raises `TypeError` on such a record.
* Confirmed still present on `main`: `config_types.py:197` (`get_reduced_scenario_mapping`) and
  `:230` (`get_reduced_plan_mapping`).
* `len()` is the only crash point for this shape — `compute_is_ready_to_run` and
  `_compute_total_attack_count` already guard with `if not steps`.
* The safe idiom is already the repo's convention (`queue_state.py:103`, the `tags` handling, and the
  two helpers above); these two `len()` calls are the outlier.
* `sb_get_scenarios` maps all records inside a single `try` under a broad `except Exception`
  (`config_functions.py:620-632`, `:673-678`), so one unmappable record discards all the others.

### Problem Description

* A single malformed record out of 475 blacks out the entire scenario catalog for the console; the
  473 healthy scenarios and all custom plans are discarded.
* The agent receives an error string rather than a degraded result, so it cannot route around the
  problem or report partial availability — the tool appears down. Scenario-discovery-dependent flows
  such as `run_scenario` are blocked.
* The failure mode is generic: fixing only `steps` leaves the same total-outage blast radius for the
  next unanticipated upstream shape.
* Whether `steps: null` is a legal scenario shape is a separate data question (assigned to Noam
  Sagiv). The MCP must not fail this way under either answer, and this fix does not depend on it.

### Affected Areas

* safebreach-mcp: `safebreach_mcp_config/config_types.py` (`get_reduced_scenario_mapping`,
  `get_reduced_plan_mapping`)
* safebreach-mcp: `safebreach_mcp_config/config_functions.py` (`sb_get_scenarios`)
```

### Acceptance Criteria

```markdown
* `get_reduced_scenario_mapping` and `get_reduced_plan_mapping` return `step_count: 0` for a record
  whose `steps` key is present with value `null`, and do not raise.
* `get_scenarios` returns the healthy records when one or more records cannot be mapped, instead of
  failing the whole call.
* The response reports how many records were skipped, and `hint_to_agent` states the count so the
  agent can disclose partial results to the user.
* When every record fails to map, the response makes that explicit rather than reporting an empty
  but successful listing.
* Genuine global failures (auth, network, RBAC) still surface as they do today — the existing
  `{"error": ...}` contract and the tests asserting it are unchanged.
* Regression test reproducing the exact reported payload (`"steps": null`) fails before the fix and
  passes after.
* The full existing suite passes.
```

### Suggested Labels/Components

- Labels (existing, keep): `CTEM-dev`, `automation`, `prod`, `test-failure`
- No component change

---

## Out of Scope (recorded, not proposed as work here)

A repo-wide audit run during investigation found ~40 further null-unsafe expressions and 11 mapping
sites with the same all-or-nothing structure, including two arguably more severe than this bug
(`get_minimal_simulator_mapping` at `config_types.py:41,69-77`; `run_scenario`'s evaluate path at
`studio_functions.py:2940,2964`, which the same two staging records likely also break). These are
retained in `context.md` to seed separate tickets and are deliberately excluded from SAF-34228.
