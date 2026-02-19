"""
Memory Profile Baseline for MCP Caching System

Standalone script that measures memory consumption of the MCP caching system
under two scenarios: caching disabled (default) and caching enabled (unbounded).

This script does NOT start MCP servers. It directly imports and manipulates
the cache dictionaries from each server module.

Usage:
    uv run python tests/memory_profile_baseline.py
    uv run python tests/memory_profile_baseline.py --output results.json
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import resource
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from typing import Any, Dict, List

import psutil

# ---------------------------------------------------------------------------
# Imports from the MCP server modules
# ---------------------------------------------------------------------------
from safebreach_mcp_core.cache_config import reset_cache_config

from safebreach_mcp_config.config_functions import simulators_cache
from safebreach_mcp_data.data_functions import (
    findings_cache,
    full_simulation_logs_cache,
    security_control_events_cache,
    simulations_cache,
    tests_cache,
)
from safebreach_mcp_playbook.playbook_functions import playbook_cache
from safebreach_mcp_studio.studio_functions import studio_draft_cache

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUM_CONSOLES = 5
TESTS_PER_CONSOLE = 10
SIMULATIONS_PER_TEST = 2
TOTAL_QUERIES = 100
SAMPLE_INTERVAL = 25

# Realistic payload sizes (in bytes)
SIMULATOR_DATA_SIZE = 10 * 1024       # ~10 KB
TEST_DATA_SIZE = 5 * 1024             # ~5 KB
SIMULATION_DATA_SIZE = 2 * 1024       # ~2 KB
SECURITY_EVENT_DATA_SIZE = 1 * 1024   # ~1 KB
FINDINGS_DATA_SIZE = 1 * 1024         # ~1 KB
FULL_SIM_LOGS_DATA_SIZE = 40 * 1024   # ~40 KB
PLAYBOOK_DATA_SIZE = 100 * 1024       # ~100 KB
STUDIO_DRAFT_DATA_SIZE = 5 * 1024     # ~5 KB


# ---------------------------------------------------------------------------
# Mock data generators
# ---------------------------------------------------------------------------

def _make_simulator_data(console: str, index: int) -> Dict[str, Any]:
    """Generate a realistic-sized simulator mock payload (~10 KB)."""
    return {
        "id": f"sim-{console}-{index}",
        "name": f"Simulator {index} on {console}",
        "isConnected": index % 2 == 0,
        "isEnabled": True,
        "version": "4.2.1",
        "OS": {"type": "Linux", "version": "Ubuntu 22.04"},
        "labels": [f"label-{i}" for i in range(5)],
        "isCritical": index % 3 == 0,
        "payload": "x" * SIMULATOR_DATA_SIZE,
    }


def _make_test_data(console: str, test_index: int) -> Dict[str, Any]:
    """Generate a realistic-sized test summary mock payload (~5 KB)."""
    return {
        "test_id": f"test-{console}-{test_index}",
        "name": f"Test Run {test_index}",
        "status": "completed",
        "test_type": "BAS",
        "start_time": time.time() - 3600,
        "end_time": time.time(),
        "duration": 3600,
        "simulations_statistics": [],
        "payload": "x" * TEST_DATA_SIZE,
    }


def _make_simulation_data(console: str, test_index: int, sim_index: int) -> Dict[str, Any]:
    """Generate a realistic-sized simulation result mock payload (~2 KB)."""
    return {
        "simulation_id": f"sim-result-{console}-{test_index}-{sim_index}",
        "status": "detected",
        "playbookAttackId": f"attack-{sim_index}",
        "playbookAttackName": f"Attack {sim_index}",
        "end_time": time.time(),
        "is_drifted": False,
        "drift_tracking_code": f"drift-{console}-{test_index}-{sim_index}",
        "payload": "x" * SIMULATION_DATA_SIZE,
    }


def _make_security_event_data(console: str, test_index: int, sim_index: int) -> Dict[str, Any]:
    """Generate a realistic-sized security control event mock payload (~1 KB)."""
    return {
        "id": f"event-{console}-{test_index}-{sim_index}",
        "connectorName": "SIEM Connector",
        "fields": {
            "product": "Firewall",
            "vendor": "Vendor A",
            "action": ["block"],
            "sourceHosts": ["10.0.0.1"],
            "destHosts": ["10.0.0.2"],
        },
        "payload": "x" * SECURITY_EVENT_DATA_SIZE,
    }


def _make_findings_data() -> List[Dict[str, Any]]:
    """Generate a realistic-sized findings mock payload (~1 KB per finding)."""
    return [
        {
            "type": "credential_exposure",
            "timestamp": str(time.time()),
            "attributes": {"host": f"host-{i}", "ports": [80, 443]},
            "payload": "x" * FINDINGS_DATA_SIZE,
        }
        for i in range(3)
    ]


def _make_full_sim_logs_data(console: str, test_index: int, sim_index: int) -> Dict[str, Any]:
    """Generate a realistic-sized full simulation logs mock payload (~40 KB)."""
    return {
        "simulation_id": f"sim-{console}-{test_index}-{sim_index}",
        "test_id": f"test-{console}-{test_index}",
        "logs": "x" * FULL_SIM_LOGS_DATA_SIZE,
        "simulation_steps": [{"step": i, "action": f"step-{i}"} for i in range(20)],
        "error": None,
        "output": "completed successfully",
    }


def _make_playbook_data(console: str) -> Dict[str, Any]:
    """Generate a realistic-sized playbook attack mock payload (~100 KB)."""
    return {
        "id": 1001,
        "name": f"Playbook Attack for {console}",
        "description": "A simulated attack technique",
        "techniques": [{"id": f"T{i}", "name": f"Technique {i}"} for i in range(50)],
        "payload": "x" * PLAYBOOK_DATA_SIZE,
    }


def _make_studio_draft_data(attack_id: int) -> Dict[str, Any]:
    """Generate a realistic-sized studio draft mock payload (~5 KB)."""
    return {
        "draft_id": attack_id,
        "name": f"Draft Attack {attack_id}",
        "status": "draft",
        "attack_type": "host",
        "os_constraint": "All",
        "parameters_count": 2,
        "payload": "x" * STUDIO_DRAFT_DATA_SIZE,
    }


# ---------------------------------------------------------------------------
# Memory measurement helpers
# ---------------------------------------------------------------------------

def get_rss_mb() -> float:
    """Return current process RSS in megabytes via psutil."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def get_peak_rss_mb() -> float:
    """
    Return peak RSS in megabytes via resource.getrusage.

    On macOS ru_maxrss is in bytes; on Linux it is in kilobytes.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    ru_maxrss = usage.ru_maxrss
    if platform.system() == "Darwin":
        return ru_maxrss / (1024 * 1024)
    else:
        # Linux: ru_maxrss is in KB
        return ru_maxrss / 1024


def clear_all_caches() -> None:
    """Clear every cache dict from all server modules."""
    simulators_cache.clear()
    tests_cache.clear()
    simulations_cache.clear()
    security_control_events_cache.clear()
    findings_cache.clear()
    full_simulation_logs_cache.clear()
    playbook_cache.clear()
    studio_draft_cache.clear()


def count_cache_entries() -> Dict[str, int]:
    """Count entries in each cache dict."""
    return {
        "simulators": len(simulators_cache),
        "tests": len(tests_cache),
        "simulations": len(simulations_cache),
        "security_control_events": len(security_control_events_cache),
        "findings": len(findings_cache),
        "full_simulation_logs": len(full_simulation_logs_cache),
        "playbook": len(playbook_cache),
        "studio_drafts": len(studio_draft_cache),
    }


# ---------------------------------------------------------------------------
# Cache population (simulates agent queries)
# ---------------------------------------------------------------------------

def populate_caches(query_index: int) -> None:
    """
    Simulate a single agent-like query by populating all caches.

    Distributes queries across consoles/tests/simulations to create
    realistic key diversity.
    """
    console_idx = query_index % NUM_CONSOLES
    test_idx = query_index % TESTS_PER_CONSOLE
    sim_idx = query_index % SIMULATIONS_PER_TEST
    console = f"console-{console_idx}"
    now = time.time()

    # --- Config server: simulators_cache ---
    # Pattern: cache[key] = (data, timestamp)
    sim_cache_key = f"simulators_{console}"
    simulators_cache[sim_cache_key] = (
        [_make_simulator_data(console, i) for i in range(10)],
        now,
    )

    # --- Data server: tests_cache ---
    # Pattern: cache[key] = (data, timestamp)
    tests_cache_key = f"tests_{console}"
    tests_cache[tests_cache_key] = (
        [_make_test_data(console, i) for i in range(TESTS_PER_CONSOLE)],
        now,
    )

    # --- Data server: simulations_cache ---
    # Pattern: cache[key] = (data, timestamp)
    test_id = f"test-{console}-{test_idx}"
    sims_cache_key = f"simulations_{console}_{test_id}"
    simulations_cache[sims_cache_key] = (
        [_make_simulation_data(console, test_idx, j) for j in range(SIMULATIONS_PER_TEST)],
        now,
    )

    # --- Data server: security_control_events_cache ---
    # Pattern: cache[key] = {'data': ..., 'timestamp': ...}
    sim_id = f"sim-result-{console}-{test_idx}-{sim_idx}"
    sec_cache_key = f"{console}:{test_id}:{sim_id}"
    security_control_events_cache[sec_cache_key] = {
        "data": [_make_security_event_data(console, test_idx, sim_idx)],
        "timestamp": now,
    }

    # --- Data server: findings_cache ---
    # Pattern: cache[key] = {'data': ..., 'timestamp': ...}
    findings_key = f"{console}:{test_id}"
    findings_cache[findings_key] = {
        "data": _make_findings_data(),
        "timestamp": now,
    }

    # --- Data server: full_simulation_logs_cache ---
    # Pattern: cache[key] = (data, timestamp)
    logs_key = f"full_simulation_logs_{console}_{sim_id}_{test_id}"
    full_simulation_logs_cache[logs_key] = (
        _make_full_sim_logs_data(console, test_idx, sim_idx),
        now,
    )

    # --- Playbook server: playbook_cache ---
    # Pattern: cache[key] = {'data': ..., 'timestamp': ...}
    playbook_key = f"attacks_{console}"
    playbook_cache[playbook_key] = {
        "data": [_make_playbook_data(console) for _ in range(20)],
        "timestamp": now,
    }

    # --- Studio server: studio_draft_cache ---
    # Pattern: cache[key] = {'data': ..., 'timestamp': ...}
    attack_id = 10000 + query_index
    studio_key = f"studio_draft_{console}_{attack_id}"
    studio_draft_cache[studio_key] = {
        "data": _make_studio_draft_data(attack_id),
        "timestamp": now,
    }


# ---------------------------------------------------------------------------
# Scenario runners
# ---------------------------------------------------------------------------

def run_scenario_disabled() -> Dict[str, Any]:
    """
    Scenario A: Caching disabled.

    Populates caches directly but verifies they should remain empty
    when caching is disabled (simulating what would happen with real code
    paths that check is_caching_enabled() before writing).

    Since we are directly writing to cache dicts to measure overhead,
    we clear them after each write to simulate the disabled behavior,
    then verify counts are zero.
    """
    # Configure environment
    os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
    reset_cache_config()
    clear_all_caches()
    gc.collect()

    tracemalloc.start()
    rss_start = get_rss_mb()
    rss_samples: List[float] = [rss_start]

    for i in range(TOTAL_QUERIES):
        # In disabled mode, the real code paths skip cache writes.
        # We simulate this by NOT populating caches.
        # Instead, we create the mock data objects (to measure baseline
        # allocation cost) and immediately discard them.
        console_idx = i % NUM_CONSOLES
        test_idx = i % TESTS_PER_CONSOLE
        sim_idx = i % SIMULATIONS_PER_TEST
        console = f"console-{console_idx}"

        # Create data objects (same as enabled path) but do not store them
        _ = [_make_simulator_data(console, j) for j in range(10)]
        _ = [_make_test_data(console, j) for j in range(TESTS_PER_CONSOLE)]
        _ = [_make_simulation_data(console, test_idx, j) for j in range(SIMULATIONS_PER_TEST)]
        _ = [_make_security_event_data(console, test_idx, sim_idx)]
        _ = _make_findings_data()
        _ = _make_full_sim_logs_data(console, test_idx, sim_idx)
        _ = [_make_playbook_data(console) for _ in range(20)]
        _ = _make_studio_draft_data(10000 + i)

        if (i + 1) % SAMPLE_INTERVAL == 0:
            rss_samples.append(get_rss_mb())

    # Verify caches are empty (since we never populated them)
    cache_counts = count_cache_entries()
    assert all(v == 0 for v in cache_counts.values()), (
        f"Expected all caches to be empty in disabled scenario, got: {cache_counts}"
    )

    _, tracemalloc_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    rss_end = get_rss_mb()
    rss_peak = get_peak_rss_mb()
    rss_samples.append(rss_end)

    return {
        "rss_start_mb": round(rss_start, 2),
        "rss_peak_mb": round(rss_peak, 2),
        "rss_end_mb": round(rss_end, 2),
        "tracemalloc_peak_mb": round(tracemalloc_peak / (1024 * 1024), 2),
        "rss_samples_mb": [round(s, 2) for s in rss_samples],
        "cache_entry_counts": cache_counts,
    }


def run_scenario_enabled_buggy() -> Dict[str, Any]:
    """
    Scenario B: Caching enabled (current unbounded behavior).

    Directly populates caches as the real code paths would when
    is_caching_enabled() returns True. Demonstrates unbounded growth.
    """
    # Configure environment
    os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
    reset_cache_config()
    clear_all_caches()
    gc.collect()

    tracemalloc.start()
    rss_start = get_rss_mb()
    rss_samples: List[float] = [rss_start]

    for i in range(TOTAL_QUERIES):
        populate_caches(i)

        if (i + 1) % SAMPLE_INTERVAL == 0:
            rss_samples.append(get_rss_mb())

    cache_counts = count_cache_entries()

    _, tracemalloc_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    rss_end = get_rss_mb()
    rss_peak = get_peak_rss_mb()
    rss_samples.append(rss_end)

    return {
        "rss_start_mb": round(rss_start, 2),
        "rss_peak_mb": round(rss_peak, 2),
        "rss_end_mb": round(rss_end, 2),
        "tracemalloc_peak_mb": round(tracemalloc_peak / (1024 * 1024), 2),
        "rss_samples_mb": [round(s, 2) for s in rss_samples],
        "cache_entry_counts": cache_counts,
    }


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def print_summary(results: Dict[str, Any]) -> None:
    """Print a human-readable summary to stderr."""
    print("\n" + "=" * 70, file=sys.stderr)
    print("  MCP Cache Memory Profile Baseline", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"  Timestamp : {results['timestamp']}", file=sys.stderr)
    print(f"  Platform  : {results['platform']}", file=sys.stderr)
    print(f"  Python    : {results['python_version']}", file=sys.stderr)
    print(f"  Queries   : {TOTAL_QUERIES} simulated agent queries", file=sys.stderr)
    print(f"  Consoles  : {NUM_CONSOLES}, Tests/console: {TESTS_PER_CONSOLE}, "
          f"Sims/test: {SIMULATIONS_PER_TEST}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)

    for scenario_key, label in [
        ("caching_disabled", "Scenario A: Caching DISABLED"),
        ("caching_enabled_buggy", "Scenario B: Caching ENABLED (unbounded)"),
    ]:
        scenario = results["scenarios"][scenario_key]
        print(f"\n  {label}", file=sys.stderr)
        print(f"    RSS start     : {scenario['rss_start_mb']:.2f} MB", file=sys.stderr)
        print(f"    RSS end       : {scenario['rss_end_mb']:.2f} MB", file=sys.stderr)
        print(f"    RSS peak (OS) : {scenario['rss_peak_mb']:.2f} MB", file=sys.stderr)
        print(f"    tracemalloc   : {scenario['tracemalloc_peak_mb']:.2f} MB (Python heap peak)",
              file=sys.stderr)
        rss_growth = scenario["rss_end_mb"] - scenario["rss_start_mb"]
        print(f"    RSS growth    : {rss_growth:+.2f} MB", file=sys.stderr)
        print(f"    RSS samples   : {scenario['rss_samples_mb']}", file=sys.stderr)
        print(f"    Cache entries : {scenario['cache_entry_counts']}", file=sys.stderr)

    print("\n" + "-" * 70, file=sys.stderr)
    thresholds = results["acceptance_thresholds"]
    print("  Acceptance Thresholds:", file=sys.stderr)
    print(f"    Max RSS growth (disabled)         : "
          f"{thresholds['max_rss_growth_disabled_mb']} MB", file=sys.stderr)
    print(f"    Max RSS growth (enabled, fixed)    : "
          f"{thresholds['max_rss_growth_enabled_fixed_mb']} MB", file=sys.stderr)
    print(f"    Max peak RSS above baseline        : "
          f"{thresholds['max_peak_rss_above_baseline_mb']} MB", file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Memory profile baseline for MCP caching system"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON output to FILE instead of stdout",
    )
    args = parser.parse_args()

    # --- Scenario A: Caching disabled ---
    print("Running Scenario A: Caching disabled ...", file=sys.stderr)
    scenario_disabled = run_scenario_disabled()

    # Clean up between scenarios
    clear_all_caches()
    gc.collect()

    # --- Scenario B: Caching enabled (buggy / unbounded) ---
    print("Running Scenario B: Caching enabled (unbounded) ...", file=sys.stderr)
    scenario_enabled = run_scenario_enabled_buggy()

    # Clean up after scenarios
    clear_all_caches()
    os.environ.pop("SB_MCP_ENABLE_LOCAL_CACHING", None)
    reset_cache_config()
    gc.collect()

    # --- Build results ---
    results: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.system().lower(),
        "python_version": platform.python_version(),
        "scenarios": {
            "caching_disabled": scenario_disabled,
            "caching_enabled_buggy": scenario_enabled,
        },
        "acceptance_thresholds": {
            "max_rss_growth_disabled_mb": 10,
            "max_rss_growth_enabled_fixed_mb": 50,
            "max_peak_rss_above_baseline_mb": 100,
        },
    }

    # --- Output ---
    json_output = json.dumps(results, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_output)
            f.write("\n")
        print(f"Results written to: {args.output}", file=sys.stderr)
    else:
        print(json_output)

    # --- Human-readable summary ---
    print_summary(results)


if __name__ == "__main__":
    main()
