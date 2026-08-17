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
from safebreach_mcp_config.config_functions import (
    sb_get_integrations,
    clear_integrations_catalog_cache,
)


E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


@skip_e2e
@pytest.mark.e2e
class TestIntegrationsE2E:
    """End-to-end tests for integration-discovery tools against real SafeBreach API."""

    def setup_method(self):
        clear_integrations_catalog_cache()

    # T-14 — live catalog retrieval + category filter
    def test_get_integrations_basic_and_filter(self):
        result = sb_get_integrations(console=E2E_CONSOLE, page_number=0)
        assert 'error' not in result, result.get('error')
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
