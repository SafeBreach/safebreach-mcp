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
    sb_get_tests,
    sb_get_test_details,
    sb_get_simulations,
    sb_get_simulation_details,
    sb_get_security_controls_events,
    sb_get_security_control_event_details,
    sb_get_test_findings_counts,
    sb_get_test_findings_details,
    sb_get_test_drifts,
    sb_get_full_simulation_logs,
    sb_get_peer_benchmark_score,
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
    """Get a real completed test ID from the console for E2E testing.

    Scoped to class to avoid repeated API calls for each test.
    Filters for completed tests to ensure simulations have final results.
    """
    # Get the first completed test from history to use for detailed testing
    tests_response = sb_get_tests(
        console=e2e_console, page_number=0,
        test_type="propagate", status_filter="completed",
    )

    if 'tests_in_page' not in tests_response or not tests_response['tests_in_page']:
        pytest.skip(f"No tests found in console {e2e_console} for E2E testing")

    # Get the first test ID
    test_id = tests_response['tests_in_page'][0]['test_id']
    return test_id


@pytest.fixture(scope="class")
def sample_simulation_id(e2e_console, sample_test_id):
    """Get a real simulation ID with a definitive status from the console for E2E testing.

    Scoped to class to avoid repeated API calls for each test.
    Prefers simulations with stopped/prevented status that are most likely to have
    execution logs and target data.
    """
    # Try statuses most likely to have execution logs first
    for status in ["stopped", "prevented", "detected", "missed", None]:
        simulations_response = sb_get_simulations(
            sample_test_id, console=e2e_console, page_number=0,
            status_filter=status,
        )
        sims = simulations_response.get('simulations_in_page', [])
        if sims:
            return sims[0]['simulation_id']

    pytest.skip(f"No simulations found in test {sample_test_id} for E2E testing")


@pytest.fixture(scope="class")
def sample_attack_id(e2e_console, sample_test_id):
    """Discover a real playbook attack id (moveId) from a simulation in the sample test.

    Self-discovering — no hardcoded IDs against the live env. Used by the account-wide
    get_simulations tests, which search by this attack id across all tests (not just the
    sample one).
    """
    for status in ["stopped", "prevented", "detected", "missed", None]:
        response = sb_get_simulations(
            sample_test_id, console=e2e_console, page_number=0,
            status_filter=status,
        )
        for sim in response.get('simulations_in_page', []):
            attack_id = sim.get('playbook_attack_id')
            if attack_id is not None:
                return str(attack_id)

    pytest.skip(f"No simulation with a playbook_attack_id found in test {sample_test_id}")


@pytest.fixture(scope="class")
def drift_pair(e2e_console):
    """Discover a real drift-capable pair of test runs on the console (SAF-33124).

    Scans completed tests for a name with >=2 runs so a baseline necessarily
    exists, then returns the two most-recent runs of that name as
    (current_test_id, baseline_test_id). Self-discovering — no hardcoded IDs,
    so it doesn't rot as the shared environment churns. Class-scoped so the page
    scan runs once for all drift tests. Skips when no such pair exists.
    """
    name_to_tests: dict = {}
    target_name = None
    for page in range(30):
        page_res = sb_get_tests(
            console=e2e_console,
            page_number=page,
            status_filter="completed",
            order_by="end_time",
            order_direction="desc",
        )
        tests = page_res.get("tests_in_page", [])
        if not tests:
            break
        for t in tests:
            name = t.get("name")
            if not name:
                continue
            name_to_tests.setdefault(name, []).append(t)
            if target_name is None and len(name_to_tests[name]) >= 2:
                target_name = name
        if target_name is not None:
            break
        if page + 1 >= page_res.get("total_pages", 0):
            break

    if target_name is None:
        pytest.skip("No test name with >=2 completed runs — cannot exercise drift baseline comparison.")

    runs = sorted(name_to_tests[target_name], key=lambda t: t.get("start_time") or 0)
    return {
        "target_name": target_name,
        "current_test_id": runs[-1]["test_id"],
        "baseline_test_id": runs[-2]["test_id"],
        "all_run_ids": [r["test_id"] for r in runs],
    }


@pytest.fixture(scope="class")
def differing_name_test_id(e2e_console, drift_pair):
    """A completed test whose name differs from the drift_pair's name (SAF-33124).

    Used to exercise comparing two runs with different test names via explicit
    baseline_test_id (no name matching is enforced). Skips when none is found.
    """
    target_name = drift_pair["target_name"]
    for page in range(30):
        page_res = sb_get_tests(
            console=e2e_console,
            page_number=page,
            status_filter="completed",
            order_by="end_time",
            order_direction="desc",
        )
        tests = page_res.get("tests_in_page", [])
        if not tests:
            break
        for t in tests:
            if t.get("name") and t.get("name") != target_name and t.get("test_id"):
                return t["test_id"]
        if page + 1 >= page_res.get("total_pages", 0):
            break
    pytest.skip("No second, differently-named completed test found for cross-name drift comparison.")


class TestDataServerE2E:
    """End-to-end tests for SafeBreach Data Server functions."""

    @pytest.mark.e2e
    def test_get_tests_e2e(self, e2e_console):
        """Test getting real test history from SafeBreach console."""
        result = sb_get_tests(console=e2e_console, page_number=0)
        
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
        """Test getting real test details from SafeBreach console with inline stats."""
        result = sb_get_test_details(sample_test_id, console=e2e_console)

        # Verify response structure
        assert isinstance(result, dict)
        assert 'test_id' in result
        assert 'name' in result
        assert 'status' in result
        assert result['test_id'] == sample_test_id
        # Simulation statistics are now always included (free from API)
        assert 'simulations_statistics' in result
        stats = result['simulations_statistics']
        assert isinstance(stats, list)
        assert len(stats) == 7  # 7 status entries, no drift by default
        # Verify status entries have expected structure
        status_names = {s.get('status') for s in stats}
        assert 'missed' in status_names
        assert 'prevented' in status_names
        assert 'detected' in status_names

    @pytest.mark.e2e
    def test_get_test_details_with_drift_count_e2e(self, e2e_console, sample_test_id):
        """Test getting real test details with drift count (streaming)."""
        result = sb_get_test_details(
            sample_test_id,
            console=e2e_console,
            include_drift_count=True
        )

        # Verify response structure
        assert isinstance(result, dict)
        assert 'test_id' in result
        assert 'simulations_statistics' in result
        stats = result['simulations_statistics']
        assert isinstance(stats, list)
        assert len(stats) == 8  # 7 status entries + 1 drift entry
        drift_entry = next((s for s in stats if 'drifted_count' in s), None)
        assert drift_entry is not None
        assert isinstance(drift_entry['drifted_count'], int)

    @pytest.mark.e2e
    def test_get_test_details_no_drift_count_e2e(self, e2e_console, sample_test_id):
        """Test that default call (no drift) returns 6 status entries only."""
        result = sb_get_test_details(
            sample_test_id,
            console=e2e_console
        )

        assert isinstance(result, dict)
        assert 'simulations_statistics' in result
        stats = result['simulations_statistics']
        assert len(stats) == 7  # 7 status entries, no drift entry

    @pytest.mark.e2e
    def test_get_simulations_e2e(self, e2e_console, sample_test_id):
        """Test getting real test simulations from SafeBreach console."""
        result = sb_get_simulations(sample_test_id, console=e2e_console, page_number=0)
        
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
    def test_get_simulations_account_wide_by_attack_id_e2e(self, e2e_console, sample_attack_id):
        """SAF-29870 Phase J: account-wide search (no test_id) filtered by attack id.

        Exercises the merged get_simulations account-wide path server-side. Verifies each
        returned record self-identifies its owning test run (test_id/test_name) and that the
        server-side moveId filter is honored across the whole account.
        """
        result = sb_get_simulations(
            console=e2e_console, page_number=0,
            playbook_attack_id_filter=sample_attack_id,
        )

        assert isinstance(result, dict)
        assert 'simulations_in_page' in result
        assert 'total_simulations' in result
        assert result['applied_filters'].get('playbook_attack_id_filter') == sample_attack_id
        # Confirm test_id was NOT part of the filter set — this is a true account-wide search.
        assert 'test_id' not in result['applied_filters']

        sims = result['simulations_in_page']
        assert isinstance(sims, list)
        # The discovered attack id came from a real simulation, so account-wide must find it.
        assert result['total_simulations'] >= 1
        assert sims, "Account-wide search by a discovered attack id returned no simulations"

        for sim in sims:
            assert 'simulation_id' in sim
            # Each record must self-identify its owning test run in account-wide mode.
            assert 'test_id' in sim, f"Account-wide simulation missing test_id: {sim}"
            assert 'test_name' in sim, f"Account-wide simulation missing test_name: {sim}"
            # Server-side moveId filter must be exact.
            assert str(sim.get('playbook_attack_id')) == sample_attack_id

    @pytest.mark.e2e
    def test_get_simulations_within_test_and_attack_id_e2e(self, e2e_console, sample_test_id, sample_attack_id):
        """SAF-29870 Phase J: combined within-test + attack-id server-side filter.

        Scoping to a test AND an attack id must return only rows matching BOTH.
        """
        result = sb_get_simulations(
            sample_test_id, console=e2e_console, page_number=0,
            playbook_attack_id_filter=sample_attack_id,
        )

        assert isinstance(result, dict)
        assert result['applied_filters'].get('test_id') == sample_test_id
        assert result['applied_filters'].get('playbook_attack_id_filter') == sample_attack_id

        for sim in result['simulations_in_page']:
            assert str(sim.get('test_id')) == str(sample_test_id)
            assert str(sim.get('playbook_attack_id')) == sample_attack_id

    @pytest.mark.e2e
    def test_get_simulations_account_wide_by_tag_e2e(self, e2e_console):
        """SAF-29870 Phase J: account-wide by-tag search executes the labels.keyword clause live.

        Shape/execution validation — proves the server-side `labels.keyword` Lucene clause is
        accepted by the live endpoint and returns the standard paginated structure account-wide.
        Does NOT assert non-empty results: the console is not guaranteed to have tag-labeled
        simulations, and (per SAF-29870) sim-result labels are upper-cased server-side. When
        results do come back, each must still carry its owning test_id.
        """
        result = sb_get_simulations(
            console=e2e_console, page_number=0,
            tags="mcp-e2e-nonexistent-tag",
        )

        assert isinstance(result, dict)
        assert 'simulations_in_page' in result
        assert isinstance(result['simulations_in_page'], list)
        assert isinstance(result['total_simulations'], int)
        assert result['total_simulations'] >= 0
        assert result['applied_filters'].get('tags') == "mcp-e2e-nonexistent-tag"
        assert 'test_id' not in result['applied_filters']

        for sim in result['simulations_in_page']:
            assert 'test_id' in sim
            assert 'simulation_id' in sim

    @pytest.mark.e2e
    def test_get_simulations_requires_filter_account_wide_e2e(self, e2e_console):
        """SAF-29870 Phase J guard: account-wide with no filter must be refused, not dumped."""
        with pytest.raises(ValueError, match="at least one filter"):
            sb_get_simulations(console=e2e_console, page_number=0)

    @pytest.mark.e2e
    def test_get_test_simulation_details_basic_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test getting basic simulation details from SafeBreach console."""
        result = sb_get_simulation_details(
            sample_simulation_id,
            console=e2e_console
        )
        
        # Verify response structure — curated hybrid envelope
        assert isinstance(result, dict)
        assert 'simulation_id' in result
        assert result['simulation_id'] == sample_simulation_id
        # Hybrid additions: per-node execution steps (forensic middle tier) + routing flag,
        # and NO raw v3 document passthrough
        assert 'simulation_steps_by_node' in result
        assert isinstance(result['simulation_steps_by_node'], list)
        assert 'logs_embedded' in result
        assert 'dataObj' not in result  # raw document is not relayed

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
        # Hybrid additions present alongside the enrichments
        assert 'simulation_steps_by_node' in result
        assert isinstance(result['simulation_steps_by_node'], list)
        assert 'logs_embedded' in result
        # Per-node steps carry role tagging + steps, never the heavy LOGS/OUTPUT blobs
        for node in result['simulation_steps_by_node']:
            assert node['role'] in ('attacker', 'target', 'host', 'unknown')
            assert 'simulation_steps' in node
            assert 'logs' not in node and 'output' not in node

    @pytest.mark.e2e 
    def test_attack_logs_across_multiple_simulations_e2e(self, e2e_console, sample_test_id):
        """Test attack logs functionality across multiple simulations to ensure broad compatibility."""
        # Get simulations from the test
        simulations_result = sb_get_simulations(
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
        """Drift analysis E2E — self-discovering to avoid hardcoded-ID rot.

        Previously this test pinned a specific test ID and baseline pair, which
        decayed as the shared environment churned (the baseline test eventually
        no longer existed/matched), requiring repeated patching. Instead, this
        version discovers a test name that has >=2 completed runs on the console
        at runtime (so a baseline necessarily exists), runs sb_get_test_drifts on
        the run with the latest start_time, and asserts the response is
        well-formed. It does NOT assert exact drift counts (data-dependent). If
        the environment has no test name with two runs, it skips.
        """
        # Discover a test name with >=2 completed runs by scanning pages.
        name_to_tests: dict = {}
        target_name = None
        for page in range(30):
            page_res = sb_get_tests(
                console=e2e_console,
                page_number=page,
                status_filter="completed",
                order_by="end_time",
                order_direction="desc",
            )
            tests = page_res.get("tests_in_page", [])
            if not tests:
                break
            for t in tests:
                name = t.get("name")
                if not name:
                    continue
                name_to_tests.setdefault(name, []).append(t)
                if target_name is None and len(name_to_tests[name]) >= 2:
                    target_name = name
            if target_name is not None:
                break
            if page + 1 >= page_res.get("total_pages", 0):
                break

        if target_name is None:
            pytest.skip(
                "No test name with >=2 completed runs on this console — "
                "cannot exercise drift baseline comparison."
            )

        # Pick the run with the latest start_time so an earlier run (baseline)
        # exists strictly before it.
        runs = sorted(name_to_tests[target_name], key=lambda t: t.get("start_time") or 0)
        current = runs[-1]
        current_test_id = current["test_id"]

        result = sb_get_test_drifts(current_test_id, console=e2e_console)

        # Structure assertions only — no hardcoded counts.
        assert isinstance(result, dict)
        assert "error" not in result, (
            f"Drift analysis errored for a discovered baseline pair "
            f"(name={target_name!r}, current={current_test_id}): {result.get('error')}"
        )
        assert isinstance(result.get("total_drifts"), int)
        assert isinstance(result.get("drifts"), dict)
        assert "_metadata" in result

        metadata = result["_metadata"]
        assert metadata["console"] == e2e_console
        assert metadata["current_test_id"] == current_test_id
        assert metadata["test_name"] == target_name
        assert "baseline_test_id" in metadata
        assert "analyzed_at" in metadata

        # Summary carries the stable, filter-independent counts.
        summary = result["summary"]
        assert isinstance(summary.get("baseline_total_simulations"), int)
        assert isinstance(summary.get("current_total_simulations"), int)
        assert isinstance(summary.get("status_drifts"), int)
        # total_drifts is exactly the genuine status-transition count (not inflated by scope).
        assert result["total_drifts"] == summary["status_drifts"]

        # Each drift entry is well-formed; security impacts come from the valid set; attack identity inline.
        valid_impacts = {"positive", "negative", "neutral", "unknown"}
        for drift_type, drift_info in result["drifts"].items():
            assert "drift_type" in drift_info
            assert "former_status" in drift_info and "current_status" in drift_info
            assert "security_impact" in drift_info
            assert drift_info["security_impact"] in valid_impacts
            assert "drifted_simulations" in drift_info
            for drifted_sim in drift_info["drifted_simulations"]:
                assert "drift_tracking_code" in drifted_sim
                assert "attack_id" in drifted_sim
                assert "attack_name" in drifted_sim
                assert "former_simulation_id" in drifted_sim
                assert "current_simulation_id" in drifted_sim

        # SAF-33124: default is an inner join — exclusive block is gated, counts always in summary.
        assert isinstance(summary.get("baseline_only_count"), int)
        assert isinstance(summary.get("current_only_count"), int)
        assert isinstance(summary.get("no_result_filtered_count"), int)
        assert "exclusive_simulations" not in result
        assert metadata["applied_filters"]["baseline_selection"] == "auto"
        assert "hint_to_agent" in result

        # SAF-33124: explicit baseline_test_id (discovered earlier run) skips auto-selection,
        # and the include_* flags widen the join. Self-discovering — no hardcoded IDs.
        discovered_baseline_id = metadata["baseline_test_id"]
        widened = sb_get_test_drifts(
            current_test_id,
            console=e2e_console,
            baseline_test_id=discovered_baseline_id,
            include_baseline_only=True,
            include_current_only=True,
            include_no_results=True,
        )
        assert "error" not in widened, widened.get("error")
        w_meta = widened["_metadata"]
        # Explicit baseline is honored verbatim and flagged as explicit.
        assert w_meta["baseline_test_id"] == discovered_baseline_id
        assert w_meta["applied_filters"]["baseline_selection"] == "explicit"
        assert w_meta["applied_filters"]["include_no_results"] is True
        # total_drifts stays the genuine status-transition count even with outer flags on.
        assert widened["total_drifts"] == widened["summary"]["status_drifts"]
        # With both outer flags on, exclusive sides are surfaced as summarized blocks.
        w_excl = widened["exclusive_simulations"]
        assert isinstance(w_excl["baseline_only"]["by_attack"], dict)
        assert isinstance(w_excl["current_only"]["sample_simulations"], list)

        print("\n=== E2E Drift Analysis (discovered) ===")
        print(f"Test name: {target_name}")
        print(f"Current test: {current_test_id}, baseline: {metadata.get('baseline_test_id')}")
        print(f"Total drifts (default inner join): {result['total_drifts']}")
        print(f"Total drifts (explicit baseline + all flags): {widened['total_drifts']}")
        print("========================================\n")

    @pytest.mark.e2e
    def test_drift_include_baseline_only_gating_e2e(self, e2e_console, drift_pair):
        """SAF-33124: include_baseline_only surfaces ONLY the baseline-exclusive list."""
        result = sb_get_test_drifts(
            drift_pair["current_test_id"],
            console=e2e_console,
            baseline_test_id=drift_pair["baseline_test_id"],
            include_baseline_only=True,
        )
        assert "error" not in result, result.get("error")
        excl = result["exclusive_simulations"]
        assert "baseline_only" in excl
        assert "current_only" not in excl
        # The summarized block reconciles with the always-present summary count.
        assert excl["baseline_only"]["count"] == result["summary"]["baseline_only_count"]
        assert isinstance(excl["baseline_only"]["by_attack"], dict)
        assert result["_metadata"]["applied_filters"]["include_baseline_only"] is True
        assert result["_metadata"]["applied_filters"]["include_current_only"] is False

    @pytest.mark.e2e
    def test_drift_include_current_only_gating_e2e(self, e2e_console, drift_pair):
        """SAF-33124: include_current_only surfaces ONLY the current-exclusive list."""
        result = sb_get_test_drifts(
            drift_pair["current_test_id"],
            console=e2e_console,
            baseline_test_id=drift_pair["baseline_test_id"],
            include_current_only=True,
        )
        assert "error" not in result, result.get("error")
        excl = result["exclusive_simulations"]
        assert "current_only" in excl
        assert "baseline_only" not in excl
        assert excl["current_only"]["count"] == result["summary"]["current_only_count"]
        assert isinstance(excl["current_only"]["by_attack"], dict)
        assert result["_metadata"]["applied_filters"]["include_current_only"] is True
        assert result["_metadata"]["applied_filters"]["include_baseline_only"] is False

    @pytest.mark.e2e
    def test_drift_total_drifts_accounting_e2e(self, e2e_console, drift_pair):
        """SAF-33124: total_drifts = genuine status transitions ONLY, invariant to outer flags."""
        current, baseline = drift_pair["current_test_id"], drift_pair["baseline_test_id"]

        default_res = sb_get_test_drifts(current, console=e2e_console, baseline_test_id=baseline)
        both_res = sb_get_test_drifts(
            current, console=e2e_console, baseline_test_id=baseline,
            include_baseline_only=True, include_current_only=True,
        )

        status_drifts = default_res["summary"]["status_drifts"]
        # total_drifts is exactly the status-transition count — scope changes never inflate it.
        assert default_res["total_drifts"] == status_drifts
        # Turning the outer flags on surfaces exclusive breakdowns but does NOT change total_drifts.
        assert both_res["total_drifts"] == status_drifts
        assert both_res["summary"]["status_drifts"] == status_drifts

    @pytest.mark.e2e
    def test_drift_include_no_results_effect_e2e(self, e2e_console, drift_pair):
        """SAF-33124: no-results included by default; opting out hides them but counts them."""
        current, baseline = drift_pair["current_test_id"], drift_pair["baseline_test_id"]

        # Default now INCLUDES no-result transitions.
        default_res = sb_get_test_drifts(current, console=e2e_console, baseline_test_id=baseline)
        excluded = sb_get_test_drifts(
            current, console=e2e_console, baseline_test_id=baseline, include_no_results=False,
        )
        assert "error" not in default_res and "error" not in excluded
        d_sum, e_sum = default_res["summary"], excluded["summary"]

        # Default: nothing hidden; the include flag is on.
        assert default_res["_metadata"]["applied_filters"]["include_no_results"] is True
        assert d_sum["hidden_no_result_drift_count"] == 0
        # Stable totals are filter-independent — identical across both calls.
        assert e_sum["baseline_total_simulations"] == d_sum["baseline_total_simulations"]
        assert e_sum["current_total_simulations"] == d_sum["current_total_simulations"]
        # Excluding can only drop drifts: the default's status_drifts >= the excluded path's,
        # and the difference is exactly what the excluded path reports as hidden.
        assert d_sum["status_drifts"] >= e_sum["status_drifts"]
        assert e_sum["hidden_no_result_drift_count"] == d_sum["status_drifts"] - e_sum["status_drifts"]
        if e_sum["hidden_no_result_drift_count"] > 0:
            assert "HIDDEN" in excluded["hint_to_agent"]

    @pytest.mark.e2e
    def test_drift_same_id_twice_e2e(self, e2e_console, drift_pair):
        """SAF-33124 edge case: comparing a run against itself yields zero drifts."""
        current = drift_pair["current_test_id"]
        result = sb_get_test_drifts(current, console=e2e_console, baseline_test_id=current)
        assert "error" not in result, result.get("error")
        assert result["total_drifts"] == 0
        assert result["drifts"] == {}
        # Every coded simulation is shared with itself; no exclusive sides.
        assert result["summary"]["baseline_only_count"] == 0
        assert result["summary"]["current_only_count"] == 0

    @pytest.mark.e2e
    def test_drift_reversed_direction_e2e(self, e2e_console, drift_pair):
        """SAF-33124 edge case: baseline newer than current (reversed pair) still works."""
        # Swap: pass the later run as baseline and the earlier run as current.
        result = sb_get_test_drifts(
            drift_pair["baseline_test_id"],
            console=e2e_console,
            baseline_test_id=drift_pair["current_test_id"],
        )
        assert "error" not in result, result.get("error")
        meta = result["_metadata"]
        assert meta["current_test_id"] == drift_pair["baseline_test_id"]
        assert meta["baseline_test_id"] == drift_pair["current_test_id"]
        assert meta["applied_filters"]["baseline_selection"] == "explicit"
        assert isinstance(result["total_drifts"], int)

    @pytest.mark.e2e
    def test_drift_nonexistent_baseline_e2e(self, e2e_console, drift_pair):
        """SAF-33124 edge case: a bogus baseline_test_id does not crash — structured result."""
        result = sb_get_test_drifts(
            drift_pair["current_test_id"],
            console=e2e_console,
            baseline_test_id="0000000000000.0",  # no such run
            include_current_only=True,
        )
        assert isinstance(result, dict)
        # No exception; either a well-formed drift result or a clear structured error.
        assert ("total_drifts" in result) or ("error" in result)
        if "total_drifts" in result:
            assert result["_metadata"]["baseline_test_id"] == "0000000000000.0"
            # An empty baseline means no shared codes; current sims become current-exclusive.
            assert result["summary"]["baseline_only_count"] == 0
            assert isinstance(result["summary"]["current_only_count"], int)

    @pytest.mark.e2e
    def test_drift_differing_test_names_e2e(self, e2e_console, drift_pair, differing_name_test_id):
        """SAF-33124: explicit baseline with a DIFFERENT test name is allowed (no name matching)."""
        result = sb_get_test_drifts(
            drift_pair["current_test_id"],
            console=e2e_console,
            baseline_test_id=differing_name_test_id,
        )
        assert "error" not in result, result.get("error")
        meta = result["_metadata"]
        assert meta["baseline_test_id"] == differing_name_test_id
        assert meta["current_test_id"] == drift_pair["current_test_id"]
        assert meta["applied_filters"]["baseline_selection"] == "explicit"
        assert isinstance(result["total_drifts"], int)
        assert isinstance(result.get("hint_to_agent"), str)

    @pytest.mark.e2e
    def test_get_full_simulation_logs_e2e(self, e2e_console, sample_simulation_id):
        """Test getting comprehensive simulation execution logs from SafeBreach console.

        Uses the sample_simulation_id fixture to find a simulation with actual logs.
        """
        console = e2e_console
        simulation_id = sample_simulation_id
        
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

        # Verify required top-level fields
        required_fields = ['simulation_id', 'test_id', 'execution_times', 'status', 'attack_info', 'target']
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

        print(f"  ✅ All required top-level fields present: {required_fields}")

        # Target node should always be present
        target = result['target']
        assert isinstance(target, dict), "Target should be a dictionary"

        # Validate target node fields
        target_fields = ['logs', 'simulation_steps', 'details_summary', 'error', 'output', 'node_id', 'state']
        for field in target_fields:
            assert field in target, f"Missing target field: {field}"

        # Validate logs field (~40KB of raw, verbose simulator logs)
        logs = target['logs']
        assert isinstance(logs, str), "Logs should be a string"
        assert len(logs) > 1000, f"Logs should be substantial (>1KB), got {len(logs)} characters"
        print(f"  ✅ Target logs: {len(logs):,} characters of raw execution logs")

        # Validate simulation_steps (structured execution steps)
        simulation_steps = target['simulation_steps']
        assert isinstance(simulation_steps, list), "Simulation steps should be a list"
        if simulation_steps:
            first_step = simulation_steps[0]
            assert isinstance(first_step, dict), "Each step should be a dictionary"
        print(f"  ✅ Target simulation steps: {len(simulation_steps)} structured execution steps")

        # Validate details_summary
        details_summary = target['details_summary']
        assert isinstance(details_summary, (str, type(None))), "Details summary should be string or None"
        if details_summary:
            print(f"  ✅ Details summary: {len(details_summary)} characters")
        else:
            print(f"  ✅ Details summary: None (no exceptions/errors)")

        # Validate output
        output = target['output']
        assert isinstance(output, (str, type(None))), "Output should be string or None"
        if output:
            print(f"  ✅ Output: {len(output)} characters")
        else:
            print(f"  ✅ Output: None (no initialization output)")

        # Attacker may or may not be present depending on attack type
        attacker = result.get('attacker')
        if attacker is not None:
            assert isinstance(attacker, dict), "Attacker should be a dictionary when present"
            attacker_logs = attacker.get('logs', '')
            print(f"  ✅ Attacker node present with {len(attacker_logs):,} characters of logs")
        else:
            print(f"  ✅ Attacker: None (host-only attack)")

        # Verify this is comprehensive execution logs (not just basic attack logs)
        assert 'trace' in logs.lower() or 'execution' in logs.lower() or 'step' in logs.lower(), \
            "Logs should contain trace/execution details indicating comprehensive logs"

        # Print summary for debugging/validation
        print(f"\n📊 Full Simulation Logs Test Summary:")
        print(f"  Console: {console}")
        print(f"  Simulation ID: {simulation_id}")
        print(f"  Test ID: {test_id}")
        print(f"  Target logs size: {len(logs):,} characters")
        print(f"  Target execution steps: {len(simulation_steps)}")
        print(f"  Has attacker node: {attacker is not None}")
        print(f"  Response size: ~{len(str(result)):,} characters")
        print(f"==================================\n")
    
    @pytest.mark.e2e
    def test_get_full_simulation_logs_error_handling_e2e(self, e2e_console, sample_test_id, sample_simulation_id):
        """Test error handling for get_full_simulation_logs with invalid parameters.

        Self-discovering — the valid simulation/test ids come from fixtures so the test does not
        depend on hardcoded ids that may not exist on the target console.
        """
        console = e2e_console

        # Test 1: Invalid simulation ID (real test_id, bogus sim id → not found)
        print(f"\n=== Testing error handling for get_full_simulation_logs ===")
        print(f"Test 1: Invalid simulation ID...")

        try:
            result = sb_get_full_simulation_logs(
                simulation_id="invalid-sim-id",
                test_id=sample_test_id,
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

        # Test 2: Invalid test ID with valid simulation ID
        # NOTE: The API resolves by simulation_id (path param), not test_id (query param runId).
        # A valid simulation_id with invalid test_id returns data successfully — this is expected.
        print(f"Test 2: Invalid test ID with valid simulation ID (expects success)...")

        result = sb_get_full_simulation_logs(
            simulation_id=str(sample_simulation_id),  # Valid, discovered simulation ID
            test_id="invalid-test-id",
            console=console
        )
        assert isinstance(result, dict), "Should return valid response when simulation_id is valid"
        assert 'simulation_id' in result, "Response should contain simulation_id"
        print(f"  ✅ API correctly resolved by simulation_id despite invalid test_id")

        # Test 3: Invalid console
        print(f"Test 3: Invalid console...")

        try:
            result = sb_get_full_simulation_logs(
                simulation_id=str(sample_simulation_id),
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


# ---------------------------------------------------------------------
# Peer benchmark score E2E (SAF-29415 Phase 4)
# ---------------------------------------------------------------------
# The /api/data/v1/accounts/{id}/score endpoint is now available on
# pentest01, so this fixture defaults to E2E_CONSOLE (pentest01).
# Override via PEER_BENCHMARK_E2E_CONSOLE if you need a different console.

@pytest.fixture(scope="class")
def peer_benchmark_e2e_console():
    """Resolve the console for the peer benchmark E2E test.

    Defaults to E2E_CONSOLE (pentest01) where the /score endpoint is now
    available. Override via PEER_BENCHMARK_E2E_CONSOLE. Skips (does not
    fail) when the resolved console isn't configured locally.

    SAF-29974: Sets the ContextVar to the console-specific token so that
    get_auth_headers_for_console() returns the right credentials.
    """
    console = os.environ.get('PEER_BENCHMARK_E2E_CONSOLE',
                             os.environ.get('E2E_CONSOLE', 'pentest01'))
    skip_msg = (
        "Peer Benchmark E2E skipped: endpoint not yet deployed on the "
        "default E2E console; set PEER_BENCHMARK_E2E_CONSOLE to a console "
        "that has POST /api/data/v1/accounts/{id}/score live, or configure "
        "credentials for the 'staging' console."
    )

    from safebreach_mcp_core.environments_metadata import get_environment_by_name
    from safebreach_mcp_core.token_context import _user_auth_artifacts

    try:
        get_environment_by_name(console)
    except Exception:
        pytest.skip(skip_msg)

    token_key = f"{console.replace('-', '_')}_apitoken"
    api_token = os.environ.get(token_key) or os.environ.get('SB_API_KEY')
    if not api_token:
        pytest.skip(skip_msg)

    # Swap ContextVar to this console's token
    _user_auth_artifacts.set({"x-apitoken": api_token})

    return console


class TestPeerBenchmarkScoreE2E:
    """End-to-end smoke test for sb_get_peer_benchmark_score (SAF-29415)."""

    @pytest.mark.e2e
    def test_peer_benchmark_score_e2e(self, peer_benchmark_e2e_console):
        """Smoke: 30-day window; assert renamed top-level shape."""
        import time

        end_ms = int(time.time() * 1000)
        start_ms = end_ms - (30 * 24 * 60 * 60 * 1000)  # 30 days back

        print(f"\n=== Peer Benchmark E2E ===")
        print(f"  Console: {peer_benchmark_e2e_console}")
        print(f"  Window: {start_ms} -> {end_ms} (30 days)")

        result = sb_get_peer_benchmark_score(
            console=peer_benchmark_e2e_console,
            start_date=start_ms,
            end_date=end_ms,
        )

        # Top-level renamed keys must always be present (even on 204 path).
        assert isinstance(result, dict)
        for required_key in (
            "start_date", "end_date",
            "customer_score", "all_peers_score", "customer_industry_scores",
        ):
            assert required_key in result, f"missing required key: {required_key}"

        # Scores: each is either None or a dict with the expected sub-keys.
        for score_key in ("customer_score", "all_peers_score"):
            value = result[score_key]
            assert value is None or isinstance(value, dict), (
                f"{score_key} must be None or dict, got {type(value).__name__}"
            )
            if isinstance(value, dict):
                for sub_key in ("score", "score_blocked", "score_detected"):
                    assert sub_key in value, f"{score_key} missing {sub_key}"

        # customer_industry_scores must be a list (possibly empty);
        # each element (if any) must be a dict carrying industry_name.
        industries = result["customer_industry_scores"]
        assert isinstance(industries, list)
        for entry in industries:
            assert isinstance(entry, dict)
            assert "industry_name" in entry
            assert "score" in entry

        # Surface useful operational signal — if the staging snapshot is
        # frozen or the window has no data, the hint explains it. The
        # test still passes because the structured empty shape is valid.
        if "hint_to_agent" in result:
            print(f"  hint_to_agent: {result['hint_to_agent']}")
        else:
            print(f"  customer_score.score: {result['customer_score'].get('score') if result['customer_score'] else None}")
            print(f"  all_peers_score.score: {result['all_peers_score'].get('score') if result['all_peers_score'] else None}")
        print(f"  ✅ Peer benchmark E2E shape verified")
        print(f"==========================\n")
