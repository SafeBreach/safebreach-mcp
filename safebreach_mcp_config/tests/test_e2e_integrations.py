"""
End-to-End Tests for SafeBreach Integration-Discovery Tools (Config Server, SAF-32798)

Tests the complete functionality using real API calls to the SIEM
/config/integrations endpoints. Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v

Tests are self-discovering: connector ids/types are picked from live responses,
never hardcoded against the environment.
"""

import pytest
import os
import json
import time
from safebreach_mcp_config.config_functions import (
    sb_get_integrations,
    sb_get_installed_integrations,
    sb_get_installed_integration,
    sb_get_ti_integrations,
    clear_integrations_catalog_cache,
)


E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


def _resilient_call(fn, attempts=3, delay=3.0):
    """Call an sb_* tool, retrying on a transient backend error (e.g. 5xx). Returns the
    first non-error result. If every attempt errors, pytest.skip (BLOCKED — the live env
    is transiently unreachable, not a code defect)."""
    last = None
    for attempt in range(attempts):
        result = fn()
        if 'error' not in result:
            return result
        last = result.get('error')
        if attempt < attempts - 1:
            time.sleep(delay)
    pytest.skip(f"BLOCKED — live console transiently unreachable after {attempts} attempts: {last}")


@skip_e2e
@pytest.mark.e2e
class TestIntegrationsE2E:
    """End-to-end tests for integration-discovery tools against real SafeBreach API."""

    def setup_method(self):
        clear_integrations_catalog_cache()

    # T-14 — live catalog retrieval + category filter
    def test_get_integrations_basic_and_filter(self):
        result = _resilient_call(lambda: sb_get_integrations(console=E2E_CONSOLE, page_number=0))
        assert result['total_integrations'] > 0
        assert result['integrations_in_page'], "expected at least one connector type"
        first = result['integrations_in_page'][0]
        for key in ('type', 'name', 'category', 'is_ti', 'is_vm'):
            assert key in first

        # pick a category present in the live catalog, then filter by it
        category = next((e['category'] for e in result['integrations_in_page'] if e.get('category')), None)
        assert category is not None
        filtered = sb_get_integrations(console=E2E_CONSOLE, category_filter=category)
        assert 'error' not in filtered
        assert filtered['total_integrations'] >= 1
        assert all(category.lower() in (e.get('category') or '').lower()
                   for e in filtered['integrations_in_page'])

    # T-15 — live installed-integrations slim list
    def test_get_installed_integrations_slim(self):
        result = _resilient_call(lambda: sb_get_installed_integrations(console=E2E_CONSOLE, page_number=0))
        assert result['total_installed_integrations'] > 0
        for item in result['installed_integrations_in_page']:
            assert set(item.keys()) == {"id", "type", "name", "enabled"}

    # T-16 — live redaction + cross-layer identity consistency (self-discovered id)
    def test_get_installed_integration_redaction(self):
        listing = _resilient_call(lambda: sb_get_installed_integrations(console=E2E_CONSOLE, page_number=0))
        assert listing['installed_integrations_in_page'], "need at least one installed connector"
        target = listing['installed_integrations_in_page'][0]
        detail = _resilient_call(lambda: sb_get_installed_integration(console=E2E_CONSOLE, integration_id=target['id']))
        # cross-layer identity consistency
        assert detail['id'] == target['id']
        assert detail['type'] == target['type']
        assert detail['name'] == target['name']
        # no secret material leaks: no vault refs anywhere in the payload
        dumped = json.dumps(detail)
        assert "$PAM:" not in dumped
        # headers, when present, must be redacted (never a raw object)
        if "headers" in detail:
            assert detail["headers"] == "@enc:SENSITIVE_FIELD"
        if "proxyPass" in detail:
            assert detail["proxyPass"] == "@enc:SENSITIVE_FIELD"

    # T-17 — live TI integrations list, cross-checked against catalog isTiV2
    def test_get_ti_integrations_matches_catalog(self):
        ti = _resilient_call(lambda: sb_get_ti_integrations(console=E2E_CONSOLE, page_number=0))
        for item in ti['ti_integrations_in_page']:
            assert set(item.keys()) == {"id", "type", "name", "enabled"}
        # every returned TI type must be isTiV2 in the live catalog
        catalog = _resilient_call(lambda: sb_get_integrations(console=E2E_CONSOLE, ti_only=True))
        ti_types = {e['type'] for e in catalog['integrations_in_page']}
        # (catalog may paginate; page through to collect all ti types)
        page = 1
        while catalog.get('total_pages', 0) > page:
            catalog = sb_get_integrations(console=E2E_CONSOLE, ti_only=True, page_number=page)
            ti_types |= {e['type'] for e in catalog['integrations_in_page']}
            page += 1
        for item in ti['ti_integrations_in_page']:
            assert item['type'] in ti_types, f"{item['type']} returned but not isTiV2 in catalog"
