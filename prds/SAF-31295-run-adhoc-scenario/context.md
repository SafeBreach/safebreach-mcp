# SAF-31295: Context

## Status: Phase 6: PRD Created

## Ticket
- **ID**: SAF-31295
- **Title**: MCP Studio: Add run_adhoc_scenario tool for ad-hoc attack execution
- **Type**: Task
- **Assignee**: Yossi Attas
- **Team**: AI Tools
- **Project**: SAF

## Objective
Add a new dedicated MCP tool `run_adhoc_scenario` to the Studio Server that allows AI agents to construct and execute ad-hoc scenarios from a list of explicit playbook attack IDs, with intelligent simulator selection and multi-step grouping by attack phase.

## Investigation Findings

### Repository: safebreach-mcp

#### Existing run_scenario Architecture
- **Business logic**: `safebreach_mcp_studio/studio_functions.py:2321` — `sb_run_scenario()`
- **MCP tool wrapper**: `safebreach_mcp_studio/studio_server.py:1095`
- **7 parameters**, 66-line tool description (3.9x the 32-tool average of 16.8 lines)
- **3 response modes**: `not_ready`, `dry_run`, `queued`
- **6-phase control flow**: validate → lookup → augment → diagnose → statistics → queue
- **Three-turn workflow**: diagnostic → dry_run preview → execute (for non-ready scenarios)

#### Key Helper Functions (Reusable)
| Function | Location | Purpose |
|---|---|---|
| `_get_scenario_statistics()` | studio_functions.py:2221 | Statistics API pre-flight — works on any steps array |
| `_summarize_constraints()` | studio_functions.py:2120 | Per-attack constraint breakdown (14 reason codes) |
| `_summarize_constraints_aggregated()` | studio_functions.py:2171 | Grouped constraint summary |
| `_build_attack_name_map()` | studio_functions.py:2106 | Attack ID → name resolution (cross-server) |
| `CONSTRAINT_REASON_DESCRIPTIONS` | studio_functions.py:2046 | 14 constraint reason codes (fixable vs not) |
| `ATTACK_PHASE_RECOMMENDATIONS` | studio_functions.py:1827 | Phase → attacker role mapping |
| `_get_step_filter_recommendation()` | studio_functions.py:1880 | 5-tier heuristic for filter recommendation |

#### Queue API Details
- **Endpoint**: `POST /api/orch/v4/accounts/{id}/queue?enableFeedbackLoop=true&retrySimulations=true`
- **Statistics**: `POST /api/orch/v1/accounts/{id}/plan/statistics?limit=500000&includeDisabled=true`
- **Payload**: `{"plan": {"name": ..., "steps": [...], "systemTags": [], "actions": [...], "edges": [...]}}`
- **DO NOT** use `"draft": True` (that is for studio draft attacks only)

#### attacksFilter Schema
The `playbook` key allows explicit attack ID selection:
```json
{"playbook": {"operator": "is", "values": [10000298, 10000291], "name": "playbook"}}
```
Each filter key requires three fields: `operator`, `values`, `name` (must match key).

#### Attack Phase → Role Mapping
| Phase | Type | attackerFilter needed |
|---|---|---|
| 5 | Host-level | Same as target |
| 0 | Exfiltration | `role=isExfiltration` |
| 1, 2 | Infiltration | `role=isInfiltration` |
| — | AWS Cloud | `role=isAWSAttacker` |
| — | Azure Cloud | `role=isAzureAttacker` |
| — | GCP Cloud | `role=isGCPAttacker` |
| — | Web App | `role=isWebApplicationAttacker` |

#### Existing Precedent: run_studio_attack
- `studio_functions.py:1065` — runs a single DRAFT attack
- Uses same queue API endpoint
- Constructs single step with `attacksFilter.playbook` + simulator filters
- Uses `"draft": True` and `retrySimulations=false` (distinct from scenario execution)

#### Tool Complexity Baseline (32 tools across 5 servers)
- Average parameters: 6.3 per tool
- Average description: 16.8 lines
- `run_scenario` is the most complex: 7 params, 66-line description
- New tool targets: 6 params, ~30-line description

#### Rate Limiting Infrastructure
- `check_limit(caller_id, tool_name)` — before mutating API call
- `record_action(caller_id, tool_name)` — after success
- Dry-run/validation paths do NOT count against limit

## Problem Analysis

### Core Problem
AI agents currently cannot construct and execute ad-hoc test scenarios from arbitrary attack combinations. They can only run pre-existing OOB or custom scenarios (`run_scenario`) or single draft attacks (`run_studio_attack`). This gap prevents use cases like:
- Re-running specific historic simulations on exact simulators
- Testing arbitrary attack combinations without pre-creating a scenario
- Quick ad-hoc validation of specific attacks against specific targets

### Design Challenge: Smart Inference
The tool must balance two competing goals:
1. **Maximize coverage**: ensure as many attacks as possible produce non-zero simulations
2. **Minimize explosion**: prevent combinatorial blow-up where attacks run on every compatible simulator

Solution: Level 2 statistics-informed inference with mandatory dry_run preview. Role-based attacker filters provide deterministic narrowing; `dry_run=True` default ensures user reviews predicted counts before committing.

### Key Design Decision: Dedicated Tool
Creating a separate `run_adhoc_scenario` rather than extending `run_scenario` because:
- Different interaction pattern (2-turn vs. 3-turn)
- Different user intent ("run these attacks" vs. "run that scenario")
- Avoids pushing the already-most-complex tool past LLM reliability thresholds
- Enables independent feature evolution

### Risks
- **Cross-server dependency**: Attack phase classification requires playbook cache data
- **Statistics API latency**: Pre-flight adds ~2-5s per call
- **Step splitting complexity**: Per-attack simulator overrides can fragment steps significantly

## Brainstorming Decisions

### Step Grouping: One Attack Per Step (Simplified)
**Decision:** Use one attack per step instead of phase-based grouping.
- Eliminates attack classification logic entirely
- Each attack gets its own targetFilter/attackerFilter — trivial simulator_overrides mapping
- Parallel fan-out DAG ensures concurrent execution (no sequential bottleneck)

### DAG Topology: Linear Sequential (proven pattern)
**Decision:** Use linear sequential DAG (same as `run_scenario`) for now.
- Proven pattern already in production
- Parallel fan-out DAG validated at API level (accepted, RUNNING, cancellable)
  but completion not verified due to console load during experiments
- Sequential execution may be slower for many attacks but is reliable
- **Future optimization:** Switch to parallel fan-out DAG once completion is verified

### Step Ordering: Arbitrary (insertion order)
Steps execute in the order attacks are provided. No fixed semantic ordering.

### Cross-Server Dependency: Direct Python Import
Same pattern as `_build_attack_name_map()` — import from playbook module, reuse cache.

### Helper Extraction: Extract as Part of This Task
Create `_submit_to_queue()` and `_build_parallel_dag()` / `_build_linear_dag()` shared helpers.
Refactor `sb_run_scenario` and `sb_run_studio_attack` to use them.
