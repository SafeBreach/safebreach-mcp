# SAF-31295: Summary — run_adhoc_scenario Tool

## Title
MCP Studio: Add `run_adhoc_scenario` tool for ad-hoc attack execution

## Description

Add a new dedicated MCP tool to the Studio Server that constructs and executes ad-hoc scenarios from
explicit playbook attack IDs. The tool automatically groups attacks into steps by phase/role
requirement, infers simulator filters, validates via the statistics API, and presents a dry-run
preview before execution.

### Key Capabilities
- Accepts a list of playbook attack IDs and constructs a multi-step scenario on the fly
- Automatically groups attacks by attacker role requirement (host, infil, exfil, AWS, Azure, GCP, webapp)
- Smart inference: role-based attacker filters + statistics API validation
- Per-attack simulator overrides for exact targeting (re-run historic simulations)
- `all_connected` global override as escape hatch
- `dry_run=True` default — agent must get user confirmation before execution
- Implicit consent for partial execution (0-sim attacks skipped after user sees preview)

## Tool Interface

```python
def sb_run_adhoc_scenario(
    attack_ids: str,              # Required: comma-separated playbook IDs
    console: str = "default",
    test_name: str = None,
    all_connected: bool = False,  # Global override: all connected simulators
    simulator_overrides: str = None,  # JSON: per-attack simulator UUID mapping
    dry_run: bool = True,         # Default True: preview first
) -> Dict[str, Any]
```

### simulator_overrides Schema
```json
{
  "100": {"target": ["sim-uuid-1"]},
  "200": {"target": ["sim-uuid-1"], "attacker": ["sim-uuid-2"]},
  "300": {"target": ["sim-uuid-3"]}
}
```
- `all_connected=True` takes precedence over all overrides
- For host attacks: attacker inferred as same as target when omitted
- Attacks with identical overrides in the same phase group share a step
- Different overrides → separate steps (step splitting)

## Step Grouping Algorithm

1. **Validate**: All attack IDs exist in playbook cache (fail-fast)
2. **Classify**: Look up attack phase/type from playbook metadata
3. **Separate**: Auto pool (no overrides) vs. manual pool (has overrides)
4. **Group auto**: One step per phase group with inferred filters
5. **Group manual**: By (phase x unique override set)
6. **all_connected override**: Collapse to one step per phase, connection filter on both sides
7. **Build DAG**: Linear sequential: step1 → wait(0s) → step2 → ...

### Phase → Step Mapping

| Group | Phase | attackerFilter | targetFilter |
|---|---|---|---|
| Host-level | 5 | Same as target | connection: all_connected |
| Infiltration | 1, 2 | role=isInfiltration | connection: all_connected |
| Exfiltration | 0 | role=isExfiltration | connection: all_connected |
| AWS Cloud | — | role=isAWSAttacker | inferred |
| Azure Cloud | — | role=isAzureAttacker | inferred |
| GCP Cloud | — | role=isGCPAttacker | inferred |
| Web App | — | role=isWebApplicationAttacker | inferred |

## Interaction Flow

### Standard (2-turn minimum)
1. Agent calls with `attack_ids` → dry_run preview (default)
2. Agent presents preview to user → user confirms
3. Agent calls with `dry_run=False` → test queued

### Adjustment (3-turn)
1. Dry run preview
2. Agent calls with `simulator_overrides` + `dry_run=True` → adjusted preview
3. Agent calls with `dry_run=False` → execute

## Validation & Error Handling

- **Invalid attack IDs**: Fail-fast with list of invalid IDs
- **Total simulations = 0**: Hard refuse (ValueError)
- **Partial (some 0-sim)**: Execute viable attacks, skip 0-sim, report skipped (implicit consent)
- **Empty step after grouping**: Remove from plan, warn in response

## Rate Limiting
- `check_limit` before queue POST (after dry_run/validation early returns)
- `record_action` after successful POST
- Dry-run does NOT count against limit
- Tool name: `"run_adhoc_scenario"`

## Shared Infrastructure

**Reuse from run_scenario:**
- `_get_scenario_statistics()` — statistics API pre-flight
- `_summarize_constraints()` / `_summarize_constraints_aggregated()` — constraint diagnostics
- `_build_attack_name_map()` — attack ID → name
- `CONSTRAINT_REASON_DESCRIPTIONS` — 14 reason codes
- `ATTACK_PHASE_RECOMMENDATIONS` — phase → role mapping
- Rate limiter gates

**Extract into shared helpers:**
- `_submit_to_queue()` — queue API POST
- `_build_linear_dag()` — DAG generation (actions + edges)

**New code:**
- Attack phase classification from playbook metadata
- Step grouping algorithm (auto vs. manual, phase-based)
- Smart inference filter construction
- Simulator override parsing and step-splitting
- MCP tool wrapper with Markdown formatting

## Acceptance Criteria

1. [ ] New `run_adhoc_scenario` tool registered on Studio Server (Port 8004)
2. [ ] Accepts comma-separated attack IDs and validates all exist in playbook
3. [ ] Automatically groups attacks into steps by attacker role requirement
4. [ ] Infers role-based attacker filters per step (host/infil/exfil/cloud/webapp)
5. [ ] Calls statistics API for simulation count prediction
6. [ ] `dry_run=True` is the default — returns preview without queuing
7. [ ] `dry_run=False` submits to queue API and returns test_id
8. [ ] `all_connected=True` overrides all simulator selection with connection filter
9. [ ] `simulator_overrides` allows per-attack UUID targeting with step splitting
10. [ ] Partial execution: skips 0-sim attacks, hard-refuses if all are 0
11. [ ] Rate limiting gates follow existing pattern (check before POST, record after)
12. [ ] Unit tests for step grouping, filter construction, overrides, validation, dry_run, execution
13. [ ] E2E test against real console

## Out of Scope (Future)
- Persisting ad-hoc scenarios as custom plans
- MITRE technique ID input (T1046 → attack IDs resolution)
- Criteria-based attack selection (by type, tags, etc.)
