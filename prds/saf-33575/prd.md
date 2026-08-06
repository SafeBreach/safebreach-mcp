# Quick Run test name should reflect the attack — SAF-33575

## 1. Overview

Ad-hoc attack execution through Helm queues a test named `Quick Run (1 attacks)`, omitting the
name of the attack that was run. The operator looking at the "Now Running" panel cannot tell what
is executing without opening the test.

Bug: `safebreach_mcp_studio/studio_functions.py:2786`

```python
effective_test_name = test_name or f"Quick Run ({len(steps)} attacks)"
```

## 2. Solution Description

### 2.1 The name format is already decided by precedent

`ui-react/src/components/QuickRunModal/index.tsx:199` — the Playbook UI's own Quick Run — already
ships this convention:

```js
const plan = { name: `Quick Run - ${moveName || ''}`, steps: [step] };
```

So this is not "the generated name is unhelpful", it is **the Helm/MCP path diverging from the UI's
shipped convention**. Match the UI. No new format decision is required; the ticket's open question
to Tal Rotem is answered by the existing product behaviour.

### 2.2 The attack name is already in scope

`_build_quick_run_steps` (`studio_functions.py:2582-2585`) already resolves and stores the name on
every step:

```python
attack_name = name_map.get(attack_id, f"Attack {attack_id}")
steps.append({..., "name": attack_name, ...})
```

So the fix reads `step["name"]` and needs no `name_map` plumbing. Because the name is built at
line 2786 — *after* the 0-simulation filter at 2770-2780 replaces `steps` with `exec_steps` — it
naturally reflects the attacks **actually queued**, not the attacks requested. That is the correct
behaviour: the test card should describe what is running.

### 2.3 Multi-attack naming

The UI path only ever handles a single attack (`moveName`, one `step`); `sb_quick_run` accepts
several `attack_ids`, so multi-attack naming has no precedent. Extension:

| Queued attacks | Name |
|---|---|
| 1 | `Quick Run - Lazarus Fake TLS` |
| 3 | `Quick Run - Lazarus Fake TLS +2 more` |
| 0 names resolvable | `Quick Run (N attacks)` (existing fallback) |

An explicitly passed `test_name` still wins — unchanged.

## 3. API / Integration

No tool-signature change. `quick_run`'s `test_name` parameter and all other behaviour are
untouched; only the default fallback changes. No console/backend change.

## 4. Definition of Done

- [ ] Single-attack Quick Run through Helm produces `Quick Run - <attack name>`.
- [ ] Multi-attack Quick Run produces `Quick Run - <first> +<n> more`.
- [ ] Explicit `test_name` still overrides the default.
- [ ] Unresolvable names fall back to `Quick Run (N attacks)` — no crash, no empty name.
- [ ] Name reflects queued (post-skip-filter) attacks, not requested ones.
- [ ] Unit tests green; lint clean.

## 5. Testing Strategy

Unit tests on `_default_quick_run_name` covering: one step, several steps, zero steps, and steps
missing a `name` key. Existing `sb_quick_run` tests in
`safebreach_mcp_studio/tests/test_studio_functions.py` must stay green — any that assert the old
`Quick Run (N attacks)` string are updated to the new expectation.

## 6. Implementation Phases

| Phase | Status | Notes |
|---|---|---|
| 1. `_default_quick_run_name` helper + call site | pending | one helper, one line changed |
| 2. Unit tests | pending | four cases above |

## 7. Risks

Low. Pure presentation change on a default value, behind an existing override, with no signature
or payload-shape change. Only risk is a test elsewhere asserting the old literal name.
