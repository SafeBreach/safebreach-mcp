# Live API Research — SAF-32798 (pentest01, 2026-08-17)

Console `pentest01` → `https://pentest01.safebreach.com`, account `3471166703`, auth header
`x-apitoken` (200 OK). All SIEM endpoints under `/api/siem/v1/accounts/{accountId}`. Response
envelope is uniformly `{ "error": 0, "result": <payload> }`.

> No secret **values** were captured — only response structure, field names, and value *forms*
> (classified as vault-ref / plaintext / object). Raw responses live in scratchpad, not committed.

## Endpoint validation (all live 200)

| Endpoint | Purpose | Live result |
|----------|---------|-------------|
| `GET /config/integrations/installed` | installed connectors | **already slim** — each item is exactly `{id,type,name,enabled}` (25 connectors). Not raw/full as swagger implied. |
| `GET /config/integrations` | connector-type catalog | **object keyed by `type`** (91 types). Each entry: `category, description, displayName, featureFlag, fields[], guideLink, isDynamic, isFileProvider, isPam, isReadOnly, isSecEvents, isSendSimResult, isTi, isTiV2, isVm, product, productRegex, vendor`. |
| `GET /config` | whole SIEM config blob | keys: `connectors[], featureFlags, fetchIntervalMinutes, logLevel, managementUIAddress, nodes, pci, skipInternalFail, streamingDelayMinutes`. `connectors[]` holds **full** per-connector config incl. sensitive fields. |
| `GET /config/integrations/installed/{id}` | single connector | **404** — confirms no dedicated single-connector GET (matches Gal + swagger). |
| `GET /config/providers` | combined | keys: `categories, defaults (=catalog), parsers, providers (=installed configs)`. Superset; not needed if we hit the specific endpoints. |
| `GET /config/categories` | categories | small lookup. |

## Data-source map (finalized, live-validated)

| Python tool | Source endpoint | Transform |
|-------------|-----------------|-----------|
| `get_integrations` | `GET /config/integrations` | map (type→def) → list of catalog entries; filter by `category`; paginate |
| `get_installed_integrations` | `GET /config/integrations/installed` | pass-through slim `{id,type,name,enabled}`; optional `categories` joined from catalog; paginate |
| `get_installed_integration` | `GET /config` → `.connectors[]`, filter by `id` | redact (below); 404-style "not found" if id absent |
| `get_ti_integrations` | `GET /config/integrations/installed` + catalog | keep installed whose `catalog[type].isTiV2 == true`; slim `{id,type,name,enabled}`; paginate |

## Redaction — CONFIRMED REQUIRED (highest-severity)

`/config` returns sensitive fields **unmasked relative to the MCP contract**:
- Secret values (`secret`, `apiToken`, `password`, `token`, `apiSecret`, `proxyPass`, …) come back as
  **`$PAM:INTERNAL_VAULT:...` vault references** (raw secret stays in vault, but the path is exposed).
- Non-secret fields (`clientId`, `apiHost`, `host`, `proxyUser`, `authMethod`, `apiTokenId`) are
  **plaintext** — legitimately returned.
- `headers` (seen on `custom_wiz`) is returned as a **raw object**, and is **not** flagged `sensitive`
  in the schema → this is exactly why the TS tool force-masks it (can carry bearer/auth tokens).

**Redaction source is the catalog**: `catalog[type].fields[]` where `field.sensitive == true` gives
the exact set of fields to mask per connector type. Live sample (installed types):
- `alienvault`: `apiToken, proxyPass` · `custom_splunkrest`: `token, password, proxyPass`
- `custom_crowdstrike`: `secret, proxyPass` · `threatconnect`: `apiSecret, apiToken, proxyPass`
- `custom_hashicorpvault`: `clientKeyPassword, token, secretId, proxyPass` · `idira`: `keyPassword, pfxPassword, proxyPass`
- `msatpgraph`/`office365graph`/`custom_wiz`: `clientSecret, proxyPass` · `sentinelonesdl`/`cortexxdr`: `apiToken, proxyPass`

**Python redaction algorithm (mirrors the platform's existing sensitive-field sanitization):**
1. Look up `catalog[connector.type].fields[]`; for every field with `sensitive==true`, set
   `connector[field.key] = "@enc:SENSITIVE_FIELD"` (mask regardless of current value/vault-ref).
2. Force-mask `headers` and `proxyPass` to `@enc:SENSITIVE_FIELD` if present (backstop — `headers`
   is not schema-`sensitive`).
3. Requires fetching the catalog (already needed for `get_integrations`) — one extra call, cacheable.

## TI derivation — CONFIRMED

`catalog[type].isTiV2 == true` identifies TI connectors (the platform's TI capability, which the
catalog surfaces as `isTiV2`). Live: 6 installed TI connectors
(`alienvault` ×2, `custom_tiv2mockconnector`, `threatconnect`, `custom_mitreattack` ×2). `isTi` and
`isTiV2` agreed for every installed TI connector here; use **`isTiV2`** as primary,
optionally union with `isTi`.

## RBAC — still an implementation/verify item

Direct `x-apitoken` calls succeed (200). Whether the **RBAC gateway** in embedded/SIMP mode gates
these `/config/integrations*` paths (returning 403 for unauthorized callers, which
`check_rbac_response` maps to `PermissionError`/`RBAC_DENIED_HINT`) cannot be proven with a direct
admin token — must be verified in embedded mode / with a restricted principal during implementation.

## Consistency notes (match existing Config-server tools)
- Envelope handling: read `response.json()["result"]` (all SIEM endpoints wrap in `{error,result}`) —
  differs from some config endpoints; handle explicitly.
- Auth/HTTP: `get_api_base_url(console,'siem')` + `get_api_account_id` + `get_auth_headers_for_console`
  + `requests.get(timeout=120)` + `check_rbac_response`.
- Pagination `page_number`/`PAGE_SIZE=10`; transforms in `config_types.py`; `sb_*` in
  `config_functions.py`; `@self.mcp.tool(readOnlyHint=True)` in `config_server.py`.
