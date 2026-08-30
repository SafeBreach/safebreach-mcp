# Environment Design — SAF-35508

**Owning ticket:** SAF-35508   **Env name (planned):** *none — reuse recommended, see below*
**Environment class:** product / console env
**Offering:** Validate (BAS) — _the test plan names `Validate console environment` verbatim for all five
automatic e2e tests (T-28, T-29, T-30, T-31, T-40), which per the Level-2 ordering overrides the JIRA
`Offering` field. No Propagate finding families are involved: nothing here runs an attack at all._
**Builder:** `create-validate-environment` — **only if a dedicated env is chosen over reuse**
**Runnability verdict:** env buildable: **yes** · feature exercisable E2E: **yes, on any console whose
orchestrator carries SAF-35568** — and **NO** on one that does not, where T-40 degrades to a recorded skip
**Source artifacts:** prd.md, test-plan.md, context.md
**Status:** Draft (awaiting review)

## Summary

Five automatic e2e tests score real plans against a live console and read the numbers back. **Nothing is
queued, attacked, or mutated** — `get_plan_statistics` is registered `readOnlyHint=True`, and the one test
that raises (T-31) does so client-side before any request. The environment requirement is therefore not a
topology at all: it is **a reachable Validate console whose orchestrator carries SAF-35568**, holding at
least one scenario with steps and enough simulators that some attacks are eliminated.

**The recommendation is to reuse an existing console, not to build a dedicated environment.**

## Reuse versus build — the cost trade-off, stated explicitly

| | Reuse an existing console | Build `saf-35508` |
|---|---|---|
| Wall-clock | minutes (set two env vars) | ~6 min mgmt build + EC2 provisioning |
| Cost | none | EC2 burn, 72 h TTL, teardown to remember |
| Risk to the console | **none — every call is read-only** | n/a |
| Satisfies T-28, T-29, T-31 | yes, if any scenario has steps | yes |
| Satisfies T-30 | only if a disabled/offline simulator exists — else a recorded skip | yes, by construction |
| Satisfies T-40 | **only if its orchestrator carries SAF-35568** | yes, if built from a develop that has it |

A dedicated AWS lab to run five read-only scoring calls is disproportionate. The one thing a purpose-built
env buys is **determinism for T-30** (guaranteeing a disabled simulator exists) — and T-30 already handles
its absence with an explicit skip that asserts the unconditional half first. That is not worth a build on
its own; it becomes worth it only if the reviewer wants T-30's conditional half genuinely exercised.

## Artifacts under test — DEPLOY MAP (developer: confirm this before approving)

**Mission-scoped repo:** `safebreach-mcp` @ `feature/SAF-35508-plan-statistics-mcp-tool` (HEAD `fd03c14`).

| Artifact | Where it runs for these tests | Deploy mechanism | Built? |
|---|---|---|---|
| `safebreach-mcp` (this branch) | **the local working tree** — pytest imports `sb_get_plan_statistics` | none; the checkout *is* the artifact | n/a |
| in-console MCP server (`mcp-proxy`) | **not used by T-28…T-31, T-40** | — | — |
| `orchestrator` | the console's own, **must carry SAF-35568** | stock; not built by this mission | must verify |

**Two things a reader must not get wrong here:**

1. **No `deploy-mcp-server-under-test` is required.** The plugin rule that "for `safebreach-mcp`, the
   in-console MCP server is an artifact under test" does **not** apply to these five tests: they import the
   Python function and call the console's REST API directly, never traversing an in-console MCP server.
   Deploying `mcp-proxy` would be pure cost. *(It **is** required for the manual **T-32**, which exercises
   the tool through Helm in the product — see Gaps.)*
2. **`orchestrator` is not ours, but it is the decisive dependency.** SAF-35568 is what serves
   `constraintCatalog`. T-40 is the only test in the whole plan that can *falsify* the relay design — every
   Phase 1 test asserts MCP's behaviour *given* a catalog. On a console predating SAF-35568 it records a
   skip and asserts the R11 degradation instead, so the design's central claim stays unverified.

## Hosts (endpoints) — what the console must already have

Not a build spec. These are the properties any candidate console must satisfy:

| # | Requirement | Needed by | If absent |
|---|---|---|---|
| 1 | ≥1 scenario carrying ≥1 step | T-28, T-29, T-30, T-40 | tests skip with a stated reason |
| 2 | ≥1 custom plan (integer-string id) | T-29's second case | that case skips |
| 3 | Enough simulators that some attacks are eliminated (OS mismatch etc.) | T-40 | no conflicts ⇒ nothing to relay ⇒ skip |
| 4 | ≥1 disabled / unapproved / offline simulator | T-30's conditional half | recorded skip; the ordering half still asserts |
| 5 | Orchestrator carrying **SAF-35568** | **T-40** | recorded skip; the relay design stays unverified |

**If a dedicated env is chosen instead**, the minimal buildable spec is 2 simulators — `windows2022` and
`ubuntu22` (both canonical `hosts.md` Validate ids, no-hyphen form) — with one deliberately left
disconnected to satisfy requirement 4. No DC, no cloud attacker, no EDR sensor, no connectors: nothing here
detects or blocks anything.

## Console configuration

- **Cloud integrations:** none
- **EDR/SIEM connectors:** none — no attack runs, so nothing detects
- **Email inboxes:** none
- **Impersonated users:** none
- **Simulator roles & assets:** none required beyond the OS mismatch that produces a conflict
- **Feature toggles:** none
- **API keys:** one read-scope token for the chosen console (credential source below)

## Credential sources (no secrets here)

- Console API token ← `<console>_apitoken` env var, or `SB_API_KEY`, per the root `conftest.py`
  `set_e2e_auth_context` fixture
- Delivered via the private `.vscode/set_env.sh` (**absent in this checkout — only
  `set_env.sh.template` is present**)

## Runner-contract reconciliation

`running-phase-tests` dispatches *(e2e × Automatic × Validate console)* → **`run-validate-attack`**. That is
the wrong runner here: `run-validate-attack` executes attacks, and **these tests run no attack**. They are
plain pytest making read-only API calls, invoked as:

```
export E2E_CONSOLE=<console>
source .vscode/set_env.sh
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_e2e_plan_statistics.py -m "e2e" -v
```

Surfaced per the SAF-33190 rule — a runner mismatch found at design time rather than after a build.

## Decisions needed

1. **Which console?** The repo's e2e default is `pentest01`. Any reachable Validate console works. *(This
   is the only genuinely blocking decision.)*
2. **Credentials.** No `.vscode/set_env.sh` exists in this checkout and no console env vars are set, so
   **these tests cannot be run from this session as it stands** — a token must be supplied.
3. **Is T-30's conditional half required?** If the chosen console has no disabled simulator, T-30 skips it.
   Accepting the skip means reusing a console; requiring it means either disabling one simulator on the
   chosen console or building a dedicated env.
4. **Does the chosen console's orchestrator carry SAF-35568?** Verifiable in one call: score anything with
   `get_constraints=True` and check whether `constraint_catalog` holds a non-null `description`.

## Gaps

- **T-32, T-33, T-35 are Manual and out of this design's scope** (`Passes after: Final`). **T-32 exercises
  the tool through Helm in the product**, which *does* require the in-console MCP server — so it, unlike
  the five automatic tests, needs `deploy-mcp-server-under-test`. **T-35 is the only test that checks the
  numbers are right** rather than merely self-consistent, by comparing against the console's own Checkout
  tab.
- No environment can make T-40 meaningful on a pre-SAF-35568 console; that is a version dependency, not a
  provisioning one.
