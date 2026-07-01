# PRD: playbook_attack_id_filter silently returns empty — SAF-32805

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | `get_test_simulations` attack-id / attack-name filters silently return empty (wrong key + int/str), producing false-negative drift results |
| **JIRA** | SAF-32805 (relates to SB-36136 — Travelers HELM credit burn) |
| **Task Type** | Bug |
| **Component** | `safebreach_mcp_data` (Data Server) |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Implemented (filter fix + empty-match guard) |
| **Last Updated** | 2026-06-29 |
| **Branch** | `feature/SAF-32805-fix-playbook-attack-id-filter` |

## 2. Solution Description

### Root cause (corrects the ticket's stated mechanism)

The ticket describes the cause as an int/str mismatch on `s.get('playbookAttackId') == playbook_attack_id_filter`. That is incomplete. `_apply_simulation_filters` runs on **reduced** simulation entities (`get_reduced_simulation_result_entity`), whose keys are snake_case (`playbook_attack_id` from `moveId`, `playbook_attack_name` from `moveName`). The camelCase keys `playbookAttackId` / `playbookAttackName` **do not exist** on those entities, so `s.get('playbookAttackId')` is `None` and the comparison is always `False` — the filter returns `[]` for every query.

Consequently the ticket's proposed fix, `str(s.get('playbookAttackId')) == str(playbook_attack_id_filter)`, would **still fail** (`str(None)` never matches). The real fix needs the correct key **and** type coercion (since `moveId` is an int and the filter arg is a str). Both the id and name filters are affected.

This has been broken since the initial commit `7182b18` (2025-07-29) — the filters never matched once. In SB-36136 it produced a false "0 detection drifts / new scenario additions" conclusion (true answer: real drifts incl. #4029, #2195); only caught when the user manually supplied counterexample sim `1316205` (attack #3819).

### Chosen Solution

- Fix both filters to the correct snake_case keys, with str-coercion on the id and None-safety on the name:
  ```python
  if playbook_attack_id_filter:
      filtered = [s for s in filtered
                  if str(s.get('playbook_attack_id')) == str(playbook_attack_id_filter)]
  if playbook_attack_name_filter:
      filtered = [s for s in filtered
                  if playbook_attack_name_filter.lower() in (s.get('playbook_attack_name') or '').lower()]
  ```
- Empty-match guard: when filters matched 0 in a **non-empty** test, `sb_get_test_simulations` returns a `hint_to_agent` warning not to infer the attack/criteria is absent (distinguishes "filtered to empty" from "nothing to filter") — directly countering the SB-36136 failure where the agent inferred absence from a false zero.

## 3. Core Feature Components

- `data_functions.py` `_apply_simulation_filters` — correct keys + coercion + None-safety.
- `data_functions.py` `sb_get_test_simulations` — empty-match guard hint.
- `test_data_functions.py` — tests updated from the wrong (camelCase) shape to the real reduced shape; added int-id coercion test, end-to-end id match, and the guard test.

## 4. Tests & Verification

- Unit: filter matches int `playbook_attack_id` via str arg; name filter on snake key; guard hint on empty match in non-empty test. Full data suite green (477 passed).
- Live (pentest01, test `1782728041622.137`): `playbook_attack_id_filter="923"` now returns sim `5192190` (was `0`); name filter "Whiter" returns it; filtering a non-existent attack returns `0` **with** the guard hint.

## 5. Out of scope (remaining for SAF-32805)

**401 retry-with-backoff is NOT in this change.** Acceptance criterion 3 (transient 401s on `get_security_controls_events` auto-recover; persistent ones raise an explicit typed error instead of silent-empty) is not implemented here and remains open.

## 6. Acceptance Criteria status

- ✅ `playbook_attack_id_filter` returns matching sims regardless of int/str typing (regression test added).
- ✅ Replaying the baseline lookup for attack #3819-style id returns the sim, not empty (verified on pentest01 with attack 923 / sim 5192190).
- ❌ Transient 401 auto-recovery — **not addressed in this PR.**
