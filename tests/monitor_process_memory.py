#!/usr/bin/env python3
"""Lightweight standalone script that monitors a process's memory usage from the outside.

Usage examples:
    # Monitor an existing process by PID for 30 seconds
    uv run python tests/monitor_process_memory.py --pid 12345 --duration 30

    # Start a subprocess and monitor it
    uv run python tests/monitor_process_memory.py --command "python my_server.py" --duration 120

    # Write CSV output to a file with custom polling interval
    uv run python tests/monitor_process_memory.py --pid 12345 --interval 0.5 --output memory.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TextIO

import psutil


BYTES_PER_MB = 1024 * 1024


@dataclass
class Sample:
    """A single memory/CPU measurement."""

    timestamp: str
    elapsed_seconds: float
    rss_mb: float
    vms_mb: float
    cpu_percent: float


@dataclass
class MonitorResult:
    """Accumulated monitoring results."""

    samples: list[Sample] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    error: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Monitor a process's memory usage over time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s --pid 12345 --duration 30\n"
            '  %(prog)s --command "python my_server.py" --duration 120\n'
            "  %(prog)s --pid 12345 --interval 0.5 --output memory.csv\n"
        ),
    )

    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--pid",
        type=int,
        help="Monitor an existing process by PID",
    )
    target_group.add_argument(
        "--command",
        type=str,
        help='Start a subprocess and monitor it (e.g., "python my_server.py")',
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="How long to monitor in seconds (default: 60)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write CSV output to file (default: stdout)",
    )

    return parser.parse_args(argv)


def collect_sample(proc: psutil.Process, elapsed: float) -> Sample:
    """Collect a single memory and CPU sample from the process."""
    mem = proc.memory_info()
    cpu = proc.cpu_percent(interval=None)
    now = datetime.now(timezone.utc).isoformat()

    return Sample(
        timestamp=now,
        elapsed_seconds=elapsed,
        rss_mb=mem.rss / BYTES_PER_MB,
        vms_mb=mem.vms / BYTES_PER_MB,
        cpu_percent=cpu,
    )


def linear_regression_slope(x_values: list[float], y_values: list[float]) -> float:
    """Compute the slope of a simple least-squares linear regression.

    slope = (n * sum(x*y) - sum(x) * sum(y)) / (n * sum(x^2) - sum(x)^2)

    Returns the slope, or 0.0 if computation is not possible (e.g., fewer
    than 2 data points or zero variance in x).
    """
    n = len(x_values)
    if n < 2:
        return 0.0

    sum_x = sum(x_values)
    sum_y = sum(y_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values))
    sum_x2 = sum(x * x for x in x_values)

    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0.0:
        return 0.0

    return (n * sum_xy - sum_x * sum_y) / denominator


def percentile(sorted_values: list[float], p: float) -> float:
    """Compute the p-th percentile from a sorted list of values.

    Uses linear interpolation between adjacent ranks.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (p / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = lower + 1
    fraction = rank - lower

    if upper >= len(sorted_values):
        return sorted_values[-1]

    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def monitor_process(
    proc: psutil.Process,
    duration: float,
    interval: float,
    csv_writer: Any,
) -> MonitorResult:
    """Poll the target process at the given interval and write CSV rows.

    Returns a MonitorResult with all collected samples.
    """
    result = MonitorResult(start_time=time.monotonic())

    # Prime cpu_percent so the first real reading is meaningful.
    try:
        proc.cpu_percent(interval=None)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    deadline = result.start_time + duration

    try:
        while time.monotonic() < deadline:
            loop_start = time.monotonic()
            elapsed = loop_start - result.start_time

            try:
                sample = collect_sample(proc, elapsed)
            except psutil.NoSuchProcess:
                print(
                    f"Process (PID {proc.pid}) exited after {elapsed:.1f}s. "
                    f"Collected {len(result.samples)} samples.",
                    file=sys.stderr,
                )
                break
            except psutil.AccessDenied:
                print(
                    f"Permission denied reading process (PID {proc.pid}) after {elapsed:.1f}s.",
                    file=sys.stderr,
                )
                result.error = "permission_denied"
                break

            result.samples.append(sample)
            csv_writer.writerow([
                sample.timestamp,
                f"{sample.rss_mb:.2f}",
                f"{sample.vms_mb:.2f}",
                f"{sample.cpu_percent:.1f}",
            ])

            # Sleep for the remainder of the interval, accounting for collection time.
            sleep_time = interval - (time.monotonic() - loop_start)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        elapsed = time.monotonic() - result.start_time
        print(
            f"\nInterrupted after {elapsed:.1f}s. Collected {len(result.samples)} samples.",
            file=sys.stderr,
        )

    result.end_time = time.monotonic()
    return result


def print_summary(result: MonitorResult) -> None:
    """Print a human-readable summary of the monitoring results to stderr."""
    samples = result.samples
    if not samples:
        print("\n=== Memory Monitor Summary ===", file=sys.stderr)
        print("No samples collected.", file=sys.stderr)
        return

    duration = result.end_time - result.start_time
    rss_values = [s.rss_mb for s in samples]
    vms_values = [s.vms_mb for s in samples]

    sorted_rss = sorted(rss_values)
    sorted_vms = sorted(vms_values)

    rss_mean = sum(rss_values) / len(rss_values)
    vms_mean = sum(vms_values) / len(vms_values)

    rss_p95 = percentile(sorted_rss, 95)
    vms_p95 = percentile(sorted_vms, 95)

    # Find peak RSS and its timestamp.
    peak_idx = rss_values.index(max(rss_values))
    peak_rss = rss_values[peak_idx]
    peak_timestamp = samples[peak_idx].timestamp

    # Growth rate: linear regression slope of RSS over elapsed time, converted to MB/minute.
    elapsed_minutes = [s.elapsed_seconds / 60.0 for s in samples]
    slope_mb_per_minute = linear_regression_slope(elapsed_minutes, rss_values)

    print("\n=== Memory Monitor Summary ===", file=sys.stderr)
    print(f"Duration: {duration:.1f}s", file=sys.stderr)
    print(f"Samples: {len(samples)}", file=sys.stderr)
    print(
        f"RSS (MB): min={min(rss_values):.2f}, max={max(rss_values):.2f}, "
        f"mean={rss_mean:.2f}, p95={rss_p95:.2f}",
        file=sys.stderr,
    )
    print(
        f"VMS (MB): min={min(vms_values):.2f}, max={max(vms_values):.2f}, "
        f"mean={vms_mean:.2f}, p95={vms_p95:.2f}",
        file=sys.stderr,
    )
    print(f"Growth rate: {slope_mb_per_minute:.4f} MB/minute", file=sys.stderr)
    print(f"Peak RSS: {peak_rss:.2f} MB at {peak_timestamp}", file=sys.stderr)


def open_output(path: str | None) -> tuple[TextIO, bool]:
    """Open the output destination.

    Returns a tuple of (file_handle, should_close).
    When writing to stdout, should_close is False.
    """
    if path is None:
        return sys.stdout, False
    try:
        return open(path, "w", newline=""), True  # noqa: SIM115
    except OSError as exc:
        print(f"Error: Cannot open output file '{path}': {exc}", file=sys.stderr)
        sys.exit(1)


def get_process(pid: int) -> psutil.Process:
    """Get a psutil.Process for the given PID, with validation."""
    try:
        proc = psutil.Process(pid)
        # Verify the process exists and is accessible.
        proc.status()
        return proc
    except psutil.NoSuchProcess:
        print(f"Error: No process found with PID {pid}.", file=sys.stderr)
        sys.exit(1)
    except psutil.AccessDenied:
        print(
            f"Error: Permission denied accessing process with PID {pid}. "
            f"Try running with elevated privileges.",
            file=sys.stderr,
        )
        sys.exit(1)


def start_subprocess(command: str) -> tuple[psutil.Process, subprocess.Popen[bytes]]:
    """Start a subprocess from a command string and return its psutil.Process handle."""
    try:
        args = shlex.split(command)
    except ValueError as exc:
        print(f"Error: Invalid command string: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        child = subprocess.Popen(args)  # noqa: S603
    except FileNotFoundError:
        print(f"Error: Command not found: {args[0]}", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"Error: Permission denied executing: {args[0]}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"Error: Failed to start subprocess: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Started subprocess (PID {child.pid}): {command}", file=sys.stderr)

    try:
        proc = psutil.Process(child.pid)
    except psutil.NoSuchProcess:
        print(
            f"Error: Subprocess (PID {child.pid}) exited immediately.",
            file=sys.stderr,
        )
        sys.exit(1)

    return proc, child


def main(argv: list[str] | None = None) -> int:
    """Entry point for the memory monitor script.

    Returns 0 on success, 1 on error.
    """
    args = parse_args(argv)

    child_popen: subprocess.Popen[bytes] | None = None

    if args.pid is not None:
        proc = get_process(args.pid)
        print(f"Monitoring PID {args.pid} for {args.duration}s (interval={args.interval}s)", file=sys.stderr)
    else:
        proc, child_popen = start_subprocess(args.command)
        print(f"Monitoring for {args.duration}s (interval={args.interval}s)", file=sys.stderr)

    output_handle, should_close = open_output(args.output)

    try:
        # Use a StringIO buffer if writing to a file so we can flush atomically,
        # but for stdout write directly for real-time visibility.
        buffer: io.StringIO | None = None
        if should_close:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
        else:
            writer = csv.writer(output_handle)

        # Write CSV header.
        writer.writerow(["timestamp", "rss_mb", "vms_mb", "cpu_percent"])

        if not should_close:
            output_handle.flush()

        result = monitor_process(proc, args.duration, args.interval, writer)

        # Write buffered output to file.
        if buffer is not None:
            output_handle.write(buffer.getvalue())

        print_summary(result)

        if result.error == "permission_denied":
            return 1

        return 0

    finally:
        if should_close:
            output_handle.close()

        # Clean up child subprocess if we started one.
        if child_popen is not None:
            if child_popen.poll() is None:
                print(f"Terminating subprocess (PID {child_popen.pid})...", file=sys.stderr)
                child_popen.terminate()
                try:
                    child_popen.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"Killing subprocess (PID {child_popen.pid})...", file=sys.stderr)
                    child_popen.kill()
                    child_popen.wait()


if __name__ == "__main__":
    sys.exit(main())
