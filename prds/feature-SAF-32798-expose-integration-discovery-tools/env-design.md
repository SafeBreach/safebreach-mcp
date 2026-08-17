# Environment Design — SAF-32798

**Owning ticket:** SAF-32798   **Env name (planned):** saf-32798 (mgmt: `pentest-saf-32798.dev.sbops.com`)
**Environment class:** product / console env
**Offering:** Propagate (pentest) — _not because the feature does lateral movement, but because the Manual e2e
lane dispatches to `run-helm-tests`, whose env contract requires a **pentest console** with the AI-agent/Helm
stack + a connected Windows simulator. Deciding tests: T-18, T-19, T-35–T-39 (Manual, run-helm-tests)._
**Builder:** create-propagate-environment
**Retention:** terminate_at=72h, TF=eod-off (auto-stops end-of-day; resume next day if needed)
**Runnability verdict:** env buildable: **yes** · feature exercisable E2E: **yes, only if** (a) the mcp-proxy
feature build (pip-pinned to the safebreach-mcp branch) is deployed, (b) the 4 Helm flags are enabled, and
(c) several SIEM/TI connectors are configured incl. ≥1 sensitive-field type and ≥1 `isTiV2` type. Absent any of
these the Helm run has nothing to discover / redact.
**Source artifacts:** prd.md, test-plan.md, context.md, api-research.md
**Status:** Draft (awaiting review)

## Summary
A minimal **pentest** console with the AI-agent (Helm) stack enabled and a single Windows patient-zero simulator,
pre-seeded with a diverse set of SIEM/TI integration connectors. Its sole purpose is to let `run-helm-tests` drive
the four integration-discovery MCP tools (`get_integrations`, `get_installed_integrations`,
`get_installed_integration`, `get_ti_integrations`) through the AI-agent chat against **real** connector data, and
verify redaction on connectors that carry sensitive fields. No lateral movement / attacks are needed — this is a
**data-query** Helm case, so no victim hosts and no DC-based propagation topology are required beyond the pentest
build's baseline.

## Artifacts under test — DEPLOY MAP (developer: confirm before approving)   — see references/mcp-artifact-under-test.md

The **only** artifact under test is the in-console MCP server (SIMP), pip-baked into `mcp-proxy`. Everything else
runs the pentest build's stock `develop`/AMI images, by design.

| Artifact (mission-scoped) | Source | Build/deploy | Lands on |
|---------------------------|--------|--------------|----------|
| safebreach-mcp @ `feature/SAF-32798-expose-integration-discovery-tools` (HEAD `36d6de9`/latest) | GitHub `SafeBreach/safebreach-mcp` | repin `mcp-proxy` `requirements.txt` line 5 `git+https://…@<sha>` on a mcp-proxy branch → build (butler `integrationPipeline mcp-proxy`) → resolve **commit-SHA tag** → `mgmt_docker pull_image service=mcp-proxy tag=<sha>` | console `mcp-proxy` service (:4150, `sbmcp-proxy.service`) |

- **Deploy mechanism:** `deploy-mcp-server-under-test` (repin → build → `mgmt_docker pull_image`).
- **Verify live by the pip ref**, not a tag match (SAF-33511): confirm the running `mcp-proxy` installed
  safebreach-mcp at the intended branch/sha.
- **Built? = no yet** — the mcp-proxy feature build must be triggered by `deploy-mcp-server-under-test` (the
  safebreach-mcp branch is pushed; PR #88).
- Everything NOT in this table (orchestrator, ui-server, data, agent, …) = **stock pentest build**. Intended.

## Hosts (endpoints)   — see references/hosts.md (Propagate scheme) / offerings.md
| # | Role | OS (version, Propagate hyphenated id) | Agent | Notes |
|---|------|----------------------------------------|-------|-------|
| 1 | patient-zero (SafeBreach agent installed) | `windows-11` | stock `master` agent | satisfies run-helm-tests "connected Windows sim" precondition; **not** the artifact under test — baseline **master** (Propagate default; develop Win agent is broken for impacket, hosts.md) |
| DC | Windows Server DC (`pentest.lab`) | `windows-server-dc` | — | built by the pentest job by default; domain-joins the patient-zero |

- **No victim hosts** — this is a data-query Helm case, not lateral movement. Minimal topology = mgmt + DC + 1 patient-zero.
- Cloud/network simulator: not required.

## Console configuration   — see references/console.md §3, automation-capabilities.md
Applied post-build via `SbActions(mgmt, token).siem_actions` / `conf_actions` (automation repo). The goal is a
**diverse, redaction-exercising** connector set — ≥1 with sensitive fields, ≥1 `isTiV2` TI feed, plus breadth.

- **SIEM/TI connectors to configure** (`siem_actions.add_configured_integration({type, name, settings})`):
  1. **`splunkrest`** (name e.g. "Splunk - SAF-32798") — **has sensitive fields (`password`, `token`)** → the
     primary **redaction** target for `get_installed_integration`. Real creds from SSM `/automation/splunk`
     (`SPLUNK_BASE_URL/USER/PASSWORD`). Verified-working via automation (SAF-28472).
  2. **`tiv2mockconnector`** (name "TI Mock v2 - SAF-32798") — an **`isTiV2` TI** connector with **no real creds
     needed** (mock) → the deterministic target for `get_ti_integrations`.
  3. **`alienvault`** (name "AlienVault OTX - SAF-32798") — a second **`isTiV2` TI** type for breadth. Needs an
     API token; if none is available in SSM, fall back to a mock/placeholder or drop (see Decisions).
  4. *(breadth, optional)* **`sentinelonesdl`** or **`cortex`** — adds a non-TI installed connector with its own
     sensitive fields; `cortex`/`crowdstrike` need a collector node id (heavier). Prefer `sentinelone` if a typed
     helper + creds exist, else skip — the redaction + TI + slim-list assertions are already covered by 1–3.
- **Helm / AI-agent flags** (feature toggles, `conf_actions`; value = string `"true"`):
  `enableAiFeatures`, `enableAmazonBedrock`, `feature.aiAgentChat`, `enableAiAgentActions`.
- **Impersonated user / RBAC:** default admin is sufficient (happy-path discovery). No restricted-RBAC principal
  is required — the RBAC-deny path is out of scope for this feature (unit-covered by T-11).

## Credential sources (no secrets here)
- Splunk connector ← SSM `/automation/splunk`. AlienVault ← (TBD; see Decisions). EC2 key ← `~/.ssh/us-east-1.pem`.
- safebreach-mcp / mcp-proxy build: butler; console dev-ECR reachable by construction (pentest-*.dev).

## Reconciliation against the run-helm-tests env contract (SAF-33190)
- **Pentest console** ✓ (Propagate build). **Windows sim connected** ✓ (host #1). **AI/Bedrock + Helm flags** ✓
  (4 toggles above). **Case shape = data-query** → "seeded backend data" = the configured connectors above (that
  IS the data the tools discover). No attack/simulation run needed → no seeded `executionsHistory`, no scenario.

## Decisions needed
- **AlienVault creds:** is a usable AlienVault OTX API token in SSM? If not — drop connector #3 and rely on
  `tiv2mockconnector` alone for the `isTiV2` TI assertion (sufficient), or use another mock. (Recommend: proceed
  with `splunkrest` + `tiv2mockconnector` as the guaranteed core; treat `alienvault`/`sentinelone` as best-effort breadth.)
- **Windows patient-zero OS:** `windows-11` assumed (run-helm-tests just needs a connected Windows sim); confirm or pick `windows-2022`.

## Gaps
- **Connector-type breadth is capped by typed-helper coverage.** Only `crowdstrike`/`sentinelone`/`cortex`/
  `splunkrest` have typed `build_integration_data()` helpers; `alienvault`/`tiv2mockconnector` go through raw
  `add_configured_integration` with an explicit `type`+`settings` dict (known for these). MDE/Trend/QRadar/etc.
  have **no** typed helper and unconfirmed `type` strings (console.md §3 → consult Boris Ifraimov) — **out of scope**;
  the core assertions (slim list, redaction, TI-derivation) are fully covered by `splunkrest` + `tiv2mockconnector`
  (+ optional `alienvault`). This is acceptable: the feature's contract is validated by connector *diversity we can
  configure*, not by every real vendor connector.
- **mcp-proxy feature build not yet triggered** — `deploy-mcp-server-under-test` will build+deploy it (Built? = no).
