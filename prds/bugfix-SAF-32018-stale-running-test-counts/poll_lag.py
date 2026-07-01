"""
SAF-32018 live-divergence capture.

Polls a RUNNING test, comparing:
  - aggregate total: sum of get_test_details.simulations_statistics (testsummaries.finalStatus)
  - live total:      get_test_simulations total_simulations (executionsHistoryResults)
Records a timeseries and flags any sample where the two diverge.
"""
import time
import logging

logging.disable(logging.INFO)
logging.getLogger().setLevel(logging.ERROR)

from safebreach_mcp_data.data_functions import sb_get_test_details, sb_get_test_simulations

CONSOLE = "pentest01"
TID = "1782107855457.2"
SAMPLES = 60
INTERVAL = 5  # seconds


def agg_total_and_missed(d):
    total = 0
    missed = 0
    for s in d.get("simulations_statistics", []):
        if "count" in s and "status" in s:
            total += s["count"] or 0
            if s["status"] == "missed":
                missed = s["count"] or 0
    return total, missed


max_div = 0
saw = False
print(f"{'t(s)':>5} {'status':>9} {'agg_tot':>8} {'live_tot':>8} {'agg_mis':>8} {'live_mis':>8}  note")
start = None
for i in range(SAMPLES):
    try:
        d = sb_get_test_details(TID, CONSOLE)
        status = d.get("status")
        a_tot, a_mis = agg_total_and_missed(d)
        live = sb_get_test_simulations(TID, CONSOLE, page_number=0)
        l_tot = live.get("total_simulations") or 0
        lm = sb_get_test_simulations(TID, CONSOLE, page_number=0, status_filter="missed")
        l_mis = lm.get("total_simulations") or 0
        div = abs(l_tot - a_tot)
        note = ""
        if div > 0:
            note = f"DIVERGENCE total {l_tot - a_tot:+d}"
            saw = True
            max_div = max(max_div, div)
        if l_mis != a_mis:
            note += f" | missed {l_mis - a_mis:+d}"
            saw = True
        print(f"{i*INTERVAL:>5} {str(status):>9} {a_tot:>8} {l_tot:>8} {a_mis:>8} {l_mis:>8}  {note}")
        if status and status.upper() in ("COMPLETED", "CANCELED", "FAILED"):
            print(f"\nTest reached terminal status {status}; stopping.")
            break
    except Exception as e:
        print(f"{i*INTERVAL:>5}  ERROR: {type(e).__name__}: {e}")
    time.sleep(INTERVAL)

print("\n=== VERDICT ===")
if saw:
    print(f"CONFIRMED: aggregate (finalStatus) lagged live (executionsHistoryResults). "
          f"Max total divergence observed = {max_div}.")
else:
    print("No divergence captured in this window (aggregate stayed in sync). "
          "Try a longer/denser window or a larger test.")
