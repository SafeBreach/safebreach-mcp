"""
End-to-End Tests for SafeBreach Scenario Tools (Config Server)

Tests the complete functionality using real API calls to the scenarios and
scenarioCategories endpoints. Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v
"""

import pytest
import os
from safebreach_mcp_config.config_functions import (
    sb_get_scenarios,
    sb_get_scenario_details,
    clear_scenarios_cache,
    clear_categories_cache,
)


E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


@skip_e2e
@pytest.mark.e2e
class TestScenarioE2E:
    """End-to-end tests for scenario tools against real SafeBreach API."""

    def setup_method(self):
        clear_scenarios_cache()
        clear_categories_cache()

    def test_get_scenarios_basic(self):
        """Test basic scenario listing returns valid paginated response."""
        result = sb_get_scenarios(console=E2E_CONSOLE, page_number=0)

        assert 'page_number' in result
        assert 'total_pages' in result
        assert 'total_scenarios' in result
        assert 'scenarios_in_page' in result
        assert 'hint_to_agent' in result

        assert result['total_scenarios'] > 0
        assert len(result['scenarios_in_page']) > 0
        assert len(result['scenarios_in_page']) <= 10

    def test_scenario_structure(self):
        """Verify each scenario in the list has expected keys."""
        result = sb_get_scenarios(console=E2E_CONSOLE, page_number=0)

        for scenario in result['scenarios_in_page']:
            assert 'id' in scenario
            assert 'name' in scenario
            assert 'createdBy' in scenario
            assert 'category_names' in scenario
            assert 'step_count' in scenario
            assert 'is_ready_to_run' in scenario
            assert 'recommended' in scenario
            assert isinstance(scenario['category_names'], list)
            assert isinstance(scenario['step_count'], int)
            assert isinstance(scenario['is_ready_to_run'], bool)

    def test_name_filter(self):
        """Test name filter with a known substring."""
        result = sb_get_scenarios(console=E2E_CONSOLE, name_filter="CISA")

        assert result['total_scenarios'] > 0
        for scenario in result['scenarios_in_page']:
            assert 'cisa' in scenario['name'].lower()

    def test_creator_filter_safebreach(self):
        """Test filtering for SafeBreach-created (OOB) scenarios."""
        result = sb_get_scenarios(console=E2E_CONSOLE, creator_filter="safebreach")

        assert result['total_scenarios'] > 0
        for scenario in result['scenarios_in_page']:
            assert scenario['createdBy'] == 'SafeBreach'

    def test_recommended_filter(self):
        """Test filtering for recommended scenarios."""
        result = sb_get_scenarios(console=E2E_CONSOLE, recommended_filter=True)

        assert result['total_scenarios'] > 0
        for scenario in result['scenarios_in_page']:
            assert scenario['recommended'] is True

    def test_ready_to_run_filter(self):
        """Test filtering for ready-to-run scenarios."""
        result = sb_get_scenarios(console=E2E_CONSOLE, ready_to_run_filter=True)

        assert result['total_scenarios'] > 0
        for scenario in result['scenarios_in_page']:
            assert scenario['is_ready_to_run'] is True

    def test_pagination_hint(self):
        """Test that pagination hint works correctly."""
        result = sb_get_scenarios(console=E2E_CONSOLE, page_number=0)

        if result['total_pages'] > 1:
            assert result['hint_to_agent'] is not None
            assert 'page_number=1' in result['hint_to_agent']

    def test_get_scenario_details(self):
        """Test getting simplified scenario details by ID."""
        list_result = sb_get_scenarios(console=E2E_CONSOLE, page_number=0)
        first_id = list_result['scenarios_in_page'][0]['id']

        detail = sb_get_scenario_details(str(first_id), console=E2E_CONSOLE)

        assert str(detail['id']) == str(first_id)
        assert 'name' in detail
        assert 'steps' in detail
        assert 'source_type' in detail
        assert 'category_names' in detail
        assert 'step_count' in detail
        assert 'is_ready_to_run' in detail
        assert 'has_wait_steps' in detail
        assert isinstance(detail['category_names'], list)
        # Steps are simplified
        for step in detail['steps']:
            assert 'name' in step
            assert 'attack_selection' in step
            assert 'mode' in step['attack_selection']

    def test_get_scenario_details_not_found(self):
        """Test that non-existent scenario ID raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            sb_get_scenario_details("00000000-0000-0000-0000-000000000000", console=E2E_CONSOLE)

    def test_scenario_details_simplified_format(self):
        """Test that details return simplified LLM-readable format."""
        list_result = sb_get_scenarios(
            console=E2E_CONSOLE, creator_filter="safebreach", page_number=0
        )
        first_id = list_result['scenarios_in_page'][0]['id']

        detail = sb_get_scenario_details(str(first_id), console=E2E_CONSOLE)

        assert detail['source_type'] == 'oob'
        assert 'steps' in detail
        assert 'createdBy' in detail
        assert 'createdAt' in detail
        assert 'updatedAt' in detail
        # Simplified — no raw execution mechanics
        assert 'actions' not in detail
        assert 'edges' not in detail
        assert 'phases' not in detail

    def test_custom_scenarios_returned(self):
        """Custom plans should be fetched and returned with source_type='custom'."""
        result = sb_get_scenarios(console=E2E_CONSOLE, creator_filter="custom")

        assert result['total_scenarios'] > 0, \
            "Expected custom plans on pentest01 (My Scenarios tab)"
        for scenario in result['scenarios_in_page']:
            assert scenario['source_type'] == 'custom'
            assert scenario['category_names'] == []
            assert scenario['recommended'] is False

    def test_merged_oob_and_custom_by_default(self):
        """No filter should return both OOB scenarios and custom plans."""
        result = sb_get_scenarios(console=E2E_CONSOLE, page_number=0)

        # Sanity: there should be more than just OOB on pentest01
        oob_only = sb_get_scenarios(console=E2E_CONSOLE, creator_filter="safebreach")
        custom_only = sb_get_scenarios(console=E2E_CONSOLE, creator_filter="custom")

        assert result['total_scenarios'] == \
            oob_only['total_scenarios'] + custom_only['total_scenarios']

    def test_get_custom_plan_details_by_integer_id(self):
        """Custom plan details should be retrievable and in simplified format."""
        list_result = sb_get_scenarios(console=E2E_CONSOLE, creator_filter="custom")
        first_custom = list_result['scenarios_in_page'][0]
        plan_id = first_custom['id']

        detail = sb_get_scenario_details(str(plan_id), console=E2E_CONSOLE)

        assert detail['source_type'] == 'custom'
        assert str(detail['id']) == str(plan_id)
        assert 'steps' in detail
        assert 'has_wait_steps' in detail
        # Same simplified step format as OOB
        for step in detail['steps']:
            assert 'name' in step
            assert 'attack_selection' in step
