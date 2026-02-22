"""
Memory Profile Baseline for MCP Caching System (E2E — Real API Data)

Measures memory consumption by calling real SafeBreach API endpoints and
letting the cache dictionaries fill with production-sized data. Runs two
scenarios:
  A. Caching DISABLED  — API calls happen but nothing is retained
  B. Caching ENABLED   — unbounded dicts accumulate real responses

Requires environment setup (API tokens, console config):
    source .vscode/set_env.sh
    uv run python tests/memory_profile_baseline.py --output results.json

The workload iterates across multiple tests and simulations per test,
creating the multiplicative key cardinality that causes unbounded growth
in the current (buggy) caching implementation.
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
from typing import Any

import psutil

# ---------------------------------------------------------------------------
# Imports from the MCP server modules
# ---------------------------------------------------------------------------
from safebreach_mcp_core.cache_config import reset_cache_config

from safebreach_mcp_config.config_functions import (
    sb_get_console_simulators,
    simulators_cache,
)
from safebreach_mcp_data.data_functions import (
    findings_cache,
    full_simulation_logs_cache,
    sb_get_full_simulation_logs,
    sb_get_security_controls_events,
    sb_get_test_findings_details,
    sb_get_test_simulations,
    sb_get_tests_history,
    security_control_events_cache,
    simulations_cache,
    tests_cache,
)
from safebreach_mcp_playbook.playbook_functions import (
    playbook_cache,
    sb_get_playbook_attacks,
)
from safebreach_mcp_studio.studio_functions import studio_draft_cache


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONSOLE = "pentest01"
DEFAULT_NUM_TESTS = 10
DEFAULT_SIMS_PER_TEST = 5
DEFAULT_PLAYBOOK_PAGES = 10  # Cap playbook pages; each page re-fetches entire KB when uncached


# ---------------------------------------------------------------------------
# Memory measurement helpers
# ---------------------------------------------------------------------------

def get_rss_mb() -> float:
    """Return current process RSS in megabytes via psutil."""
    proc = psutil.Process(os.getpid())
    return proc.memory_info().rss / (1024 * 1024)


def get_peak_rss_mb() -> float:
    """Return peak RSS in MB via resource.getrusage.

    On macOS ru_maxrss is bytes; on Linux it is kilobytes.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    ru_maxrss = usage.ru_maxrss
    if platform.system() == "Darwin":
        return ru_maxrss / (1024 * 1024)
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


def count_cache_entries() -> dict[str, int]:
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


def log(msg: str) -> None:
    """Print a timestamped progress message to stderr."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Workload: real API calls against a live SafeBreach console
# ---------------------------------------------------------------------------

def discover_workload(
    console: str,
    num_tests: int,
    sims_per_test: int,
) -> list[dict[str, Any]]:
    """Call the test-history API once to discover test IDs, then for each
    test discover simulation IDs. Returns a list of work items.

    Each work item: {"test_id": str, "simulation_ids": [str, ...]}

    This discovery phase always runs with caching DISABLED so it does not
    pollute the measurement scenarios.
    """
    os.environ.pop("SB_MCP_CACHE_CONFIG", None)
    os.environ.pop("SB_MCP_CACHE_DATA", None)
    os.environ.pop("SB_MCP_CACHE_PLAYBOOK", None)
    os.environ.pop("SB_MCP_CACHE_STUDIO", None)
    reset_cache_config()
    clear_all_caches()

    log(f"Discovering workload from {console} "
        f"(target: {num_tests} tests × {sims_per_test} sims)...")

    # Collect test IDs across pages until we have enough
    test_ids: list[str] = []
    page = 0
    while len(test_ids) < num_tests:
        resp = sb_get_tests_history(console=console, page_number=page)
        tests_in_page = resp.get("tests_in_page", [])
        if not tests_in_page:
            break
        for t in tests_in_page:
            test_ids.append(t["test_id"])
            if len(test_ids) >= num_tests:
                break
        page += 1

    if not test_ids:
        print(f"ERROR: No tests found on console '{console}'.", file=sys.stderr)
        sys.exit(1)

    log(f"Found {len(test_ids)} tests. Discovering simulations...")

    work_items: list[dict[str, Any]] = []
    for test_id in test_ids:
        sim_ids: list[str] = []
        page = 0
        while len(sim_ids) < sims_per_test:
            resp = sb_get_test_simulations(
                test_id, console=console, page_number=page
            )
            sims_in_page = resp.get("simulations_in_page", [])
            if not sims_in_page:
                break
            for s in sims_in_page:
                sim_ids.append(s["simulation_id"])
                if len(sim_ids) >= sims_per_test:
                    break
            page += 1

        work_items.append({"test_id": test_id, "simulation_ids": sim_ids})

    total_sims = sum(len(w["simulation_ids"]) for w in work_items)
    log(f"Workload: {len(work_items)} tests, {total_sims} simulations total")

    # Clean up discovery caches
    clear_all_caches()
    return work_items


def run_workload(
    console: str,
    work_items: list[dict[str, Any]],
    playbook_pages: int = DEFAULT_PLAYBOOK_PAGES,
) -> dict[str, Any]:
    """Execute the full API workload and measure memory.

    Calls real SafeBreach API functions. When caching is enabled,
    the server-module cache dicts accumulate real responses.
    Returns measurement dict.
    """
    gc.collect()
    tracemalloc.start()
    rss_start = get_rss_mb()
    rss_samples: list[float] = [rss_start]
    api_call_count = 0
    api_errors = 0

    # --- Simulators (Config server) ---
    log("Fetching simulators...")
    try:
        sb_get_console_simulators(console=console)
        api_call_count += 1
    except Exception as exc:
        log(f"  WARN simulators: {exc}")
        api_errors += 1
    rss_samples.append(get_rss_mb())

    # --- Playbook (Playbook server) — big singleton cache entry ---
    # NOTE: sb_get_playbook_attacks fetches the ENTIRE KB (~12K attacks) on
    # every call, then paginates locally. With caching disabled, each page
    # request triggers a full API re-fetch. We cap pages to avoid spending
    # hours on 1,200+ identical API calls while still measuring the effect.
    log(f"Fetching playbook attacks ({playbook_pages} pages)...")
    try:
        page = 0
        while page < playbook_pages:
            resp = sb_get_playbook_attacks(
                console=console, page_number=page
            )
            api_call_count += 1
            total_pages = resp.get("total_pages", 1)
            if page + 1 >= total_pages:
                break
            page += 1
    except Exception as exc:
        log(f"  WARN playbook: {exc}")
        api_errors += 1
    rss_samples.append(get_rss_mb())
    log(f"  RSS after playbook: {rss_samples[-1]:.1f} MB")

    # --- Data server: iterate tests × simulations ---
    for idx, item in enumerate(work_items):
        test_id = item["test_id"]
        sim_ids = item["simulation_ids"]
        log(f"Test {idx + 1}/{len(work_items)} ({test_id}): "
            f"{len(sim_ids)} simulations")

        # Tests history (populates tests_cache)
        try:
            sb_get_tests_history(console=console, page_number=0)
            api_call_count += 1
        except Exception as exc:
            log(f"  WARN tests_history: {exc}")
            api_errors += 1

        # Simulations list (populates simulations_cache)
        try:
            sb_get_test_simulations(test_id, console=console, page_number=0)
            api_call_count += 1
        except Exception as exc:
            log(f"  WARN simulations: {exc}")
            api_errors += 1

        # Findings (populates findings_cache)
        try:
            sb_get_test_findings_details(
                test_id, console=console, page_number=0
            )
            api_call_count += 1
        except Exception as exc:
            log(f"  WARN findings: {exc}")
            api_errors += 1

        # Per-simulation: security events + full logs
        for sim_id in sim_ids:
            try:
                sb_get_security_controls_events(
                    test_id, sim_id, console=console, page_number=0
                )
                api_call_count += 1
            except Exception as exc:
                log(f"  WARN sec_events({sim_id}): {exc}")
                api_errors += 1

            try:
                sb_get_full_simulation_logs(
                    simulation_id=sim_id,
                    test_id=test_id,
                    console=console,
                )
                api_call_count += 1
            except Exception as exc:
                log(f"  WARN full_logs({sim_id}): {exc}")
                api_errors += 1

        rss_samples.append(get_rss_mb())

    # --- Final measurements ---
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
        "rss_growth_mb": round(rss_end - rss_start, 2),
        "rss_samples_mb": [round(s, 2) for s in rss_samples],
        "cache_entry_counts": cache_counts,
        "api_call_count": api_call_count,
        "api_errors": api_errors,
    }


# ---------------------------------------------------------------------------
# Scenario runners
# ---------------------------------------------------------------------------

def run_scenario_disabled(
    console: str,
    work_items: list[dict[str, Any]],
    playbook_pages: int = DEFAULT_PLAYBOOK_PAGES,
) -> dict[str, Any]:
    """Scenario A: Caching disabled — API calls happen, nothing cached."""
    os.environ.pop("SB_MCP_CACHE_CONFIG", None)
    os.environ.pop("SB_MCP_CACHE_DATA", None)
    os.environ.pop("SB_MCP_CACHE_PLAYBOOK", None)
    os.environ.pop("SB_MCP_CACHE_STUDIO", None)
    reset_cache_config()
    clear_all_caches()
    gc.collect()

    log("--- Scenario A: Caching DISABLED ---")
    result = run_workload(console, work_items, playbook_pages=playbook_pages)

    # Verify caches stayed empty
    for name, count in result["cache_entry_counts"].items():
        if count != 0:
            log(f"  WARN: {name} has {count} entries despite caching disabled")

    return result


def run_scenario_enabled(
    console: str,
    work_items: list[dict[str, Any]],
    playbook_pages: int = DEFAULT_PLAYBOOK_PAGES,
) -> dict[str, Any]:
    """Scenario B: Caching enabled (unbounded) — real data accumulates."""
    os.environ["SB_MCP_CACHE_CONFIG"] = "true"
    os.environ["SB_MCP_CACHE_DATA"] = "true"
    os.environ["SB_MCP_CACHE_PLAYBOOK"] = "true"
    os.environ["SB_MCP_CACHE_STUDIO"] = "true"
    reset_cache_config()
    clear_all_caches()
    gc.collect()

    log("--- Scenario B: Caching ENABLED (unbounded) ---")
    return run_workload(console, work_items, playbook_pages=playbook_pages)


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def print_summary(results: dict[str, Any]) -> None:
    """Print a human-readable summary to stderr."""
    print("\n" + "=" * 72, file=sys.stderr)
    print("  MCP Cache Memory Profile Baseline (E2E — Real API Data)",
          file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print(f"  Timestamp : {results['timestamp']}", file=sys.stderr)
    print(f"  Platform  : {results['platform']}", file=sys.stderr)
    print(f"  Python    : {results['python_version']}", file=sys.stderr)
    print(f"  Console   : {results['console']}", file=sys.stderr)
    wl = results["workload"]
    print(f"  Workload  : {wl['num_tests']} tests × "
          f"{wl['sims_per_test']} sims/test "
          f"({wl['total_simulations']} total sims)", file=sys.stderr)
    print("-" * 72, file=sys.stderr)

    for key, label in [
        ("caching_disabled", "Scenario A: Caching DISABLED"),
        ("caching_enabled_buggy", "Scenario B: Caching ENABLED (unbounded)"),
    ]:
        sc = results["scenarios"][key]
        growth = sc["rss_growth_mb"]
        print(f"\n  {label}", file=sys.stderr)
        print(f"    API calls     : {sc['api_call_count']} "
              f"({sc['api_errors']} errors)", file=sys.stderr)
        print(f"    RSS start     : {sc['rss_start_mb']:.1f} MB",
              file=sys.stderr)
        print(f"    RSS end       : {sc['rss_end_mb']:.1f} MB",
              file=sys.stderr)
        print(f"    RSS peak (OS) : {sc['rss_peak_mb']:.1f} MB",
              file=sys.stderr)
        print(f"    RSS growth    : {growth:+.1f} MB", file=sys.stderr)
        print(f"    tracemalloc   : {sc['tracemalloc_peak_mb']:.1f} MB "
              f"(Python heap peak)", file=sys.stderr)
        print(f"    Cache entries : {sc['cache_entry_counts']}",
              file=sys.stderr)

    # Delta
    dis = results["scenarios"]["caching_disabled"]
    ena = results["scenarios"]["caching_enabled_buggy"]
    delta = ena["rss_end_mb"] - dis["rss_end_mb"]
    print(f"\n  {'─' * 68}", file=sys.stderr)
    print(f"  Cache memory overhead (enabled − disabled): "
          f"{delta:+.1f} MB", file=sys.stderr)
    print(f"  Cache entries total: "
          f"{sum(ena['cache_entry_counts'].values())}", file=sys.stderr)

    print("\n" + "-" * 72, file=sys.stderr)
    th = results["acceptance_thresholds"]
    print("  Acceptance Thresholds (post-fix):", file=sys.stderr)
    print(f"    Max RSS growth (disabled)       : "
          f"{th['max_rss_growth_disabled_mb']} MB", file=sys.stderr)
    print(f"    Max RSS growth (enabled, fixed)  : "
          f"{th['max_rss_growth_enabled_fixed_mb']} MB", file=sys.stderr)
    print(f"    Max cache overhead (ena - dis)    : "
          f"{th['max_cache_overhead_mb']} MB", file=sys.stderr)
    print(f"    Max peak RSS above baseline      : "
          f"{th['max_peak_rss_above_baseline_mb']} MB", file=sys.stderr)
    print("=" * 72 + "\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Memory profile baseline using real SafeBreach API data"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write JSON results to FILE (default: stdout)",
    )
    parser.add_argument(
        "--console", type=str,
        default=os.environ.get("E2E_CONSOLE", DEFAULT_CONSOLE),
        help=f"SafeBreach console name (default: $E2E_CONSOLE or "
             f"'{DEFAULT_CONSOLE}')",
    )
    parser.add_argument(
        "--num-tests", type=int, default=DEFAULT_NUM_TESTS,
        help=f"Number of tests to iterate (default: {DEFAULT_NUM_TESTS})",
    )
    parser.add_argument(
        "--sims-per-test", type=int, default=DEFAULT_SIMS_PER_TEST,
        help=f"Simulations per test (default: {DEFAULT_SIMS_PER_TEST})",
    )
    parser.add_argument(
        "--playbook-pages", type=int, default=DEFAULT_PLAYBOOK_PAGES,
        help=f"Max playbook pages to iterate (default: "
             f"{DEFAULT_PLAYBOOK_PAGES}). Each page re-fetches entire KB "
             f"when uncached.",
    )
    args = parser.parse_args()

    console = args.console
    num_tests = args.num_tests
    sims_per_test = args.sims_per_test
    playbook_pages = args.playbook_pages

    print(f"\nMCP Memory Baseline — console={console}, "
          f"tests={num_tests}, sims/test={sims_per_test}\n",
          file=sys.stderr)

    # --- Phase 1: Discover workload (test IDs + simulation IDs) ---
    work_items = discover_workload(console, num_tests, sims_per_test)
    total_sims = sum(len(w["simulation_ids"]) for w in work_items)

    # --- Phase 2: Scenario A — caching disabled ---
    print("", file=sys.stderr)
    scenario_disabled = run_scenario_disabled(
        console, work_items, playbook_pages=playbook_pages
    )

    # Clean up between scenarios
    clear_all_caches()
    gc.collect()
    time.sleep(1)  # let OS reclaim

    # --- Phase 3: Scenario B — caching enabled (unbounded) ---
    print("", file=sys.stderr)
    scenario_enabled = run_scenario_enabled(
        console, work_items, playbook_pages=playbook_pages
    )

    # Clean up
    clear_all_caches()
    for suffix in ("CONFIG", "DATA", "PLAYBOOK", "STUDIO"):
        os.environ.pop(f"SB_MCP_CACHE_{suffix}", None)
    reset_cache_config()
    gc.collect()

    # --- Build results ---
    results: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.system().lower(),
        "python_version": platform.python_version(),
        "console": console,
        "workload": {
            "num_tests": len(work_items),
            "sims_per_test": sims_per_test,
            "playbook_pages": playbook_pages,
            "total_simulations": total_sims,
            "expected_cache_keys": {
                "simulators": 1,
                "tests": 1,
                "simulations": len(work_items),
                "security_control_events": total_sims,
                "findings": len(work_items),
                "full_simulation_logs": total_sims,
                "playbook": 1,
                "studio_drafts": 0,
            },
        },
        "scenarios": {
            "caching_disabled": scenario_disabled,
            "caching_enabled_buggy": scenario_enabled,
        },
        "acceptance_thresholds": {
            "max_rss_growth_disabled_mb": 350,
            "max_rss_growth_enabled_fixed_mb": 400,
            "max_cache_overhead_mb": 50,
            "max_peak_rss_above_baseline_mb": 1200,
        },
    }

    # --- Output ---
    json_output = json.dumps(results, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_output)
            f.write("\n")
        print(f"\nResults written to: {args.output}", file=sys.stderr)
    else:
        print(json_output)

    print_summary(results)


if __name__ == "__main__":
    main()
