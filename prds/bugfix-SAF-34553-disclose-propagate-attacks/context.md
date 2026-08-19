# SAF-34553 — Helm: misleading presentation of filtered attacks due to Propagate inclusion

**Status**: Phase 4: Document Findings
**Type**: Bug | **Priority**: Medium | **Labels**: CTEM-dev, Helm
**Repo**: safebreach-mcp | **Branch**: bugfix/SAF-34553-disclose-propagate-attacks (off origin/main)
**Jira**: https://safebreach.atlassian.net/browse/SAF-34553

## Ticket Summary

`get_playbook_attacks` returns Playbook (Validate) and Propagate/ALM attacks in a single
total with no indication that two catalogs were merged. Helm states one number while the
Playbook UI beside it shows another, and Helm lists attacks the customer cannot find, open
or run from the Playbook. The data is correct; the *scope of the answer* is undisclosed.

Reported on pentest-helm-2156a0.dev.sbops.com, mgmt 26.3.4.

### Expected results (from reporter)
1. Helm refers only to Validate attacks by default, even when asked for totals.
2. Asking for Propagate returns only Propagate, never mixed.
3. Asking for both discloses the split ("153 — 108 Validate, 45 Propagate") and marks
   Propagate rows as not reachable from the Playbook.

Reporter note: Propagate attacks are planned to appear in the Playbook later, behind a
"test type" filter.

## Related Tickets (finding-related-tickets verdict: PROCEED)

| Key | Status | Class | Why |
|-----|--------|-------|-----|
| SAF-34097 | Blocked | Downstream dependent | Test-automation task explicitly waiting for SAF-34553 to ship |
| SAF-33946 | Done | Related-context | Same area — `get_playbook_attack_details` leaking full metadata for Propagate IDs when Propagate disabled. Different symptom (metadata leak, not undisclosed totals) |
| SAF-35111 | To Do | Related-context | Different Helm/Propagate scoping bug (ADCS misconfig count) |

No duplicate exists.

## Investigation Findings

### Entry points / data flow
```
get_playbook_attacks (playbook_server.py:69)
  -> sb_get_playbook_attacks (playbook_functions.py:99)
    -> _get_all_attacks_from_cache_or_api (:35)  cache 30m, maxsize 5
       GET {base_url}/api/kb/vLatest/moves?details=true   (:71)
    -> transform_reduced_playbook_attack (playbook_types.py:321)   <-- drops tag groups
    -> filter_attacks_by_criteria (playbook_types.py)              <-- filters
    -> paginate_attacks (:188)  PAGE_SIZE 10
  -> response assembly (playbook_server.py:112-160), renders result['hint_to_agent'] at :159
```

### The discriminator (verified against live consoles)
- ui-react decides this in exactly one place: `containers/Playbook/moveUtils.ts:190`
  `isAlmMove = tags.find(t => t.id === 44 && t.name === 'ALM')` — **ignores the value**.
  `PROPAGATE_PLAYBOOK_TAG_ID = 44` (`containers/Pentest/utils/data.ts:10`).
- `tag` table has **no accountId** -> tag definitions are global, not per-account.
- `id=44, name='ALM'` confirmed on **both** staging-management and pentest01 -> stable
  across consoles.
- ALM is a **boolean-valued** tag group: `values = [{value:'0'},{value:'1'}]`.
- Live counts:
  - pentest01: 9,605 moves, **111 with `ALM:[1]`, zero with `ALM:[0]`**.
  - staging-management: 9,497 moves, **zero ALM tags of any value**.
- => matching on group presence is safe *in practice*; matching on **value == 1** is
  strictly more correct and free. The UI's value-blindness is a latent bug not worth porting.
- The discriminator lives in content-manager's `move.tags` (DB shape: object keyed by tag
  name -> array of value-ids), which is what `/api/kb/vLatest/moves?details=true` serves.
  So the MCP's own data source carries it — no dependency on the UI's data path.

### Existing repo precedent (IMPORTANT — align with this)
`safebreach_mcp_data` already implements this exact concept for **tests**:
- `data_functions.py:101` — `test_type: Filter by test type ('validate', 'propagate')`
- `:119` — `valid_test_types = ['validate', 'propagate']`, `.lower()` compared, raises
  `ValueError(f"Invalid test_type parameter '{test_type}'. Valid values are: ...")`
- `:378-382` — filter block: `'ALM' not in t['test_type']` / `'ALM' in t['test_type']`
- `data_types.py:163,172` — `is_propagate = "ALM" in system_tags`; emits a verbose
  agent-facing string: `"Automated Lateral Movement (aka ALM aka Propagate)"` vs
  `"Breach And Attack Simulation (aka BAS aks Validate)"` [sic — 'aks' typo, pre-existing]

Divergences this forces (see Design Decisions):
- sibling has **no `'all'` value**; `test_type=None` means unfiltered *and* is the default.
  Here the default must be `'validate'` (expected result 1), so `None` cannot mean both.
- sibling's discriminator is `'ALM' in system_tags` on a **test**; moves use tag groups.
  Naming/validation style is reusable, the predicate is not.

### Out of scope (verified)
- `safebreach_mcp_studio/studio_server.py` references `get_playbook_attacks` only in prose
  (`:1003`, `:1425`) — no code coupling.

### Constraints
- **Verification requires a Propagate-capable console.** staging-management has zero
  Propagate content. pentest01 (i-0b889ae01e44bf882) has 111.
- Filtering must be applied **before** pagination so `total_attacks` self-corrects.
- safebreach-mcp reaches a console only via a version tag that mcp-proxy pip-installs at
  docker build time — release is tracked separately (see Scope decisions).

## Scope Decisions (user, Phase 2)
1. **All three tools**: `test_type` on `get_playbook_attacks` and
   `get_playbook_attacks_by_tags`; Propagate marker on `get_playbook_attack_details`.
2. **Code only** — release + mcp-proxy pin bump is a separate ticket (SAF-35238 pattern).
3. **Values `validate` / `propagate` / `all`** — matches ticket language, the repo
   precedent, and ui-react `selectors.ts:424` (`testType === 'propagate'`).

## Brainstorm (Phase 5) — COMPLETE, Approach A approved

### Approaches considered
- **A — `test_type` param, default `validate`** (CHOSEN). Filter in the MCP before
  pagination; Propagate rows marked; split subtotals when `all`. Deterministic — the agent
  cannot return mixed data by accident because its input is already scoped.
- **B — no param, always return both with split subtotals.** Rejected: violates expected
  result 1 (default must be Validate-only), and breaks pagination sanely (at PAGE_SIZE 10 a
  page could be entirely Propagate).
- **C — fix in the Helm system prompt, leave the MCP alone.** Rejected on a fact, not a
  preference: `transform_reduced_playbook_attack` drops the tag groups, so the payload the
  model sees carries no Propagate marker. The model cannot disclose or filter what is not in
  its input. An MCP data change is required regardless.

### Settled design decisions
1. **Param**: `test_type: Optional[str] = 'validate'`, valid `['validate','propagate','all']`,
   `.lower()`-compared, `ValueError` message mirroring `data_functions.py:119`.
   Explicit `'all'` (diverges from sibling's `None`) so "both catalogs" is discoverable in
   the tool schema rather than being another undisclosed behaviour.
2. **Discriminator**: `_is_propagate_attack(tags_data)` in `playbook_types.py` — tag group
   `id == 44` AND `name == 'ALM'` AND a value of `'1'`. Value-aware, unlike ui-react's
   `isAlmMove`.
3. **Payload**: `transform_reduced_playbook_attack` emits `is_propagate: bool` (always — one
   bool, same cost basis as the existing platform fields). The verbose
   Propagate/ALM/"not reachable from the Playbook" vocabulary lives in the **tool
   description** and in `hint_to_agent`, taught once rather than repeated per row.
4. **Filter placement**: inside `filter_attacks_by_criteria`, applied **before**
   `paginate_attacks`, so `total_attacks` self-corrects and the headline number in the bug
   report fixes itself.
5. **Disclosure**: on a default (`validate`) call that excluded rows, emit via the existing
   `hint_to_agent` channel — "N Propagate attacks excluded; pass test_type='all' to
   include them." Keeps the default safe AND makes the exclusion disclosed, which is the
   ticket's root complaint inverted.
6. **Presentation** (`playbook_server.py`): when `test_type='all'`, split the header total
   ("153 — 108 Playbook (Validate), 45 Propagate") and mark Propagate rows as not reachable
   from the Playbook. `test_type` echoed in `applied_filters`.
7. **`get_playbook_attack_details`**: Propagate marker so a customer opening an ALM attack
   id is told it is not reachable from the Playbook. Must not regress SAF-33946 (metadata
   leak when Propagate disabled).
8. **`get_playbook_attacks_by_tags`**: same `test_type` param, same default.

### Deliberately NOT done
- Not fixing the pre-existing `"aks Validate"` typo at `data_types.py:172,196` — different
  module, not a line this change touches.
- Not porting `isAlmMove`'s value-blindness.
- Not touching `safebreach_mcp_studio` (prose references only).
- Release / mcp-proxy pin bump — separate ticket per Phase 2 decision.

**Status**: Phase 6: PRD Created
