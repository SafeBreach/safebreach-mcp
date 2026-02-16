"""
Quick investigation script to dump raw API fields from /testsummaries/ for a Propagate test.
This helps identify the correct field names for findingsCount/compromisedHosts.

Usage:
    source .vscode/set_env.sh && uv run python scripts/investigate_propagate_fields.py
"""

import json
import os

import requests
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id

CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
# Use the Propagate test ID from TC-1 results
TEST_ID = "1771172654423.2"


def main():
    apitoken = get_secret_for_console(CONSOLE)
    base_url = get_api_base_url(CONSOLE, 'data')
    account_id = get_api_account_id(CONSOLE)

    api_url = f"{base_url}/api/data/v1/accounts/{account_id}/testsummaries/{TEST_ID}"
    headers = {"Content-Type": "application/json", "x-apitoken": apitoken}

    print(f"Fetching: {api_url}")
    response = requests.get(api_url, headers=headers, timeout=120)
    response.raise_for_status()

    data = response.json()

    print(f"\n=== All top-level keys ({len(data)} keys) ===")
    for key in sorted(data.keys()):
        val = data[key]
        val_type = type(val).__name__
        if isinstance(val, (str, int, float, bool)) or val is None:
            print(f"  {key}: {val_type} = {val!r}")
        elif isinstance(val, list):
            print(f"  {key}: list[{len(val)}]")
        elif isinstance(val, dict):
            print(f"  {key}: dict[{len(val)} keys] = {list(val.keys())}")
        else:
            print(f"  {key}: {val_type}")

    # Look specifically for anything related to findings or compromised
    print("\n=== Fields containing 'finding' or 'compromis' (case-insensitive) ===")
    for key in sorted(data.keys()):
        if 'finding' in key.lower() or 'compromis' in key.lower():
            print(f"  {key} = {data[key]!r}")

    # Also dump systemTags to confirm it's ALM
    print(f"\n=== systemTags ===")
    print(f"  {data.get('systemTags', 'NOT FOUND')}")

    # Also dump finalStatus to confirm
    print(f"\n=== finalStatus ===")
    final_status = data.get('finalStatus', {})
    print(f"  {json.dumps(final_status, indent=2)}")

    # Now check the propagateSummary endpoint
    propagate_url = f"{base_url}/api/data/v1/propagateSummary/{TEST_ID}"
    print(f"\n=== Checking propagateSummary endpoint: {propagate_url} ===")
    try:
        prop_response = requests.get(propagate_url, headers=headers, timeout=120)
        prop_response.raise_for_status()
        prop_data = prop_response.json()
        print(f"Top-level keys ({len(prop_data)} keys):")
        for key in sorted(prop_data.keys()):
            val = prop_data[key]
            val_type = type(val).__name__
            if isinstance(val, (str, int, float, bool)) or val is None:
                print(f"  {key}: {val_type} = {val!r}")
            elif isinstance(val, list):
                print(f"  {key}: list[{len(val)}]")
            elif isinstance(val, dict):
                print(f"  {key}: dict[{len(val)} keys] = {list(val.keys())}")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    main()
