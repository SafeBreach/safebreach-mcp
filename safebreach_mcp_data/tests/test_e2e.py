"""
SafeBreach MCP Data Server End-to-End Tests

These tests run against real SafeBreach APIs and require:
- Valid SafeBreach console access
- API tokens configured in environment/AWS
- Network access to SafeBreach consoles
"""

import pytest
import os
from typing import Dict, Any

from safebreach_mcp_data.data_functions import (
    sb_get_tests_history,
    sb_get_test_details, 
    sb_get_test_simulations,
    sb_get_simulation_details,
    sb_get_security_controls_events,
    sb_get_security_control_event_details,
    sb_get_test_findings_counts,
    sb_get_test_findings_details
)


@pytest.fixture
def e2e_console():
    """Get console name for E2E tests from environment."""
    console = os.environ.get('E2E_CONSOLE', 'pentest01')
    if not console:
        pytest.skip("E2E_CONSOLE environment variable not set")
    return console


@pytest.fixture
def sample_test_id(e2e_console):
    """Get a real test ID from the console for E2E testing."""
    # Get the first test from history to use for detailed testing
    tests_response = sb_get_tests_history(e2e_console, page_number=0, test_type="propagate")
    
    if 'tests_in_page' not in tests_response or not tests_response['tests_in_page']:
        pytest.skip(f"No tests found in console {e2e_console} for E2E testing")
    
    # Get the first test ID
    test_id = tests_response['tests_in_page'][0]['test_id']
    return test_id


@pytest.fixture 
def sample_simulation_id(e2e_console, sample_test_id):
    """Get a real simulation ID from the console for E2E testing."""
    # Get simulations from the sample test
    simulations_response = sb_get_test_simulations(e2e_console, sample_test_id, page_number=0)
    
    if 'simulations_in_page' not in simulations_response or not simulations_response['simulations_in_page']:
        pytest.skip(f"No simulations found in test {sample_test_id} for E2E testing")
    
    # Get the first simulation ID
    simulation_id = simulations_response['simulations_in_page'][0]['simulation_id']
    return simulation_id


class TestDataServerE2E:
    """End-to-end tests for SafeBreach Data Server functions."""

    @pytest.mark.e2e
    def test_get_tests_history_e2e(self, e2e_console):
        """Test getting real test history from SafeBreach console."""
        result = sb_get_tests_history(e2e_console, page_number=0)
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'tests_in_page' in result
        assert 'total_tests' in result
        assert 'page_number' in result
        
        # Verify we got some tests
        assert isinstance(result['tests_in_page'], list)
        if result['tests_in_page']:
            test = result['tests_in_page'][0]
            assert 'test_id' in test
            assert 'name' in test
            assert 'status' in test

    @pytest.mark.e2e
    def test_get_test_details_e2e(self, e2e_console, sample_test_id):
        """Test getting real test details from SafeBreach console."""
        result = sb_get_test_details(e2e_console, sample_test_id)
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'test_id' in result
        assert 'name' in result
        assert 'status' in result
        assert result['test_id'] == sample_test_id

    @pytest.mark.e2e 
    def test_get_test_details_with_statistics_e2e(self, e2e_console, sample_test_id):
        """Test getting real test details with simulation statistics."""
        result = sb_get_test_details(
            e2e_console, 
            sample_test_id, 
            include_simulations_statistics=True
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'test_id' in result
        assert 'simulations_statistics' in result
        assert isinstance(result['simulations_statistics'], list)

    @pytest.mark.e2e
    def test_get_test_simulations_e2e(self, e2e_console, sample_test_id):
        """Test getting real test simulations from SafeBreach console."""
        result = sb_get_test_simulations(e2e_console, sample_test_id, page_number=0)
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'simulations_in_page' in result
        assert 'total_simulations' in result
        assert 'page_number' in result
        
        # Verify we got some simulations
        assert isinstance(result['simulations_in_page'], list)
        if result['simulations_in_page']:
            simulation = result['simulations_in_page'][0]
            assert 'simulation_id' in simulation
            assert 'status' in simulation

    @pytest.mark.e2e
    def test_get_test_simulation_details_basic_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting basic simulation details from SafeBreach console."""
        result = sb_get_simulation_details(
            e2e_console, 
            sample_simulation_id
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'simulation_id' in result
        assert result['simulation_id'] == sample_simulation_id

    @pytest.mark.e2e
    def test_get_test_simulation_details_with_mitre_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting simulation details with MITRE techniques - THIS SHOULD HIT YOUR BREAKPOINT!"""
        result = sb_get_simulation_details(
            e2e_console, 
            sample_simulation_id,
            include_mitre_techniques=True
        )
        
        # Verify response structure 
        assert isinstance(result, dict)
        assert 'simulation_id' in result
        assert result['simulation_id'] == sample_simulation_id
        
        # MITRE techniques should be included
        assert 'mitre_techniques' in result
        assert isinstance(result['mitre_techniques'], list)

    @pytest.mark.e2e
    def test_get_test_simulation_details_with_attack_logs_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting simulation details with attack logs - THIS SHOULD ALSO HIT YOUR BREAKPOINT!"""
        result = sb_get_simulation_details(
            e2e_console,
            sample_simulation_id, 
            include_full_attack_logs=True
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'simulation_id' in result 
        assert result['simulation_id'] == sample_simulation_id
        
        # Attack logs should be included
        assert 'full_attack_logs_by_hosts' in result
        assert isinstance(result['full_attack_logs_by_hosts'], list)

    @pytest.mark.e2e
    def test_get_test_simulation_details_full_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting simulation details with all extensions - THIS WILL DEFINITELY HIT YOUR BREAKPOINT!"""
        result = sb_get_simulation_details(
            e2e_console,
            sample_simulation_id,
            include_mitre_techniques=True,
            include_full_attack_logs=True
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'simulation_id' in result
        assert result['simulation_id'] == sample_simulation_id
        
        # All extensions should be included
        assert 'mitre_techniques' in result
        assert 'full_attack_logs_by_hosts' in result
        assert isinstance(result['mitre_techniques'], list)
        assert isinstance(result['full_attack_logs_by_hosts'], list)

    @pytest.mark.e2e
    def test_get_security_controls_events_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting real security control events."""
        result = sb_get_security_controls_events(
            e2e_console,
            sample_test_id,
            sample_simulation_id,
            page_number=0
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'events_in_page' in result
        assert 'total_events' in result
        assert isinstance(result['events_in_page'], list)

    @pytest.mark.e2e
    def test_get_test_findings_counts_e2e(self, e2e_console, sample_test_id):
        """Test getting real test findings counts."""
        result = sb_get_test_findings_counts(e2e_console, sample_test_id)
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'findings_counts' in result
        assert isinstance(result['findings_counts'], list)

    @pytest.mark.e2e
    def test_get_test_findings_details_e2e(self, e2e_console, sample_test_id):
        """Test getting real test findings details."""
        result = sb_get_test_findings_details(
            e2e_console, 
            sample_test_id,
            page_number=0
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'findings_in_page' in result
        assert 'total_findings' in result
        assert isinstance(result['findings_in_page'], list)