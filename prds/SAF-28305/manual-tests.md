# Manual Test Plan: SAF-28305 - MITRE ATT&CK Tags for Playbook Tools

## Prerequisites
- SafeBreach MCP servers running (`uv run start_all_servers.py`)
- Claude Desktop connected to the playbook server (`http://127.0.0.1:8003/sse`)
- A valid SafeBreach console configured (e.g., `pentest01`)

---

## Test 1: MITRE Data Inclusion in Bulk Listing

**Purpose**: Verify `include_mitre_techniques=True` returns MITRE data in bulk attack listing.

**Prompt**:
> Use the get_playbook_attacks tool on pentest01 with include_mitre_techniques enabled. Show me the first page.

**Expected**:
- Response includes `MITRE Tactics`, `MITRE Techniques`, and/or `MITRE Sub-Techniques` per attack
- Not all attacks will have MITRE data (~42.6% coverage)
- Attacks without MITRE data show no MITRE fields

---

## Test 2: Default Behavior Unchanged

**Purpose**: Verify default calls (no MITRE params) produce the same output as before.

**Prompt**:
> Use get_playbook_attacks on pentest01 with default settings. Show me page 0.

**Expected**:
- No MITRE fields in the response
- Same 5 fields per attack: name, ID, description, modified date, published date
- Performance indistinguishable from before

---

## Test 3: MITRE Technique Filter (Single Value)

**Purpose**: Verify filtering by a single MITRE technique ID.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_technique_filter set to "T1046".

**Expected**:
- Only attacks mapped to technique T1046 (Network Service Discovery) returned
- Applied filters metadata shows `mitre_technique_filter=T1046`
- MITRE data auto-included in results (even without `include_mitre_techniques=True`)

---

## Test 4: MITRE Technique Filter (Multi-Value)

**Purpose**: Verify comma-separated multi-value technique filter with OR logic.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_technique_filter "T1046,T1021".
> How many attacks match?

**Expected**:
- Returns attacks matching either T1046 OR T1021
- Total should be greater than single-value filter result
- Each returned attack has at least one of the two techniques

---

## Test 5: MITRE Tactic Filter (Single Value)

**Purpose**: Verify filtering by a single MITRE tactic name.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_tactic_filter "Discovery".
> How many attacks are mapped to the Discovery tactic?

**Expected**:
- Only attacks with the Discovery tactic returned
- MITRE data auto-included showing Discovery in tactics list
- Total count reported in response

---

## Test 6: MITRE Tactic Filter (Multi-Value)

**Purpose**: Verify comma-separated multi-value tactic filter with OR logic.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_tactic_filter "Discovery,Lateral Movement".
> How many attacks match? Compare this to using just "Discovery" alone.

**Expected**:
- Returns attacks matching either Discovery OR Lateral Movement tactic
- Total should be greater than the single-value "Discovery" result from Test 5
- Each returned attack has at least one of the two tactics in its MITRE data

---

## Test 7: Multi-Value Technique Filter with Spaces

**Purpose**: Verify comma-separated values with spaces after commas still work.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_technique_filter "T1046, T1021".
> Note the space after the comma. Does it still work?

**Expected**:
- Returns same results as "T1046,T1021" (without spaces)
- Whitespace around values is trimmed
- No errors

---

## Test 8: Combined MITRE + Existing Filters

**Purpose**: Verify MITRE filters work alongside existing name/ID filters.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_tactic_filter "Lateral Movement"
> and name_filter "RDP". How many match both criteria?

**Expected**:
- Results match BOTH the tactic filter AND name filter
- Applied filters metadata shows both filters active
- Narrower result set than either filter alone

---

## Test 9: MITRE in Attack Details

**Purpose**: Verify `include_mitre_techniques` works on single attack details.

**Prompt**:
> Get the details for playbook attack 1027 on pentest01 with include_mitre_techniques enabled
> and include_tags enabled.

**Expected**:
- Response includes a `MITRE ATT&CK Mapping` section with tactics, techniques (with URLs),
  and sub-techniques (with URLs)
- Tags section still works normally alongside MITRE
- ATT&CK URLs are clickable and point to correct MITRE pages

---

## Test 10: MITRE URL Correctness

**Purpose**: Verify ATT&CK URLs are constructed correctly for techniques and sub-techniques.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_technique_filter "T1021.001"
> and include_mitre_techniques enabled. Show me the MITRE details.

**Expected**:
- Sub-technique URL uses `/` not `.`: `https://attack.mitre.org/techniques/T1021/001/`
- Technique URL is standard: `https://attack.mitre.org/techniques/T1021/`
- URLs are valid if clicked

---

## Test 11: Empty MITRE Filter Results

**Purpose**: Verify graceful handling when MITRE filter matches nothing.

**Prompt**:
> Use get_playbook_attacks on pentest01 with mitre_technique_filter "T9999".

**Expected**:
- Returns 0 total attacks
- No error - clean empty result
- Applied filters metadata still shows the filter value

---

## Test 12: Full TTP Coverage Workflow (Intuit Use Case)

**Purpose**: End-to-end validation of the Intuit weekly TTP comparison workflow.

**Prompt**:
> I need to understand our MITRE ATT&CK coverage on pentest01.
> Use get_playbook_attacks with include_mitre_techniques enabled.
> Scan through multiple pages and summarize:
> 1. How many total attacks exist?
> 2. How many have MITRE technique mappings?
> 3. What are the top 5 most common MITRE tactics?

**Expected**:
- Agent iterates through pages using pagination hints
- Reports total attack count (~9,500+)
- Reports MITRE coverage percentage (~42%)
- Lists top tactics (likely: Discovery, Execution, Defense Evasion, etc.)
- Demonstrates the real-world value of this feature
