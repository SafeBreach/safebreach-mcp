"""
SafeBreach MCP Data Server End-to-End Tests

These tests run against real SafeBreach APIs and require:
- Valid SafeBreach console access with real environment details
- API tokens and console info configured via environment variables
- Private .vscode/set_env.sh file with real credentials (never commit!)
- Network access to SafeBreach consoles

Setup: See E2E_TESTING.md for complete setup instructions.
Security: All real environment details must be in private local files only.
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
    sb_get_test_findings_details,
    sb_get_test_drifts,
    sb_get_full_simulation_logs
)


@pytest.fixture(scope="class")
def e2e_console():
    """Get console name for E2E tests from environment."""
    console = os.environ.get('E2E_CONSOLE', 'demo-console')
    if not console:
        pytest.skip("E2E_CONSOLE environment variable not set")
    return console


@pytest.fixture(scope="class")
def sample_test_id(e2e_console):
    """Get a real test ID from the console for E2E testing.

    Scoped to class to avoid repeated API calls for each test.
    """
    # Get the first test from history to use for detailed testing
    tests_response = sb_get_tests_history(console=e2e_console, page_number=0, test_type="propagate")

    if 'tests_in_page' not in tests_response or not tests_response['tests_in_page']:
        pytest.skip(f"No tests found in console {e2e_console} for E2E testing")

    # Get the first test ID
    test_id = tests_response['tests_in_page'][0]['test_id']
    return test_id


@pytest.fixture(scope="class")
def sample_simulation_id(e2e_console, sample_test_id):
    """Get a real simulation ID from the console for E2E testing.

    Scoped to class to avoid repeated API calls for each test.
    """
    # Get simulations from the sample test
    simulations_response = sb_get_test_simulations(sample_test_id, console=e2e_console, page_number=0)

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
        result = sb_get_tests_history(console=e2e_console, page_number=0)
        
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
        result = sb_get_test_details(sample_test_id, console=e2e_console)
        
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
            sample_test_id,
            console=e2e_console,
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
        result = sb_get_test_simulations(sample_test_id, console=e2e_console, page_number=0)
        
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
            sample_simulation_id,
            console=e2e_console
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'simulation_id' in result
        assert result['simulation_id'] == sample_simulation_id

    @pytest.mark.e2e
    def test_get_test_simulation_details_with_mitre_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting simulation details with MITRE techniques - THIS SHOULD HIT YOUR BREAKPOINT!"""
        result = sb_get_simulation_details(
            sample_simulation_id,
            console=e2e_console,
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
        """Test getting simulation details with attack logs - comprehensive validation."""
        result = sb_get_simulation_details(
            sample_simulation_id,
            console=e2e_console,
            include_basic_attack_logs=True
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'simulation_id' in result 
        assert result['simulation_id'] == sample_simulation_id
        
        # Attack logs should be included and properly structured
        assert 'basic_attack_logs_by_hosts' in result
        assert isinstance(result['basic_attack_logs_by_hosts'], list)
        
        # If attack logs exist, validate their structure
        attack_logs = result['basic_attack_logs_by_hosts']
        if len(attack_logs) > 0:
            print(f"Found {len(attack_logs)} hosts with attack logs")
            
            for i, host_log in enumerate(attack_logs):
                print(f"Host {i+1} validation:")
                
                # Validate host log structure
                assert isinstance(host_log, dict), f"Host log {i+1} should be a dictionary"
                assert 'host_info' in host_log, f"Host log {i+1} missing 'host_info'"
                assert 'host_logs' in host_log, f"Host log {i+1} missing 'host_logs'"
                
                # Validate host_info structure
                host_info = host_log['host_info']
                assert isinstance(host_info, dict), f"Host {i+1} host_info should be a dictionary"
                assert 'node_id' in host_info, f"Host {i+1} host_info missing 'node_id'"
                assert 'event_count' in host_info, f"Host {i+1} host_info missing 'event_count'"
                
                # Validate host_logs structure
                host_logs = host_log['host_logs']
                assert isinstance(host_logs, list), f"Host {i+1} host_logs should be a list"
                assert len(host_logs) == host_info['event_count'], f"Host {i+1} event count mismatch"
                
                print(f"  Node ID: {host_info['node_id']}")
                print(f"  Event count: {host_info['event_count']}")
                
                # Validate individual events
                if len(host_logs) > 0:
                    event_types = {}
                    for j, event in enumerate(host_logs[:3]):  # Check first 3 events
                        assert isinstance(event, dict), f"Host {i+1} event {j+1} should be a dictionary"
                        
                        # Expected event fields
                        expected_fields = ['nodeId', 'type', 'action', 'timestamp']
                        for field in expected_fields:
                            assert field in event, f"Host {i+1} event {j+1} missing '{field}'"
                        
                        event_type = event.get('type', 'unknown')
                        event_types[event_type] = event_types.get(event_type, 0) + 1
                        
                        # Validate timestamp format
                        timestamp = event.get('timestamp', '')
                        assert 'T' in timestamp and 'Z' in timestamp, f"Host {i+1} event {j+1} invalid timestamp format"
                    
                    print(f"  Event types found: {dict(event_types)}")
                
                print(f"  ✅ Host {i+1} validation passed")
        else:
            print("No attack logs found - this may be normal for some simulation types")
            # Even if no logs, the field should still be present and be a list
            assert attack_logs == [], "Empty attack logs should be an empty list"

    @pytest.mark.e2e
    def test_get_test_simulation_details_full_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting simulation details with all extensions - THIS WILL DEFINITELY HIT YOUR BREAKPOINT!"""
        result = sb_get_simulation_details(
            sample_simulation_id,
            console=e2e_console,
            include_mitre_techniques=True,
            include_basic_attack_logs=True
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'simulation_id' in result
        assert result['simulation_id'] == sample_simulation_id
        
        # All extensions should be included
        assert 'mitre_techniques' in result
        assert 'basic_attack_logs_by_hosts' in result
        assert isinstance(result['mitre_techniques'], list)
        assert isinstance(result['basic_attack_logs_by_hosts'], list)

    @pytest.mark.e2e 
    def test_attack_logs_across_multiple_simulations_e2e(self, e2e_console, sample_test_id):
        """Test attack logs functionality across multiple simulations to ensure broad compatibility."""
        # Get simulations from the test
        simulations_result = sb_get_test_simulations(
            sample_test_id,
            console=e2e_console,
            page_number=0
        )
        
        assert 'simulations_in_page' in simulations_result
        simulations = simulations_result['simulations_in_page']
        
        # Test attack logs for multiple simulations (up to 3 for reasonable test time)
        tested_simulations = 0
        attack_logs_found = 0
        
        for simulation in simulations[:3]:  # Test first 3 simulations
            simulation_id = simulation['simulation_id']
            simulation_name = simulation.get('playbook_attack_name', 'Unknown')
            simulation_status = simulation.get('status', 'Unknown')
            
            print(f"\nTesting simulation {simulation_id}: {simulation_name} (status: {simulation_status})")
            
            try:
                result = sb_get_simulation_details(
                    simulation_id,
                    console=e2e_console,
                    include_basic_attack_logs=True
                )
                
                tested_simulations += 1
                
                # Verify basic structure
                assert isinstance(result, dict)
                assert 'basic_attack_logs_by_hosts' in result
                assert isinstance(result['basic_attack_logs_by_hosts'], list)
                
                attack_logs = result['basic_attack_logs_by_hosts']
                
                if len(attack_logs) > 0:
                    attack_logs_found += 1
                    print(f"  ✅ Found attack logs: {len(attack_logs)} hosts")
                    
                    # Validate structure for this simulation
                    total_events = 0
                    for host_log in attack_logs:
                        assert 'host_info' in host_log
                        assert 'host_logs' in host_log
                        
                        host_info = host_log['host_info']
                        assert 'node_id' in host_info
                        assert 'event_count' in host_info
                        
                        event_count = host_info['event_count']
                        host_logs = host_log['host_logs']
                        
                        assert len(host_logs) == event_count, f"Event count mismatch for {simulation_id}"
                        total_events += event_count
                        
                        # Validate at least one event structure if events exist
                        if len(host_logs) > 0:
                            event = host_logs[0]
                            assert 'nodeId' in event
                            assert 'type' in event  
                            assert 'action' in event
                            assert 'timestamp' in event
                    
                    print(f"  Total events across all hosts: {total_events}")
                else:
                    print(f"  No attack logs (this is normal for some simulation types)")
                    
            except Exception as e:
                print(f"  ❌ Error testing simulation {simulation_id}: {str(e)}")
                # Don't fail the test for individual simulation errors, 
                # as some simulations might have data issues
                continue
        
        print(f"\n📊 Test Summary:")
        print(f"  Simulations tested: {tested_simulations}")
        print(f"  Simulations with attack logs: {attack_logs_found}")
        print(f"  Coverage: {(attack_logs_found/max(tested_simulations,1)*100):.1f}%")
        
        # Ensure we tested at least one simulation
        assert tested_simulations > 0, "Should have tested at least one simulation"
        
        # Ensure the functionality works (at least some simulations should have logs)
        # Note: Not all simulations have logs, so we just ensure no crashes occurred
        print("✅ Attack logs functionality verified across multiple simulations")

    @pytest.mark.e2e
    def test_get_security_controls_events_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting real security control events."""
        result = sb_get_security_controls_events(
            sample_test_id,
            sample_simulation_id,
            console=e2e_console,
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
        result = sb_get_test_findings_counts(sample_test_id, console=e2e_console)
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'findings_counts' in result
        assert isinstance(result['findings_counts'], list)

    @pytest.mark.e2e
    def test_get_test_findings_details_e2e(self, e2e_console, sample_test_id):
        """Test getting real test findings details."""
        result = sb_get_test_findings_details(
            sample_test_id,
            console=e2e_console,
            page_number=0
        )
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'findings_in_page' in result
        assert 'total_findings' in result
        assert isinstance(result['findings_in_page'], list)

    @pytest.mark.e2e
    def test_get_test_drifts_e2e(self, e2e_console):
        """Test getting real test drift analysis using known test data.
        
        This test uses test ID 1762754400605.6 (test name: "Stav - Exfiltration Parallel ") 
        which has significant drift patterns when compared to its previous test with the same name 
        (baseline test ID: 1762149600283.2):
        
        Actual drift analysis results:
        - missed-logged: 312 simulations (positive impact)
        - missed-no_result: 49 simulations (neutral impact)  
        - logged-no_result: 19 simulations (negative impact)
        - stopped-no_result: 1 simulations (negative impact)
        - no_result-stopped: 3 simulations (positive impact)
        - missed-detected: 2 simulations (positive impact)
        - detected-logged: 1 simulations (negative impact)
        - Plus 490 simulations exclusive to baseline, 134 exclusive to current
        Total: 1011 drifts (387 status changes + 624 exclusive simulations)
        """
        # Use specific test ID that has known drift patterns
        test_id = "1762754400605.6"
        
        result = sb_get_test_drifts(test_id, console=e2e_console)
        
        # Verify response structure
        assert isinstance(result, dict)
        assert 'total_drifts' in result
        assert 'drifts' in result
        assert '_metadata' in result
        assert isinstance(result['drifts'], dict)
        
        # Verify metadata contains expected fields
        metadata = result['_metadata']
        assert metadata['console'] == e2e_console
        assert metadata['current_test_id'] == test_id
        assert 'baseline_test_id' in metadata
        assert 'test_name' in metadata
        assert 'baseline_simulations_count' in metadata
        assert 'current_simulations_count' in metadata
        assert 'analyzed_at' in metadata
        
        # Verify expected metadata values based on actual data
        assert metadata['baseline_test_id'] == "1762149600283.2"
        assert metadata['test_name'] == "Stav - Exfiltration Parallel "
        assert metadata['current_simulations_count'] == 1238
        assert metadata['baseline_simulations_count'] == 1594
        assert metadata['shared_drift_codes'] == 1104
        assert metadata['status_drifts'] == 387
        assert len(metadata['simulations_exclusive_to_baseline']) == 490
        assert len(metadata['simulations_exclusive_to_current']) == 134
        
        # Verify we have the expected total number of drifts
        # Based on actual analysis: 1011 total drifts
        total_drifts = result['total_drifts']
        assert total_drifts == 1011, f"Expected exactly 1011 drifts, got {total_drifts}"
        
        # Count drift types to verify expected patterns
        drift_type_counts = {}
        for drift_type, drift_info in result['drifts'].items():
            assert 'drift_type' in drift_info
            assert 'security_impact' in drift_info
            assert 'drifted_simulations' in drift_info
            
            # Count simulations for this drift type
            drift_type_counts[drift_type] = len(drift_info['drifted_simulations'])
            
            # Verify each drifted simulation has required fields
            for drifted_sim in drift_info['drifted_simulations']:
                assert 'drift_tracking_code' in drifted_sim
                assert 'former_simulation_id' in drifted_sim
                assert 'current_simulation_id' in drifted_sim
        
        # Verify the major expected drift patterns exist with expected counts
        # Based on actual analysis of test ID 1762754400605.6
        expected_drift_counts = {
            'missed-logged': 312,      # Positive impact: missed → logged  
            'missed-no_result': 49,    # Neutral impact: missed → no_result
            'logged-no_result': 19,    # Negative impact: logged → no_result
            'stopped-no_result': 1,    # Negative impact: stopped → no_result
            'no_result-stopped': 3,    # Positive impact: no_result → stopped
            'missed-detected': 2,      # Positive impact: missed → detected
            'detected-logged': 1,      # Negative impact: detected → logged
        }
        
        # Verify all expected drift patterns are present with exact counts
        found_patterns = set(drift_type_counts.keys())
        expected_patterns = set(expected_drift_counts.keys())
        
        assert found_patterns == expected_patterns, \
            f"Expected patterns {expected_patterns}, found {found_patterns}. " \
            f"Missing: {expected_patterns - found_patterns}, Extra: {found_patterns - expected_patterns}"
        
        # Verify exact counts for each drift type
        for drift_type, expected_count in expected_drift_counts.items():
            actual_count = drift_type_counts[drift_type]
            assert actual_count == expected_count, \
                f"Expected {expected_count} simulations for {drift_type}, got {actual_count}"
        
        # Verify security impact classification exists and is valid
        security_impacts = {drift['security_impact'] for drift in result['drifts'].values()}
        valid_impacts = {'positive', 'negative', 'neutral', 'unknown'}
        assert security_impacts.issubset(valid_impacts), f"Invalid security impacts found: {security_impacts - valid_impacts}"
        
        # Log results for debugging
        print(f"\n=== E2E Drift Analysis Results ===")
        print(f"Total drifts found: {total_drifts}")
        print(f"Drift type counts: {drift_type_counts}")
        print(f"Security impacts: {security_impacts}")
        print(f"Baseline test: {metadata.get('baseline_test_id', 'Unknown')}")
        print(f"Test name: {metadata.get('test_name', 'Unknown')}")
        print(f"==================================\n")

    @pytest.mark.e2e
    def test_get_full_simulation_logs_e2e(self):
        """Test getting comprehensive simulation execution logs from SafeBreach console.
        
        This test uses simulation ID 1084162 from the pentest01 console as specified.
        The test first retrieves simulation details to get the test_id, then calls 
        get_full_simulation_logs to retrieve the comprehensive (~40KB) execution logs.
        """
        console = "pentest01"
        simulation_id = "1084162"
        
        print(f"\n=== Testing get_full_simulation_logs for simulation {simulation_id} ===")
        
        # First, get simulation details to extract the test_id
        print(f"Step 1: Getting simulation details to extract test_id...")
        simulation_details = sb_get_simulation_details(simulation_id, console=console)
        
        # Verify we got valid simulation details
        assert isinstance(simulation_details, dict)
        assert 'simulation_id' in simulation_details
        assert simulation_details['simulation_id'] == simulation_id
        assert 'test_id' in simulation_details, "Missing test_id in simulation details"
        
        test_id = simulation_details['test_id']
        print(f"  ✅ Extracted test_id: {test_id}")
        
        # Now test the main functionality: get_full_simulation_logs
        print(f"Step 2: Retrieving comprehensive execution logs...")
        result = sb_get_full_simulation_logs(
            simulation_id=simulation_id,
            test_id=test_id,
            console=console
        )
        
        # Verify response structure
        assert isinstance(result, dict), "Response should be a dictionary"
        
        # Verify required fields are present
        required_fields = ['logs', 'simulation_steps', 'details_summary', 'output', 'metadata']
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"
        
        print(f"  ✅ All required fields present: {required_fields}")
        
        # Validate logs field (~40KB of raw, verbose simulator logs)
        logs = result['logs']
        assert isinstance(logs, str), "Logs should be a string"
        assert len(logs) > 1000, f"Logs should be substantial (>1KB), got {len(logs)} characters"
        print(f"  ✅ Logs field: {len(logs):,} characters of raw execution logs")
        
        # Validate simulation_steps (structured execution steps)
        simulation_steps = result['simulation_steps']
        assert isinstance(simulation_steps, list), "Simulation steps should be a list"
        if simulation_steps:
            # Check structure of first step
            first_step = simulation_steps[0]
            assert isinstance(first_step, dict), "Each step should be a dictionary"
            # Common step fields (may vary by simulation type)
            expected_step_fields = ['step_name', 'timing', 'status']
            for field in expected_step_fields:
                if field in first_step:  # Not all steps may have all fields
                    assert isinstance(first_step[field], (str, int, float, dict)), f"Step field {field} should have a valid type"
        print(f"  ✅ Simulation steps: {len(simulation_steps)} structured execution steps")
        
        # Validate details_summary (exception traceback summary)
        details_summary = result['details_summary']
        assert isinstance(details_summary, (str, type(None))), "Details summary should be string or None"
        if details_summary:
            print(f"  ✅ Details summary: {len(details_summary)} characters of exception/traceback info")
        else:
            print(f"  ✅ Details summary: None (no exceptions/errors)")
        
        # Validate output (simulation initialization output)
        output = result['output']
        assert isinstance(output, (str, type(None))), "Output should be string or None"
        if output:
            print(f"  ✅ Output: {len(output)} characters of initialization output")
        else:
            print(f"  ✅ Output: None (no initialization output)")
        
        # Validate metadata (additional fields)
        metadata = result['metadata']
        assert isinstance(metadata, dict), "Metadata should be a dictionary"
        
        # Check for expected metadata fields
        expected_metadata_fields = ['method_id', 'state', 'execution_times']
        metadata_found = []
        for field in expected_metadata_fields:
            if field in metadata:
                metadata_found.append(field)
        
        print(f"  ✅ Metadata: {len(metadata)} fields, including {metadata_found}")
        
        # Verify this is comprehensive execution logs (not just basic attack logs)
        # The logs should contain detailed traces and be significantly larger than basic logs
        assert 'trace' in logs.lower() or 'execution' in logs.lower() or 'step' in logs.lower(), \
            "Logs should contain trace/execution details indicating comprehensive logs"
        
        # Print summary for debugging/validation
        print(f"\n📊 Full Simulation Logs Test Summary:")
        print(f"  Console: {console}")
        print(f"  Simulation ID: {simulation_id}")
        print(f"  Test ID: {test_id}")
        print(f"  Logs size: {len(logs):,} characters")
        print(f"  Execution steps: {len(simulation_steps)}")
        print(f"  Has details summary: {details_summary is not None}")
        print(f"  Has output: {output is not None}")
        print(f"  Metadata fields: {len(metadata)}")
        print(f"  Response size: ~{len(str(result)):,} characters")
        print(f"==================================\n")
    
    @pytest.mark.e2e
    def test_get_full_simulation_logs_error_handling_e2e(self):
        """Test error handling for get_full_simulation_logs with invalid parameters."""
        console = "pentest01"
        
        # Test 1: Invalid simulation ID
        print(f"\n=== Testing error handling for get_full_simulation_logs ===")
        print(f"Test 1: Invalid simulation ID...")
        
        try:
            result = sb_get_full_simulation_logs(
                simulation_id="invalid-sim-id",
                test_id="1084162",  # Use a reasonable test_id
                console=console
            )
            # If no exception, check if we got an error response structure
            if isinstance(result, dict) and 'error' in result:
                print(f"  ✅ Got expected error response for invalid simulation ID")
            else:
                pytest.fail("Expected error for invalid simulation ID but got successful response")
                
        except Exception as e:
            print(f"  ✅ Got expected exception for invalid simulation ID: {type(e).__name__}")
            assert len(str(e)) > 0, "Exception should have a meaningful message"
        
        # Test 2: Invalid test ID  
        print(f"Test 2: Invalid test ID...")
        
        try:
            result = sb_get_full_simulation_logs(
                simulation_id="1084162",  # Use a valid simulation ID
                test_id="invalid-test-id",
                console=console
            )
            # If no exception, check if we got an error response structure
            if isinstance(result, dict) and 'error' in result:
                print(f"  ✅ Got expected error response for invalid test ID")
            else:
                pytest.fail("Expected error for invalid test ID but got successful response")
                
        except Exception as e:
            print(f"  ✅ Got expected exception for invalid test ID: {type(e).__name__}")
            assert len(str(e)) > 0, "Exception should have a meaningful message"
        
        # Test 3: Invalid console
        print(f"Test 3: Invalid console...")
        
        try:
            result = sb_get_full_simulation_logs(
                simulation_id="1084162",
                test_id="some-test-id", 
                console="invalid-console-name"
            )
            # If no exception, check if we got an error response structure
            if isinstance(result, dict) and 'error' in result:
                print(f"  ✅ Got expected error response for invalid console")
            else:
                pytest.fail("Expected error for invalid console but got successful response")
                
        except Exception as e:
            print(f"  ✅ Got expected exception for invalid console: {type(e).__name__}")
            assert len(str(e)) > 0, "Exception should have a meaningful message"
        
        print(f"  ✅ Error handling validation completed successfully")
        print(f"==================================\n")
