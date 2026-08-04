# PRD: SAF-34228 — `get_scenarios` crashes on a scenario with `steps: null`

- **Ticket**: [SAF-34228](https://safebreach.atlassian.net/browse/SAF-34228) (Bug, Medium)
- **Branch**: `bugfix/SAF-34228-get-scenarios-null-steps` (off `main` — this repo has no `develop`)
- **Repo**: `SafeBreach/safebreach-mcp`
- **Context**: [context.md](./context.md) | **Ticket content**: [summary.md](./summary.md)

---

## 1. Problem

`dict.get(key, default)` returns `default` only when the key is **absent**. A key present with value
`null` returns `None`. Both scenario/plan mappers computed:

```python
"step_count": len(scenario.get("steps", [])),   # config_types.py:197
"step_count": len(plan.get("steps", [])),       # config_types.py:230
```

so a record with `"steps": null` raised `TypeError: object of type 'NoneType' has no len()`. Because
`sb_get_scenarios` maps every record inside one `try` under a broad `except Exception`, that single
record's failure surfaced as a whole-tool failure:

```json
{"error": "Failed to get scenarios: object of type 'NoneType' has no len()", "console": "default"}
```

2 of 475 records on `staging.sbops.com` (created 2026-07-29) trip this, breaking the
`Automation-staging-sanity` pipeline deterministically from build #1862.

## 2. Scope

**In scope**: make `step_count` null-safe in the two mapping functions the ticket names, so a stepless
scenario is projected as a scenario with zero steps.

**Out of scope**:

- The upstream content-manager write path, and auditing/repairing the staging records (with Noam Sagiv
  on the ticket).
- Any change to `sb_get_scenarios`, its error handling, or its response shape.
- Every other finding from the investigation audit recorded in `context.md`.

## 3. Solution

`config_types.py:197-200` (`get_reduced_scenario_mapping`) and `:232-234` (`get_reduced_plan_mapping`):

```python
# before
"step_count": len(scenario.get("steps", [])),
"total_attack_count": _compute_total_attack_count(scenario.get("steps", [])),
# after
"step_count": len(scenario.get("steps") or []),
"total_attack_count": _compute_total_attack_count(scenario.get("steps") or []),
```

This is the fix suggested on the ticket, and it matches the repo's existing idiom — `queue_state.py:103`
(`entry.get('steps') or []`), the adjacent `tags` handling, and `compute_is_ready_to_run` /
`_compute_total_attack_count`, which both already guard with `if not steps`.

`total_attack_count` is guarded on the same lines even though `_compute_total_attack_count(None)`
already returns `0` safely. Not a bug fix — it stops the two adjacent expressions from disagreeing
about whether `steps` can be null, which is how this defect class survives review.

### 3.1 What this produces

A `steps: null` record maps successfully and is **returned in the listing** as
`step_count: 0`, `total_attack_count: 0`, `is_ready_to_run: False`. It is not skipped, not flagged, and
not treated as an error. Verified against the two real staging records:

```
total_scenarios: 3
  A Normal Scenario          step_count=1  attacks=2  ready=True
  Adversary Propagation      step_count=0  attacks=0  ready=False
  Adversary Reconnaissance   step_count=0  attacks=0  ready=False
```

This is deliberately agnostic on the open data question: `step_count: 0` is the correct projection of a
stepless record whether or not stepless scenarios turn out to be intended. Nothing here needs revisiting
when that question is answered.

### 3.2 No contract change

Response shape, error handling and tool description are untouched. The only observable difference is
that a call which previously returned an error payload now returns the listing. Consequently no
documentation change is required — nothing in `CLAUDE.md`, `README.md` or the `get_scenarios` tool
description describes behavior that has changed.

## 4. Testing

Four unit tests in `safebreach_mcp_config/tests/test_config_types.py`:

| # | Test | Asserts |
|---|------|---------|
| T-1 | `get_reduced_scenario_mapping` with `"steps": None` | `step_count == 0`, `total_attack_count == 0`, `is_ready_to_run is False`; no raise. Fixture uses the real incident record id `278b6968-676e-4940-bbd2-59c933437238` ("Adversary Reconnaissance") |
| T-2 | `get_reduced_plan_mapping` with `"steps": None` | same, on the custom-plan mapper |
| T-3a | `get_reduced_scenario_mapping` with the `steps` key absent | `step_count == 0` — guards the pre-existing missing-key path |
| T-3b | `get_reduced_plan_mapping` with the `steps` key absent | same |

Both null tests were confirmed failing before the fix with the exact reported error
(`TypeError: object of type 'NoneType' has no len()`).

**Regression gate**: full non-e2e suite green — 1548 tests.

**Not locally reproducible end-to-end**: needs a console holding a `steps: null` record, so T-1/T-2
encode the reported payload instead. Post-merge, confirm `Automation-staging-sanity` goes green.

## 5. Implementation

Single phase, complete:

1. T-1, T-2, T-3a, T-3b written first and confirmed failing with the reported `TypeError`.
2. The two `or []` edits applied.
3. **Gate**: new tests green; full config suite green (91); full non-e2e suite green (1548).

Committed as `0749a2a`.

## 6. Definition of done

- [x] `step_count` is `0` for `steps: null` in both mappers; no raise
- [x] A stepless scenario is returned in the listing, not skipped or flagged
- [x] Missing-`steps`-key path unchanged
- [x] No response-shape, error-handling or tool-description change
- [x] T-1/T-2 fail before the fix with the exact reported error, pass after
- [x] Full non-e2e suite green (1548)
- [ ] `Automation-staging-sanity` green post-merge
- [ ] Follow-up tickets filed for the out-of-scope audit findings

## 7. Decision log

| Date | Decision |
|------|----------|
| 2026-08-04 | Scope held to the ticket. An investigation audit surfaced ~40 further null-unsafe expressions and 11 structurally identical mapping sites; excluded rather than folded in, and recorded in `context.md` to seed separate tickets. |
| 2026-08-04 | **Per-record mapping resilience considered, implemented, and reverted.** A `_map_records_resiliently` helper in `sb_get_scenarios` (skip an unmappable record, return the rest, surface `skipped_records_count` + a warning hint) was built and passing (9 tests) before being dropped. Reasons: (a) it is not needed for this bug — after §3 the stepless records map cleanly and are listed, so the reported crash and the CI failure are fixed without it; (b) it rests on the premise that a stepless scenario is malformed, which is exactly the open question, and "skip the record" is the wrong default if the shape turns out to be legal; (c) it modified a generic flow serving every scenario/plan listing, so its own risk of introducing a regression exceeded the hypothetical failure it guarded against. The structural concern is real but belongs in its own ticket with its own justification, not as a passenger on a two-line bugfix. |
| 2026-08-04 | Data question (`steps: null` legal?) left with Noam Sagiv and explicitly decoupled: §3 is correct under either answer and does not wait on it. |
