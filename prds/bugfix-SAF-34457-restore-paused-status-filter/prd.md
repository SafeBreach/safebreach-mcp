# PRD: SAF-34457 — restore `paused` as a valid `get_tests` `status_filter`

- **Ticket**: [SAF-34457](https://safebreach.atlassian.net/browse/SAF-34457) (Bug)
- **Branch**: `bugfix/restore-paused-status-filter` (off `main`; predates the ticket key, so the
  branch name carries no key — this folder is named by the key instead)
- **PR**: [#83](https://github.com/SafeBreach/safebreach-mcp/pull/83)

## Problem

Customer-reported regression, validated on Clearwater01/02/03. `get_tests` with
`status_filter="paused"` fails before any API call:

```
Invalid status_filter parameter 'paused'. Valid values are: completed, canceled, failed, running, queued
```

The customer pauses tests routinely outside business hours and can no longer detect them.

## Root cause

SAF-33511 (`f6b20ee`, shipped 1.10.0) added the **first** `status_filter` allowlist. `git log -L`
confirms no validation existed before: any string was accepted, lowercased, sent to `testsummaries`
as `&status={UPPER}`, and matched client-side in `_apply_filters`. The allowlist was built from the
four documented values plus the new `queued`, silently dropping every undocumented-but-working
value — `paused` among them.

## Change

| File | Change |
|------|--------|
| `data_functions.py:134` | `'paused'` added to `valid_status_filters` — the fix |
| `data_functions.py:104` | docstring value list |
| `data_server.py:69` | MCP tool description |
| `README.md:873`, `CLAUDE.md:496` | documented value lists |

Restores the exact pre-1.10.0 code path. The four supporting edits are the same one-word change:
an accepted value that no description advertises is the SAF-30863 failure mode, where the agent
never learns the option exists.

## Tests

One regression test asserting `status_filter="paused"` is accepted and selects the paused row, plus
`paused` added to the existing invalid-value error-message assertion. **1066 passed, 0 failed**
(non-e2e).

## Known limitation

Pause state is authoritative in the orchestrator (`slotState[].isPaused`) — which is why
`get_test_details` and `manage_test` consult the orchestrator queue as phase 1, and why SAF-33511
found the list API has no functional `QUEUED` status. Whether `testsummaries` reports `paused` in
the **list** response is unverified: it needs a live console with a genuinely paused test, which
isn't reproducible locally. If the customer reports the call now succeeds but returns nothing, the
remaining fix is an orchestrator overlay (mark tests in paused slots as `status='paused'`), not this
allowlist.

## Definition of done

- [x] `status_filter='paused'` accepted; value advertised in tool description, docstring, README, CLAUDE.md
- [x] Regression test green; full non-e2e suite green (1066)
- [ ] Customer confirms on Clearwater with a genuinely paused test

## Notes

Written after the fix, not before — the change was triaged and shipped as a one-line validation
regression before a ticket existed. Recorded here for the PRD gate and for whoever hits the known
limitation above.
