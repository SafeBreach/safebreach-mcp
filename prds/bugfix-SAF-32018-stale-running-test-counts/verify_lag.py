"""
SAF-32018 empirical verification.

Hypothesis: for a RUNNING test, testsummaries.finalStatus (the aggregate that feeds
get_test_details.simulations_statistics) lags the live per-simulation results that
executionsHistoryResults (what get_test_simulations counts) returns.

Strategy:
  1. List tests on pentest01, find non-terminal (running/paused) ones.
  2. For each candidate, read the aggregate 'missed' count (finalStatus via get_test_details)
     and the live 'missed' count (counted from executionsHistoryResults via get_test_simulations).
  3. Compare. A mismatch on a running test confirms the lag.
  4. Also sanity-check a recent COMPLETED test: the two should agree (validates the method).
"""
import sys

CONSOLE = "pentest01"

from safebreach_mcp_data.data_functions import (
    sb_get_tests,
    sb_get_test_details,
    sb_get_test_simulations,
)


def missed_from_details(test_id):
    d = sb_get_test_details(test_id, CONSOLE)
    for s in d.get("simulations_statistics", []):
        if s.get("status") == "missed":
            return s.get("count"), d.get("status")
    return None, d.get("status")


def missed_live(test_id):
    r = sb_get_test_simulations(test_id, CONSOLE, page_number=0, status_filter="missed")
    return r.get("total_simulations")


def report(label, test_id):
    agg, status = missed_from_details(test_id)
    live = missed_live(test_id)
    flag = "  <-- MISMATCH" if (agg is not None and live is not None and agg != live) else ""
    print(f"[{label}] test={test_id} status={status} aggregate_missed={agg} live_missed={live}{flag}")
    return status, agg, live


def main():
    # Find running tests
    running = sb_get_tests(CONSOLE, status_filter="running")
    run_tests = running.get("tests_in_page", [])
    print(f"Running tests found: {len(run_tests)}")
    saw_mismatch = False
    for t in run_tests[:5]:
        status, agg, live = report("RUNNING", t["test_id"])
        if agg is not None and live is not None and agg != live:
            saw_mismatch = True

    # Sanity check: a recent completed test (counts should agree)
    completed = sb_get_tests(CONSOLE, status_filter="completed", order_by="end_time", order_direction="desc")
    comp_tests = completed.get("tests_in_page", [])
    print(f"\nCompleted tests sampled for sanity check: {min(3, len(comp_tests))}")
    for t in comp_tests[:3]:
        report("COMPLETED", t["test_id"])

    print("\n=== VERDICT ===")
    if not run_tests:
        print("No RUNNING test available right now — cannot observe live lag this moment.")
        print("Completed-test rows above validate that aggregate==live once finalStatus reconciles.")
    elif saw_mismatch:
        print("CONFIRMED: aggregate (finalStatus) lags live (executionsHistoryResults) on a RUNNING test.")
    else:
        print("No mismatch observed on the running test(s) at this instant (aggregate may be momentarily in sync).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        raise
