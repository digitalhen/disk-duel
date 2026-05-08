#!/usr/bin/env python3
"""
Disk Duel -- Comprehensive Drive Benchmark & Comparison Tool

Runs a full suite of I/O benchmarks on one or two drives using fio,
and generates an HTML report. In dual mode, every test is scored with
a winner and the report includes comparison charts. In solo mode,
the report is a single-drive scorecard.

Requirements:
    brew install fio
    pip3 install matplotlib numpy   # only needed for dual-mode charts

Usage (dual / comparison):
    python3 disk_duel.py /path/to/drive_a /path/to/drive_b
    python3 disk_duel.py /Volumes/Internal /Volumes/External --labels "Internal SSD" "TB5 Enclosure"
    python3 disk_duel.py /tmp/a /tmp/b --quick

Usage (solo / single drive):
    python3 disk_duel.py /Volumes/MyDrive
    python3 disk_duel.py /Volumes/MyDrive --labels "Crucial T705" --quick
"""

import argparse
import json
import subprocess
import os
import sys
import shutil
import time
import base64
import io
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Terminal colors
# ---------------------------------------------------------------------------
class C:
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    RESET  = "\033[0m"
    MAG    = "\033[95m"

def banner():
    print(f"""
{C.BOLD}{C.CYAN}  ┌──────────────────────────────────────────────────┐
  │                                                  │
  │   ____  _     _      ____             _          │
  │  |  _ \\(_)___| | __ |  _ \\ _   _  ___| |         │
  │  | | | | / __| |/ / | | | | | | |/ _ \\ |         │
  │  | |_| | \\__ \\   <  | |_| | |_| |  __/ |         │
  │  |____/|_|___/_|\\_\\ |____/ \\__,_|\\___|_|         │
  │                                                  │
  │  Comprehensive Drive Benchmark & Comparison      │
  │                                                  │
  └──────────────────────────────────────────────────┘{C.RESET}
""")

# ---------------------------------------------------------------------------
# Test suite definitions
# ---------------------------------------------------------------------------
def get_test_suite(quick: bool = False, size_mult: float = 1.0):
    """Return the full benchmark test suite."""

    def sz(base_mb: int) -> str:
        val = max(16, int(base_mb * size_mult))
        if val >= 1024:
            return f"{val // 1024}G"
        return f"{val}M"

    runtime = "10s" if not quick else "5s"
    runtime_long = "30s" if not quick else "10s"

    tests = [
        # --- Sequential throughput ---
        {
            "name": "Sequential Read 1M",
            "category": "sequential",
            "rw": "read", "bs": "1M", "iodepth": 1, "numjobs": 1,
            "size": sz(2048), "runtime": runtime,
            "metric": "bw_mb", "unit": "MB/s",
        },
        {
            "name": "Sequential Write 1M",
            "category": "sequential",
            "rw": "write", "bs": "1M", "iodepth": 1, "numjobs": 1,
            "size": sz(2048), "runtime": runtime,
            "metric": "bw_mb", "unit": "MB/s",
        },
        {
            "name": "Sequential Read 128K",
            "category": "sequential",
            "rw": "read", "bs": "128k", "iodepth": 1, "numjobs": 1,
            "size": sz(1024), "runtime": runtime,
            "metric": "bw_mb", "unit": "MB/s",
        },
        {
            "name": "Sequential Write 128K",
            "category": "sequential",
            "rw": "write", "bs": "128k", "iodepth": 1, "numjobs": 1,
            "size": sz(1024), "runtime": runtime,
            "metric": "bw_mb", "unit": "MB/s",
        },

        # --- Random 4K at various queue depths ---
        {
            "name": "Random Read 4K QD1",
            "category": "random_4k",
            "rw": "randread", "bs": "4k", "iodepth": 1, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },
        {
            "name": "Random Read 4K QD4",
            "category": "random_4k",
            "rw": "randread", "bs": "4k", "iodepth": 4, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },
        {
            "name": "Random Read 4K QD16",
            "category": "random_4k",
            "rw": "randread", "bs": "4k", "iodepth": 16, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },
        {
            "name": "Random Read 4K QD32",
            "category": "random_4k",
            "rw": "randread", "bs": "4k", "iodepth": 32, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },
        {
            "name": "Random Write 4K QD1",
            "category": "random_4k",
            "rw": "randwrite", "bs": "4k", "iodepth": 1, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },
        {
            "name": "Random Write 4K QD4",
            "category": "random_4k",
            "rw": "randwrite", "bs": "4k", "iodepth": 4, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },
        {
            "name": "Random Write 4K QD16",
            "category": "random_4k",
            "rw": "randwrite", "bs": "4k", "iodepth": 16, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },
        {
            "name": "Random Write 4K QD32",
            "category": "random_4k",
            "rw": "randwrite", "bs": "4k", "iodepth": 32, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "metric": "iops", "unit": "IOPS",
        },

        # --- Mixed workloads ---
        {
            "name": "Mixed R/W 70/30 4K QD16",
            "category": "mixed",
            "rw": "randrw", "bs": "4k", "iodepth": 16, "numjobs": 1,
            "size": sz(512), "runtime": runtime,
            "rwmixread": 70,
            "metric": "iops_total", "unit": "IOPS",
        },
        {
            "name": "Mixed R/W 70/30 64K QD16",
            "category": "mixed",
            "rw": "randrw", "bs": "64k", "iodepth": 16, "numjobs": 1,
            "size": sz(1024), "runtime": runtime,
            "rwmixread": 70,
            "metric": "bw_mb_total", "unit": "MB/s",
        },

        # --- Large block random (app launch, VM, container) ---
        {
            "name": "Random Read 64K QD16",
            "category": "large_random",
            "rw": "randread", "bs": "64k", "iodepth": 16, "numjobs": 1,
            "size": sz(1024), "runtime": runtime,
            "metric": "bw_mb", "unit": "MB/s",
        },
        {
            "name": "Random Write 64K QD16",
            "category": "large_random",
            "rw": "randwrite", "bs": "64k", "iodepth": 16, "numjobs": 1,
            "size": sz(1024), "runtime": runtime,
            "metric": "bw_mb", "unit": "MB/s",
        },

        # --- Sustained sequential write (SLC cache exhaustion) ---
        {
            "name": "Sustained Sequential Write",
            "category": "sustained",
            "rw": "write", "bs": "1M", "iodepth": 4, "numjobs": 1,
            "size": sz(4096), "runtime": runtime_long,
            "metric": "bw_mb", "unit": "MB/s",
        },

        # --- Latency-sensitive (QD1 4K -- simulates OS/swap) ---
        {
            "name": "Latency: 4K Read QD1",
            "category": "latency",
            "rw": "randread", "bs": "4k", "iodepth": 1, "numjobs": 1,
            "size": sz(256), "runtime": runtime,
            "metric": "lat_us_p99", "unit": "us (p99)",
        },
        {
            "name": "Latency: 4K Write QD1",
            "category": "latency",
            "rw": "randwrite", "bs": "4k", "iodepth": 1, "numjobs": 1,
            "size": sz(256), "runtime": runtime,
            "metric": "lat_us_p99", "unit": "us (p99)",
        },
    ]
    return tests


# ---------------------------------------------------------------------------
# fio runner
# ---------------------------------------------------------------------------
def check_fio():
    """Check if fio is installed."""
    if shutil.which("fio") is None:
        print(f"{C.RED}{C.BOLD}Error: fio is not installed.{C.RESET}")
        print(f"{C.YELLOW}Install it with:{C.RESET}")
        print(f"  macOS:  brew install fio")
        print(f"  Linux:  sudo apt-get install fio")
        sys.exit(1)
    # Print version
    ver = subprocess.check_output(["fio", "--version"], text=True).strip()
    print(f"  {C.DIM}fio version: {ver}{C.RESET}")


def run_fio_test(test: dict, directory: str, label: str) -> dict:
    """Run a single fio benchmark and return parsed results."""

    test_file = os.path.join(directory, ".disk_duel_testfile")
    is_macos = sys.platform == "darwin"

    cmd = [
        "fio",
        f"--name={test['name'].replace(' ', '_')}",
        f"--directory={directory}",
        f"--filename=.disk_duel_testfile",
        f"--rw={test['rw']}",
        f"--bs={test['bs']}",
        f"--iodepth={test['iodepth']}",
        f"--numjobs={test['numjobs']}",
        f"--size={test['size']}",
        f"--runtime={test['runtime']}",
        "--time_based",
        "--group_reporting",
        "--output-format=json",
        "--norandommap",
        "--direct=1",
        "--end_fsync=1",
    ]

    # macOS: psync (default) ignores iodepth > 1. Use posixaio for async I/O.
    if is_macos and test["iodepth"] > 1:
        cmd.append("--ioengine=posixaio")

    if "rwmixread" in test:
        cmd.append(f"--rwmixread={test['rwmixread']}")

    def _run_and_cleanup(cmd_list):
        res = subprocess.run(cmd_list, capture_output=True, text=True, timeout=300)
        try:
            os.remove(test_file)
        except OSError:
            pass
        return res

    try:
        result = _run_and_cleanup(cmd)

        if result.returncode != 0:
            # Some macOS/filesystem combos don't support direct=1, retry without
            if "--direct=1" in cmd and ("Invalid argument" in result.stderr
                                        or "direct" in result.stderr.lower()):
                cmd = [c for c in cmd if c != "--direct=1"]
                result = _run_and_cleanup(cmd)

            if result.returncode != 0:
                print(f"    {C.RED}fio error: {result.stderr[:300]}{C.RESET}")
                return {"error": True}

        # Parse JSON -- fio sometimes prefixes warnings before JSON output
        stdout = result.stdout.strip()
        json_start = stdout.find("{")
        if json_start == -1:
            print(f"    {C.RED}No JSON in fio output.{C.RESET}")
            if result.stderr.strip():
                print(f"    {C.RED}stderr: {result.stderr[:300]}{C.RESET}")
            if stdout:
                print(f"    {C.RED}stdout: {stdout[:300]}{C.RESET}")
            return {"error": True}

        data = json.loads(stdout[json_start:])
        job = data["jobs"][0]

        # Extract metrics
        rw = test["rw"]
        is_read = rw in ("read", "randread")
        is_write = rw in ("write", "randwrite")
        is_mixed = rw == "randrw"

        parsed = {
            "test_name": test["name"],
            "category": test["category"],
            "label": label,
        }

        # fio reports percentiles under clat_ns by default; lat_ns only has
        # them when --lat_percentiles=1 is passed. Read clat_ns first.
        def _percentiles(side: dict) -> dict:
            return (side.get("clat_ns", {}).get("percentile")
                    or side.get("lat_ns", {}).get("percentile")
                    or {})

        if is_read or is_mixed:
            r = job["read"]
            parsed["read_bw_kb"] = r["bw"]
            parsed["read_bw_mb"] = r["bw"] / 1024.0
            parsed["read_iops"] = r["iops"]
            parsed["read_lat_ns_mean"] = r["lat_ns"]["mean"]
            parsed["read_lat_us_mean"] = r["lat_ns"]["mean"] / 1000.0
            pct = _percentiles(r)
            parsed["read_lat_ns_p50"] = pct.get("50.000000", 0)
            parsed["read_lat_ns_p99"] = pct.get("99.000000", 0)
            parsed["read_lat_ns_p999"] = pct.get("99.900000", 0)
            parsed["read_lat_us_p50"] = parsed["read_lat_ns_p50"] / 1000.0
            parsed["read_lat_us_p99"] = parsed["read_lat_ns_p99"] / 1000.0
            parsed["read_lat_us_p999"] = parsed["read_lat_ns_p999"] / 1000.0

        if is_write or is_mixed:
            w = job["write"]
            parsed["write_bw_kb"] = w["bw"]
            parsed["write_bw_mb"] = w["bw"] / 1024.0
            parsed["write_iops"] = w["iops"]
            parsed["write_lat_ns_mean"] = w["lat_ns"]["mean"]
            parsed["write_lat_us_mean"] = w["lat_ns"]["mean"] / 1000.0
            pct = _percentiles(w)
            parsed["write_lat_ns_p50"] = pct.get("50.000000", 0)
            parsed["write_lat_ns_p99"] = pct.get("99.000000", 0)
            parsed["write_lat_ns_p999"] = pct.get("99.900000", 0)
            parsed["write_lat_us_p50"] = parsed["write_lat_ns_p50"] / 1000.0
            parsed["write_lat_us_p99"] = parsed["write_lat_ns_p99"] / 1000.0
            parsed["write_lat_us_p999"] = parsed["write_lat_ns_p999"] / 1000.0

        # Compute the primary metric for this test
        metric = test["metric"]
        if metric == "bw_mb":
            if is_read:
                parsed["primary_value"] = parsed["read_bw_mb"]
            else:
                parsed["primary_value"] = parsed["write_bw_mb"]
        elif metric == "iops":
            if is_read:
                parsed["primary_value"] = parsed["read_iops"]
            else:
                parsed["primary_value"] = parsed["write_iops"]
        elif metric == "iops_total":
            parsed["primary_value"] = parsed.get("read_iops", 0) + parsed.get("write_iops", 0)
        elif metric == "bw_mb_total":
            parsed["primary_value"] = parsed.get("read_bw_mb", 0) + parsed.get("write_bw_mb", 0)
        elif metric == "lat_us_p99":
            if is_read or "read_lat_us_p99" in parsed:
                parsed["primary_value"] = parsed.get("read_lat_us_p99", 0)
            else:
                parsed["primary_value"] = parsed.get("write_lat_us_p99", 0)
        else:
            parsed["primary_value"] = 0

        parsed["primary_unit"] = test["unit"]

        return parsed

    except subprocess.TimeoutExpired:
        print(f"    {C.RED}Test timed out{C.RESET}")
        try:
            os.remove(test_file)
        except OSError:
            pass
        return {"error": True}
    except json.JSONDecodeError as e:
        print(f"    {C.RED}JSON parse error: {e}{C.RESET}")
        return {"error": True}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
TIE_THRESHOLD = 0.02  # 2% margin = tie

def score_test(val_a: float, val_b: float, is_latency: bool = False) -> dict:
    """Score a single test. Lower is better for latency, higher for everything else."""
    if val_a == 0 and val_b == 0:
        return {"winner": "tie", "pct_diff": 0, "a": val_a, "b": val_b}

    if is_latency:
        # Lower is better
        if val_b == 0:
            pct_diff = 100.0
            winner = "B"
        elif val_a == 0:
            pct_diff = 100.0
            winner = "A"
        else:
            pct_diff = (val_b - val_a) / val_b * 100.0
            if abs(pct_diff) < TIE_THRESHOLD * 100:
                winner = "tie"
            elif val_a < val_b:
                winner = "A"
            else:
                winner = "B"
                pct_diff = (val_a - val_b) / val_a * 100.0
    else:
        # Higher is better
        max_val = max(val_a, val_b)
        if max_val == 0:
            pct_diff = 0
            winner = "tie"
        else:
            pct_diff = abs(val_a - val_b) / max_val * 100.0
            if pct_diff < TIE_THRESHOLD * 100:
                winner = "tie"
            elif val_a > val_b:
                winner = "A"
            else:
                winner = "B"

    return {"winner": winner, "pct_diff": round(pct_diff, 1), "a": val_a, "b": val_b}


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------
def setup_matplotlib():
    """Configure matplotlib for clean output."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({
        "figure.facecolor": "#0d1117",
        "axes.facecolor": "#161b22",
        "axes.edgecolor": "#30363d",
        "axes.labelcolor": "#c9d1d9",
        "text.color": "#c9d1d9",
        "xtick.color": "#8b949e",
        "ytick.color": "#8b949e",
        "grid.color": "#21262d",
        "grid.alpha": 0.8,
        "font.family": "sans-serif",
        "font.size": 11,
        "figure.dpi": 150,
    })
    return plt, np


def fig_to_base64(fig) -> str:
    """Convert matplotlib figure to base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def chart_sequential(results: list, labels: tuple) -> str:
    """Bar chart comparing sequential throughput."""
    plt, np = setup_matplotlib()

    seq_tests = [r for r in results if r.get("category") == "sequential" and "score" in r]
    if not seq_tests:
        return ""

    test_names = list(dict.fromkeys(r["test_name"] for r in seq_tests))
    a_vals = []
    b_vals = []
    for name in test_names:
        matches = [r for r in seq_tests if r["test_name"] == name]
        a_match = [r for r in matches if r["label"] == labels[0]]
        b_match = [r for r in matches if r["label"] == labels[1]]
        a_vals.append(a_match[0]["primary_value"] if a_match else 0)
        b_vals.append(b_match[0]["primary_value"] if b_match else 0)

    x = np.arange(len(test_names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 5))
    bars_a = ax.bar(x - width/2, a_vals, width, label=labels[0], color="#58a6ff", edgecolor="#58a6ff", alpha=0.85)
    bars_b = ax.bar(x + width/2, b_vals, width, label=labels[1], color="#f78166", edgecolor="#f78166", alpha=0.85)

    ax.set_ylabel("MB/s", fontweight="bold")
    ax.set_title("Sequential Throughput", fontweight="bold", fontsize=14, pad=15)
    ax.set_xticks(x)
    short_names = [n.replace("Sequential ", "") for n in test_names]
    ax.set_xticklabels(short_names, rotation=15, ha="right")
    ax.legend(loc="upper right", framealpha=0.3)
    ax.grid(axis="y", linestyle="--")
    ax.set_axisbelow(True)

    for bar_group in [bars_a, bars_b]:
        for bar in bar_group:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width()/2., h + max(a_vals + b_vals)*0.01,
                        f"{h:,.0f}", ha="center", va="bottom", fontsize=8, color="#c9d1d9")

    b64 = fig_to_base64(fig)
    plt.close(fig)
    return b64


def chart_qd_scaling(results: list, labels: tuple) -> str:
    """Line chart showing IOPS scaling across queue depths for random 4K."""
    plt, np = setup_matplotlib()

    qd_tests = [r for r in results if r.get("category") == "random_4k" and "score" in r]
    if not qd_tests:
        return ""

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for idx, rw_label in enumerate(["Read", "Write"]):
        ax = axes[idx]
        rw_filter = rw_label.lower()

        for drive_idx, label in enumerate(labels):
            matching = [r for r in qd_tests
                        if r["label"] == label and rw_filter in r["test_name"].lower()]
            # Sort by queue depth
            qds = []
            iops_vals = []
            for m in matching:
                for qd in [1, 4, 16, 32]:
                    if f"QD{qd}" in m["test_name"]:
                        qds.append(qd)
                        iops_vals.append(m["primary_value"])

            color = "#58a6ff" if drive_idx == 0 else "#f78166"
            marker = "o" if drive_idx == 0 else "s"
            ax.plot(qds, iops_vals, color=color, marker=marker, linewidth=2,
                    markersize=7, label=label, alpha=0.9)
            for q, v in zip(qds, iops_vals):
                ax.annotate(f"{v:,.0f}", (q, v), textcoords="offset points",
                            xytext=(0, 10), ha="center", fontsize=7, color=color)

        ax.set_xlabel("Queue Depth", fontweight="bold")
        ax.set_ylabel("IOPS", fontweight="bold")
        ax.set_title(f"Random 4K {rw_label} -- QD Scaling", fontweight="bold", fontsize=12, pad=10)
        ax.set_xticks([1, 4, 16, 32])
        ax.legend(loc="upper left", framealpha=0.3)
        ax.grid(True, linestyle="--")
        ax.set_axisbelow(True)

    fig.suptitle("Queue Depth Scaling", fontweight="bold", fontsize=14, y=1.02)
    fig.tight_layout()
    b64 = fig_to_base64(fig)
    plt.close(fig)
    return b64


def chart_latency(results: list, labels: tuple) -> str:
    """Bar chart for latency comparison."""
    plt, np = setup_matplotlib()

    lat_tests = [r for r in results if r.get("category") == "latency" and "score" in r]
    if not lat_tests:
        return ""

    test_names = list(dict.fromkeys(r["test_name"] for r in lat_tests))
    a_vals = []
    b_vals = []
    for name in test_names:
        matches = [r for r in lat_tests if r["test_name"] == name]
        a_match = [r for r in matches if r["label"] == labels[0]]
        b_match = [r for r in matches if r["label"] == labels[1]]
        a_vals.append(a_match[0]["primary_value"] if a_match else 0)
        b_vals.append(b_match[0]["primary_value"] if b_match else 0)

    x = np.arange(len(test_names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width/2, a_vals, width, label=labels[0], color="#58a6ff", alpha=0.85)
    ax.bar(x + width/2, b_vals, width, label=labels[1], color="#f78166", alpha=0.85)

    ax.set_ylabel("Microseconds (p99) -- lower is better", fontweight="bold")
    ax.set_title("Latency (p99)", fontweight="bold", fontsize=14, pad=15)
    ax.set_xticks(x)
    short_names = [n.replace("Latency: ", "") for n in test_names]
    ax.set_xticklabels(short_names)
    ax.legend(loc="upper right", framealpha=0.3)
    ax.grid(axis="y", linestyle="--")
    ax.set_axisbelow(True)

    b64 = fig_to_base64(fig)
    plt.close(fig)
    return b64


def chart_mixed(results: list, labels: tuple) -> str:
    """Bar chart for mixed workload results."""
    plt, np = setup_matplotlib()

    mixed_tests = [r for r in results if r.get("category") == "mixed" and "score" in r]
    if not mixed_tests:
        return ""

    test_names = list(dict.fromkeys(r["test_name"] for r in mixed_tests))
    a_vals = []
    b_vals = []
    for name in test_names:
        matches = [r for r in mixed_tests if r["test_name"] == name]
        a_match = [r for r in matches if r["label"] == labels[0]]
        b_match = [r for r in matches if r["label"] == labels[1]]
        a_vals.append(a_match[0]["primary_value"] if a_match else 0)
        b_vals.append(b_match[0]["primary_value"] if b_match else 0)

    x = np.arange(len(test_names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width/2, a_vals, width, label=labels[0], color="#58a6ff", alpha=0.85)
    ax.bar(x + width/2, b_vals, width, label=labels[1], color="#f78166", alpha=0.85)

    # Determine unit from first test
    unit = mixed_tests[0].get("primary_unit", "")
    ax.set_ylabel(unit, fontweight="bold")
    ax.set_title("Mixed Workload (70% Read / 30% Write)", fontweight="bold", fontsize=14, pad=15)
    ax.set_xticks(x)
    short_names = [n.replace("Mixed R/W 70/30 ", "") for n in test_names]
    ax.set_xticklabels(short_names)
    ax.legend(loc="upper right", framealpha=0.3)
    ax.grid(axis="y", linestyle="--")
    ax.set_axisbelow(True)

    b64 = fig_to_base64(fig)
    plt.close(fig)
    return b64


def chart_scorecard(scored_results: list, labels: tuple) -> str:
    """Horizontal summary scorecard chart."""
    plt, np = setup_matplotlib()

    a_wins = sum(1 for r in scored_results if r["score"]["winner"] == "A")
    b_wins = sum(1 for r in scored_results if r["score"]["winner"] == "B")
    ties = sum(1 for r in scored_results if r["score"]["winner"] == "tie")

    fig, ax = plt.subplots(figsize=(8, 3))

    total = a_wins + b_wins + ties
    if total == 0:
        plt.close(fig)
        return ""

    bar_data = [a_wins, ties, b_wins]
    bar_labels_list = [f"{labels[0]}\n{a_wins} wins", f"Tie\n{ties}", f"{labels[1]}\n{b_wins} wins"]
    colors = ["#58a6ff", "#8b949e", "#f78166"]

    bars = ax.barh([0], [a_wins], color=colors[0], height=0.5, label=labels[0])
    ax.barh([0], [ties], left=[a_wins], color=colors[1], height=0.5, label="Tie")
    ax.barh([0], [b_wins], left=[a_wins + ties], color=colors[2], height=0.5, label=labels[1])

    # Labels inside bars
    positions = [a_wins/2, a_wins + ties/2, a_wins + ties + b_wins/2]
    for pos, count, lbl in zip(positions, bar_data, [labels[0], "Tie", labels[1]]):
        if count > 0:
            ax.text(pos, 0, f"{lbl}\n{count}", ha="center", va="center",
                    fontweight="bold", fontsize=10, color="white")

    ax.set_xlim(0, total)
    ax.set_yticks([])
    ax.set_xlabel(f"Tests (out of {total})", fontweight="bold")
    ax.set_title("Overall Scorecard", fontweight="bold", fontsize=14, pad=15)
    ax.grid(False)

    b64 = fig_to_base64(fig)
    plt.close(fig)
    return b64


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------
def generate_html_report(
    scored_results: list,
    labels: tuple,
    charts: dict,
    output_path: str,
    paths: tuple,
):
    """Generate a comprehensive HTML report."""

    a_wins = sum(1 for r in scored_results if r["score"]["winner"] == "A")
    b_wins = sum(1 for r in scored_results if r["score"]["winner"] == "B")
    ties = sum(1 for r in scored_results if r["score"]["winner"] == "tie")

    if a_wins > b_wins:
        overall_winner = labels[0]
        winner_color = "#58a6ff"
    elif b_wins > a_wins:
        overall_winner = labels[1]
        winner_color = "#f78166"
    else:
        overall_winner = "TIE"
        winner_color = "#8b949e"

    # Build results table rows
    rows_html = ""
    for r in scored_results:
        s = r["score"]
        val_a = s["a"]
        val_b = s["b"]
        unit = r.get("primary_unit", "")
        is_lat = r.get("category") == "latency"

        if s["winner"] == "A":
            a_class = "winner"
            b_class = "loser"
            badge = f'<span class="badge badge-a">{labels[0]} +{s["pct_diff"]}%</span>'
        elif s["winner"] == "B":
            a_class = "loser"
            b_class = "winner"
            badge = f'<span class="badge badge-b">{labels[1]} +{s["pct_diff"]}%</span>'
        else:
            a_class = b_class = ""
            badge = '<span class="badge badge-tie">TIE</span>'

        # Format values
        if "IOPS" in unit:
            a_fmt = f"{val_a:,.0f}"
            b_fmt = f"{val_b:,.0f}"
        elif "MB/s" in unit:
            a_fmt = f"{val_a:,.1f}"
            b_fmt = f"{val_b:,.1f}"
        elif "us" in unit:
            a_fmt = f"{val_a:,.1f}"
            b_fmt = f"{val_b:,.1f}"
        else:
            a_fmt = f"{val_a:,.2f}"
            b_fmt = f"{val_b:,.2f}"

        note = " (lower is better)" if is_lat else ""

        rows_html += f"""
        <tr>
            <td class="test-name">{r['test_name']}</td>
            <td class="{a_class}">{a_fmt} <span class="unit">{unit}</span></td>
            <td class="{b_class}">{b_fmt} <span class="unit">{unit}</span></td>
            <td>{badge}{note}</td>
        </tr>"""

    # Build chart sections
    chart_sections = ""
    for title, key in [
        ("Sequential Throughput", "sequential"),
        ("Queue Depth Scaling", "qd_scaling"),
        ("Latency (p99)", "latency"),
        ("Mixed Workload", "mixed"),
        ("Overall Scorecard", "scorecard"),
    ]:
        if key in charts and charts[key]:
            chart_sections += f"""
            <div class="chart-section">
                <img src="data:image/png;base64,{charts[key]}" alt="{title}">
            </div>"""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Disk Duel Report -- {labels[0]} vs {labels[1]}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        background: #0d1117;
        color: #c9d1d9;
        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif;
        line-height: 1.6;
        padding: 40px 20px;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    h1 {{
        font-size: 2.4em;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 8px;
        background: linear-gradient(135deg, #58a6ff, #f78166);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .subtitle {{ color: #8b949e; font-size: 0.95em; margin-bottom: 30px; }}
    .overall-winner {{
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 30px;
        text-align: center;
        margin-bottom: 40px;
    }}
    .overall-winner h2 {{ color: #8b949e; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px; }}
    .overall-winner .winner-name {{ font-size: 2em; font-weight: 800; color: {winner_color}; }}
    .overall-winner .score-line {{ color: #8b949e; margin-top: 8px; font-size: 1.1em; }}
    .score-line .a-score {{ color: #58a6ff; font-weight: 700; }}
    .score-line .b-score {{ color: #f78166; font-weight: 700; }}

    table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 40px;
        font-size: 0.9em;
    }}
    th {{
        background: #161b22;
        padding: 12px 16px;
        text-align: left;
        border-bottom: 2px solid #30363d;
        font-weight: 700;
        text-transform: uppercase;
        font-size: 0.8em;
        letter-spacing: 0.05em;
        color: #8b949e;
    }}
    td {{
        padding: 10px 16px;
        border-bottom: 1px solid #21262d;
    }}
    .test-name {{ font-weight: 600; color: #e6edf3; }}
    .winner {{ color: #3fb950; font-weight: 700; }}
    .loser {{ color: #8b949e; }}
    .unit {{ color: #484f58; font-size: 0.85em; }}
    .badge {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.8em;
        font-weight: 700;
    }}
    .badge-a {{ background: rgba(88,166,255,0.15); color: #58a6ff; }}
    .badge-b {{ background: rgba(247,129,102,0.15); color: #f78166; }}
    .badge-tie {{ background: rgba(139,148,158,0.15); color: #8b949e; }}

    .chart-section {{
        margin-bottom: 30px;
        text-align: center;
    }}
    .chart-section img {{
        max-width: 100%;
        border-radius: 8px;
        border: 1px solid #30363d;
    }}

    .meta {{
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid #21262d;
        color: #484f58;
        font-size: 0.8em;
    }}

    tr:hover {{ background: rgba(88,166,255,0.04); }}
</style>
</head>
<body>
<div class="container">
    <h1>Disk Duel</h1>
    <div class="subtitle">
        {labels[0]} (<code>{paths[0]}</code>) vs {labels[1]} (<code>{paths[1]}</code>)
    </div>

    <div class="overall-winner">
        <h2>Overall Winner</h2>
        <div class="winner-name">{overall_winner}</div>
        <div class="score-line">
            <span class="a-score">{labels[0]}: {a_wins}</span> &nbsp;/&nbsp;
            Tied: {ties} &nbsp;/&nbsp;
            <span class="b-score">{labels[1]}: {b_wins}</span>
        </div>
    </div>

    {chart_sections}

    <table>
        <thead>
            <tr>
                <th>Test</th>
                <th>{labels[0]}</th>
                <th>{labels[1]}</th>
                <th>Winner</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="meta">
        Generated {timestamp} by Disk Duel &bull; fio-based benchmarks &bull;
        Results may vary with drive temperature, background I/O, and filesystem state.
    </div>
</div>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------
def print_summary(scored_results: list, labels: tuple):
    """Print a formatted summary table to the console."""

    print(f"\n{C.BOLD}{'='*80}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  RESULTS SUMMARY{C.RESET}")
    print(f"{C.BOLD}{'='*80}{C.RESET}\n")

    # Header
    col1 = 32
    col2 = 16
    col3 = 16
    col4 = 20
    header = (
        f"  {'Test':<{col1}}"
        f"{labels[0]:>{col2}}"
        f"{labels[1]:>{col3}}"
        f"  {'Winner':<{col4}}"
    )
    print(f"{C.BOLD}{header}{C.RESET}")
    print(f"  {'-'*col1}{'-'*col2}{'-'*col3}  {'-'*col4}")

    def _color(text: str, color: str) -> str:
        # Wrap an already-padded string with ANSI codes; padding stays accurate
        # because the escape sequences are zero-width visually.
        return f"{color}{text}{C.RESET}" if color else text

    for r in scored_results:
        s = r["score"]
        unit = r.get("primary_unit", "")

        if "IOPS" in unit:
            a_raw = f"{s['a']:,.0f}"
            b_raw = f"{s['b']:,.0f}"
        else:
            a_raw = f"{s['a']:,.1f}"
            b_raw = f"{s['b']:,.1f}"

        # Pad to column width FIRST, then apply color so ANSI escapes don't
        # confuse the format width calculation.
        a_padded = f"{a_raw:>{col2}}"
        b_padded = f"{b_raw:>{col3}}"

        if s["winner"] == "A":
            winner_plain = f"{labels[0]} +{s['pct_diff']}%"
            winner_color = C.BLUE + C.BOLD
            a_padded = _color(a_padded, C.GREEN)
            b_padded = _color(b_padded, C.DIM)
        elif s["winner"] == "B":
            winner_plain = f"{labels[1]} +{s['pct_diff']}%"
            winner_color = C.RED + C.BOLD
            a_padded = _color(a_padded, C.DIM)
            b_padded = _color(b_padded, C.GREEN)
        else:
            winner_plain = "TIE"
            winner_color = C.DIM

        winner_padded = _color(f"{winner_plain:<{col4}}", winner_color)

        name_short = r["test_name"][:col1-2]
        print(f"  {name_short:<{col1}}{a_padded}{b_padded}  {winner_padded}")

    # Overall
    a_wins = sum(1 for r in scored_results if r["score"]["winner"] == "A")
    b_wins = sum(1 for r in scored_results if r["score"]["winner"] == "B")
    ties = sum(1 for r in scored_results if r["score"]["winner"] == "tie")

    print(f"\n{C.BOLD}{'='*80}{C.RESET}")
    if a_wins > b_wins:
        print(f"  {C.BOLD}{C.GREEN}OVERALL WINNER: {labels[0]}{C.RESET}  ({a_wins}-{b_wins}-{ties})")
    elif b_wins > a_wins:
        print(f"  {C.BOLD}{C.GREEN}OVERALL WINNER: {labels[1]}{C.RESET}  ({b_wins}-{a_wins}-{ties})")
    else:
        print(f"  {C.BOLD}{C.YELLOW}OVERALL: TIE{C.RESET}  ({a_wins}-{b_wins}-{ties})")
    print(f"{C.BOLD}{'='*80}{C.RESET}\n")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_path(path: str) -> str:
    """Validate that the path is writable and has enough space."""
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        print(f"{C.RED}Error: {path} is not a directory{C.RESET}")
        sys.exit(1)

    # Test writability
    test_file = os.path.join(path, ".disk_duel_write_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except PermissionError:
        print(f"{C.RED}Error: Cannot write to {path}{C.RESET}")
        sys.exit(1)

    # Check free space (need at least 5GB)
    stat = os.statvfs(path)
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
    if free_gb < 5:
        print(f"{C.YELLOW}Warning: Only {free_gb:.1f} GB free on {path}. "
              f"Some tests may be affected.{C.RESET}")

    return path


# ---------------------------------------------------------------------------
# Host & drive detection (macOS-focused; degrades gracefully elsewhere)
# ---------------------------------------------------------------------------
def get_host_info() -> dict:
    """Return identifying info for this host."""
    info = {
        "platform": sys.platform,
        "hostname": None,
        "machine_name": None,
        "machine_model": None,
        "chip_type": None,
        "physical_memory": None,
        "serial_number": None,
        "platform_uuid": None,
    }
    try:
        info["hostname"] = subprocess.check_output(["hostname"], text=True).strip()
    except Exception:
        pass

    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType", "-json"],
                text=True, timeout=10,
            )
            d = json.loads(out)["SPHardwareDataType"][0]
            info["machine_name"] = d.get("machine_name")
            info["machine_model"] = d.get("machine_model")
            info["chip_type"] = d.get("chip_type")
            info["physical_memory"] = d.get("physical_memory")
            info["serial_number"] = d.get("serial_number")
            info["platform_uuid"] = d.get("platform_UUID")
        except Exception:
            pass

    return info


def host_summary(host: dict) -> str:
    """One-line summary for display."""
    bits = []
    if host.get("machine_name"):
        m = host["machine_name"]
        if host.get("machine_model"):
            m += f" ({host['machine_model']})"
        bits.append(m)
    if host.get("chip_type"):
        bits.append(host["chip_type"])
    if host.get("physical_memory"):
        bits.append(f"{host['physical_memory']} RAM")
    if host.get("serial_number"):
        bits.append(f"Serial {host['serial_number']}")
    elif host.get("hostname"):
        bits.append(host["hostname"])
    return " · ".join(bits) if bits else "(unknown host)"


def _diskutil_info(target: str) -> dict:
    """Return diskutil info for a path/device as a dict, or {} on failure."""
    if sys.platform != "darwin":
        return {}
    try:
        import plistlib
        out = subprocess.check_output(
            ["diskutil", "info", "-plist", target], timeout=10,
        )
        return plistlib.loads(out)
    except Exception:
        return {}


def _detect_enclosures() -> dict:
    """Best-effort: return a dict of bsd_name -> 'Enclosure (Vendor)'.

    Strategy:
      1. Scrape the *text* output of system_profiler SPThunderboltDataType
         for non-Apple {Vendor Name, Device Name} pairs (these are
         enclosures). The JSON variant drops the vendor field on nested
         devices, so text parsing gets us strictly more info.
      2. Identify external NVMe drives by their controller name in
         SPNVMeDataType (-json) — anything not under 'Apple SSD Controller'
         is behind an external enclosure.
      3. Pair them up in declaration order if the counts match, or
         broadcast a single enclosure across all external drives.

    USB-connected enclosures (e.g. NVMe-to-USB) aren't covered yet; they'd
    follow the same pattern with SPUSBDataType."""
    if sys.platform != "darwin":
        return {}

    import re

    enclosures = []
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPThunderboltDataType"],
            text=True, timeout=10,
        )
        pat = re.compile(r"Vendor Name:\s+(.+?)\s*\n\s*Device Name:\s+(.+?)\s*\n")
        for m in pat.finditer(out):
            vendor = m.group(1).strip()
            name = m.group(2).strip()
            if "apple" not in vendor.lower():
                enclosures.append({"vendor": vendor, "name": name})
    except Exception:
        pass

    ext_bsds: list = []
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPNVMeDataType", "-json"],
            text=True, timeout=10,
        )
        for ctrl in json.loads(out).get("SPNVMeDataType", []):
            if "apple" in (ctrl.get("_name", "") or "").lower():
                continue
            for it in ctrl.get("_items", []) or []:
                bsd = it.get("bsd_name")
                if bsd:
                    ext_bsds.append(bsd)
    except Exception:
        pass

    result: dict = {}
    if not ext_bsds or not enclosures:
        return result
    if len(ext_bsds) == len(enclosures):
        pairs = zip(ext_bsds, enclosures)
    elif len(enclosures) == 1:
        # One enclosure, multiple drives (e.g. multi-bay box) -- share it.
        pairs = ((b, enclosures[0]) for b in ext_bsds)
    else:
        # Ambiguous: don't guess.
        return result

    for bsd, enc in pairs:
        result[bsd] = {"name": enc["name"], "vendor": enc["vendor"]}
    return result


def _is_writable(path: str) -> bool:
    """Test if we can create+remove a file in this directory."""
    if not os.path.isdir(path):
        return False
    test = os.path.join(path, f".disk_duel_write_test_{os.getpid()}")
    try:
        with open(test, "w") as f:
            f.write("x")
        os.remove(test)
        return True
    except (OSError, PermissionError):
        return False


def detect_drives() -> list:
    """Return a list of usable physical drives (one entry per parent disk).
    macOS only — returns [] elsewhere."""
    if sys.platform != "darwin":
        return []

    enclosures = _detect_enclosures()

    candidates = ["/"]
    try:
        for name in os.listdir("/Volumes"):
            full = f"/Volumes/{name}"
            try:
                if os.path.ismount(full):
                    candidates.append(full)
            except OSError:
                pass
    except OSError:
        pass

    drives = []
    seen = set()
    for path in candidates:
        info = _diskutil_info(path)
        if not info:
            continue

        bus = info.get("BusProtocol", "") or ""
        if any(x in bus.upper() for x in ("SMB", "AFP", "NFS")):
            continue

        # On APFS, ParentWholeDisk points at the synthesized container disk
        # (e.g. disk5), but SPNVMeDataType identifies physical drives by their
        # bare disk name (e.g. disk4). Resolve through APFSPhysicalStores.
        parent = info.get("ParentWholeDisk", "")
        phys_disk = parent
        stores = info.get("APFSPhysicalStores") or []
        if stores:
            store_id = stores[0].get("APFSPhysicalStore", "") if isinstance(stores[0], dict) else ""
            import re as _re
            m = _re.match(r"^(disk\d+)", store_id or "")
            if m:
                phys_disk = m.group(1)

        if not phys_disk or phys_disk in seen:
            continue
        seen.add(phys_disk)

        parent_info = _diskutil_info(phys_disk)
        media = (parent_info.get("MediaName") or info.get("MediaName") or "").strip()
        if media.endswith(" Media"):
            media = media[:-6]

        free = info.get("FreeSpace", 0) or 0
        size = info.get("Size", 0) or 0
        # diskutil's FreeSpace is unreliable on APFS containers — use statvfs.
        try:
            st = os.statvfs(path)
            statvfs_free = st.f_bavail * st.f_frsize
            statvfs_size = st.f_blocks * st.f_frsize
            if free == 0 or free > statvfs_size:
                free = statvfs_free
            if size == 0:
                size = statvfs_size
        except OSError:
            pass

        # On Apple Silicon, / is the read-only sealed system volume but the
        # data partition behind it (~ etc.) is on the same physical disk, so
        # test that location for writability instead of the mount point.
        test_target = os.path.expanduser("~") if path == "/" else path
        writable = _is_writable(test_target)

        drives.append({
            "mount": path,
            "volume_name": info.get("VolumeName") or os.path.basename(path) or path,
            "media_name": media,
            "bus_protocol": bus,
            "internal": bool(info.get("Internal", False)),
            "solid_state": bool(info.get("SolidState", False)),
            "free_gb": free / (1024**3),
            "size_gb": size / (1024**3),
            "writable": bool(writable),
            "enclosure_name": (enclosures.get(phys_disk) or {}).get("name"),
            "enclosure_vendor": (enclosures.get(phys_disk) or {}).get("vendor"),
            "device": phys_disk,
        })

    drives.sort(key=lambda d: (not d["writable"], -d["free_gb"]))
    return drives


def writable_test_path(drive: dict) -> Optional[str]:
    """Return a writable directory on this drive for fio to use.
    May prompt for sudo if no writable location is found."""
    mount = drive["mount"]

    # On Apple Silicon, / is the sealed read-only system volume; use ~.
    if mount == "/":
        home = os.path.expanduser("~")
        if _is_writable(home):
            return home

    if _is_writable(mount):
        return mount

    scratch = os.path.join(mount, "disk_duel_scratch")
    if _is_writable(scratch):
        return scratch

    # Need elevated permissions to create a writable scratch dir.
    print(f"  {C.YELLOW}{mount} is not writable as {os.environ.get('USER', 'this user')}.{C.RESET}")
    try:
        ans = input(
            f"  Create writable scratch dir at {scratch} via sudo? [y/N]: "
        ).strip().lower()
    except EOFError:
        return None
    if ans != "y":
        return None

    try:
        subprocess.run(["sudo", "mkdir", "-p", scratch], check=True)
        subprocess.run(["sudo", "chown", str(os.getuid()), scratch], check=True)
    except subprocess.CalledProcessError as e:
        print(f"  {C.RED}sudo failed: {e}{C.RESET}")
        return None

    return scratch if _is_writable(scratch) else None


def pick_drives_interactive(drives: list) -> tuple:
    """Display drive menu, return (drive_a, drive_b_or_None)."""
    print(f"\n{C.BOLD}{C.CYAN}Detected {len(drives)} drive(s):{C.RESET}\n")
    for i, d in enumerate(drives, 1):
        loc = f"{C.BLUE}Internal{C.RESET}" if d["internal"] else f"{C.MAG}External{C.RESET}"
        ssd = "SSD" if d["solid_state"] else "HDD"
        bus = d["bus_protocol"] or "?"
        free_str = f"{d['free_gb']:,.0f} GB free / {d['size_gb']:,.0f} GB"
        media = d["media_name"] or "(unknown device)"
        marker = f"{C.GREEN}[{i}]{C.RESET}" if d["writable"] else f"{C.DIM}[{i}]{C.RESET}"
        head = f"{C.BOLD}{d['volume_name']}{C.RESET}"
        if not d["writable"]:
            head += f" {C.DIM}(read-only){C.RESET}"
        print(f"  {marker} {head}")
        print(f"      {C.DIM}{media} · {loc} {ssd} · {bus} · {free_str}{C.RESET}")
        if d.get("enclosure_name"):
            enc = d["enclosure_name"]
            if d.get("enclosure_vendor"):
                enc += f" ({d['enclosure_vendor']})"
            print(f"      {C.DIM}Enclosure: {enc}{C.RESET}")
        print(f"      {C.DIM}Mount: {d['mount']}{C.RESET}")
        print()

    def _ask(prompt: str, *, allow_zero: bool = False) -> int:
        while True:
            try:
                ans = input(f"{C.BOLD}{prompt}: {C.RESET}").strip()
            except EOFError:
                sys.exit(1)
            if not ans:
                continue
            if allow_zero and ans == "0":
                return 0
            try:
                idx = int(ans)
                if 1 <= idx <= len(drives):
                    return idx
            except ValueError:
                pass
            valid = f"1-{len(drives)}" + (" (or 0 to skip)" if allow_zero else "")
            print(f"  {C.RED}Enter a number {valid}.{C.RESET}")

    a_idx = _ask("Pick the FIRST drive to benchmark")
    drive_a = drives[a_idx - 1]

    b_idx = _ask("Pick a SECOND drive for comparison (0 to run solo)", allow_zero=True)
    drive_b = None if b_idx == 0 else drives[b_idx - 1]
    if drive_b and drive_b["mount"] == drive_a["mount"]:
        print(f"  {C.YELLOW}Same drive selected twice; running solo.{C.RESET}")
        drive_b = None

    return drive_a, drive_b


# ---------------------------------------------------------------------------
# Solo (single-drive) summary + report
# ---------------------------------------------------------------------------
def print_summary_solo(results: list, label: str):
    """Print a formatted summary for a single-drive benchmark."""
    print(f"\n{C.BOLD}{'='*70}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  RESULTS SUMMARY -- {label}{C.RESET}")
    print(f"{C.BOLD}{'='*70}{C.RESET}\n")

    col1 = 36
    col2 = 18
    col3 = 14
    header = f"  {'Test':<{col1}}{'Result':>{col2}}  {'Unit':<{col3}}"
    print(f"{C.BOLD}{header}{C.RESET}")
    print(f"  {'-'*col1}{'-'*col2}  {'-'*col3}")

    for r in results:
        unit = r.get("primary_unit", "")
        val = r.get("primary_value", 0)
        if "IOPS" in unit:
            v_str = f"{val:,.0f}"
        else:
            v_str = f"{val:,.1f}"
        v_padded = f"{v_str:>{col2}}"
        name_short = r["test_name"][:col1-2]
        print(f"  {name_short:<{col1}}{C.GREEN}{v_padded}{C.RESET}  {C.DIM}{unit:<{col3}}{C.RESET}")

    print(f"\n{C.BOLD}{'='*70}{C.RESET}\n")


def generate_html_report_solo(
    results: list,
    label: str,
    output_path: str,
    path: str,
):
    """Generate a single-drive HTML report (no comparison, no charts)."""
    rows_html = ""
    for r in results:
        unit = r.get("primary_unit", "")
        val = r.get("primary_value", 0)
        if "IOPS" in unit:
            v_fmt = f"{val:,.0f}"
        else:
            v_fmt = f"{val:,.1f}"

        rows_html += f"""
        <tr>
            <td class="test-name">{r['test_name']}</td>
            <td class="value">{v_fmt} <span class="unit">{unit}</span></td>
            <td class="category">{r.get('category', '')}</td>
        </tr>"""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Disk Duel Report -- {label}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        background: #0d1117;
        color: #c9d1d9;
        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif;
        line-height: 1.6;
        padding: 40px 20px;
    }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    h1 {{
        font-size: 2.4em;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 8px;
        background: linear-gradient(135deg, #58a6ff, #f78166);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .subtitle {{ color: #8b949e; font-size: 0.95em; margin-bottom: 30px; }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 40px;
        font-size: 0.9em;
    }}
    th {{
        background: #161b22;
        padding: 12px 16px;
        text-align: left;
        border-bottom: 2px solid #30363d;
        font-weight: 700;
        text-transform: uppercase;
        font-size: 0.8em;
        letter-spacing: 0.05em;
        color: #8b949e;
    }}
    td {{
        padding: 10px 16px;
        border-bottom: 1px solid #21262d;
    }}
    .test-name {{ font-weight: 600; color: #e6edf3; }}
    .value {{ color: #3fb950; font-weight: 700; }}
    .unit {{ color: #484f58; font-size: 0.85em; font-weight: 400; }}
    .category {{ color: #8b949e; font-size: 0.85em; text-transform: capitalize; }}
    .meta {{
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid #21262d;
        color: #484f58;
        font-size: 0.8em;
    }}
    tr:hover {{ background: rgba(88,166,255,0.04); }}
</style>
</head>
<body>
<div class="container">
    <h1>Disk Duel</h1>
    <div class="subtitle">
        Solo benchmark of <strong>{label}</strong> (<code>{path}</code>)
    </div>

    <table>
        <thead>
            <tr>
                <th>Test</th>
                <th>Result</th>
                <th>Category</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="meta">
        Generated {timestamp} by Disk Duel &bull; fio-based benchmarks &bull;
        Results may vary with drive temperature, background I/O, and filesystem state.
    </div>
</div>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Upload to public leaderboard
# ---------------------------------------------------------------------------
SCRIPT_VERSION = "0.2.0"
DEFAULT_UPLOAD_URL = "https://apps.cleartextlabs.com/disk-duel/api/v1/runs/"

# Proof-of-work parameters. The server verifies that
#   sha256(f"disk-duel:v1:{serial}:{timestamp}:{nonce}") has at least
#   POW_DIFFICULTY_BITS leading zero bits. Difficulty 20 averages ~0.5-2 s
#   on a recent laptop and makes scripted spam meaningfully expensive.
POW_DIFFICULTY_BITS = 20
POW_VERSION = "v1"


def _has_leading_zero_bits(digest: bytes, bits: int) -> bool:
    full, partial = divmod(bits, 8)
    if any(b for b in digest[:full]):
        return False
    if partial == 0:
        return True
    return (digest[full] >> (8 - partial)) == 0


def _compute_pow(serial: str, timestamp: str, difficulty: int = POW_DIFFICULTY_BITS) -> int:
    import hashlib
    prefix = f"disk-duel:{POW_VERSION}:{serial}:{timestamp}:".encode()
    nonce = 0
    while True:
        h = hashlib.sha256(prefix + str(nonce).encode()).digest()
        if _has_leading_zero_bits(h, difficulty):
            return nonce
        nonce += 1


class _PowSpinner:
    """Braille spinner with rotating mining-themed verbs while we mine."""
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    VERBS = [
        "Hashing nonces",
        "Mining entropy",
        "Forging the seal",
        "Hammering bytes",
        "Quarrying for zeros",
        "Sifting candidates",
        "Polishing the proof",
        "Tumbling bits",
        "Chiseling the work",
        "Tempering the hash",
        "Smithing leading zeros",
        "Wrangling nonces",
        "Burnishing bytes",
        "Conjuring entropy",
        "Sharpening the proof",
        "Coaxing the SHA",
        "Wheedling the lock",
    ]

    def __init__(self):
        import threading
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def __enter__(self):
        if not sys.stdout.isatty():
            return self
        import threading
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def _run(self):
        import itertools
        import random
        import time
        frames = itertools.cycle(self.FRAMES)
        verbs = self.VERBS[:]
        random.shuffle(verbs)
        verb_iter = itertools.cycle(verbs)
        verb = next(verbs.__iter__())
        next_swap = time.monotonic() + 0.6
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_swap:
                verb = next(verb_iter)
                next_swap = now + 0.6 + random.random() * 0.4
            sys.stdout.write(f"\r  {C.CYAN}{next(frames)}{C.RESET} {verb}…")
            sys.stdout.flush()
            time.sleep(0.08)


def _drive_for_path(path: str, drives: list | None = None) -> dict | None:
    """Return the detected-drive dict whose mount is the longest prefix
    of `path`. Falls back to a fresh detect_drives() if not supplied."""
    if drives is None:
        drives = detect_drives()
    real = os.path.realpath(path)
    best = None
    best_len = -1
    for d in drives:
        m = os.path.realpath(d["mount"])
        # `/` mount is shorter than any other and matches everything; only
        # accept it if no more specific mount matches.
        if real == m or real.startswith(m.rstrip("/") + "/"):
            if len(m) > best_len:
                best = d
                best_len = len(m)
    return best


def _payload_drive(label: str, path: str, meta: dict | None) -> dict:
    """Shape a detected-drive dict into the structure the API expects."""
    if meta is None:
        return {"label": label, "path": path, "media_name": label}
    return {
        "label": label,
        "path": path,
        "device": meta.get("device"),
        "media_name": meta.get("media_name") or label,
        "bus_protocol": meta.get("bus_protocol"),
        "internal": bool(meta.get("internal")),
        "solid_state": bool(meta.get("solid_state", True)),
        "size_gb": meta.get("size_gb"),
        "enclosure_name": meta.get("enclosure_name"),
        "enclosure_vendor": meta.get("enclosure_vendor"),
    }


def upload_results(
    payload: dict, *, url: str, api_key: str | None = None, timeout: int = 30,
) -> dict:
    """POST the payload to the leaderboard. Returns the parsed JSON response."""
    import urllib.request
    import urllib.error

    body = json.dumps(payload, default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"disk-duel/{SCRIPT_VERSION}",
    }
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"upload failed ({e.code}): {detail[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"upload failed: {e.reason}") from e


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Disk Duel -- Comprehensive Drive Benchmark & Comparison",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path_a", nargs="?", default=None,
        help="Path/mount point for Drive A (omit to use the interactive drive menu)"
    )
    parser.add_argument(
        "path_b", nargs="?", default=None,
        help="(Optional) Path/mount point for Drive B. Omit to run solo benchmark on path_a only."
    )
    parser.add_argument(
        "--labels", nargs="+", default=None, metavar="LABEL",
        help="Labels for the drives (1 label in solo mode, 2 in dual mode; default: path basenames)"
    )
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="Disable the drive menu (requires path_a to be provided)"
    )
    upload_group = parser.add_mutually_exclusive_group()
    upload_group.add_argument(
        "--upload", action="store_true",
        help="Submit the result to the public leaderboard at apps.cleartextlabs.com/disk-duel."
    )
    upload_group.add_argument(
        "--no-upload", action="store_true",
        help="Do not upload, even if running interactively."
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Run shorter tests for quick validation"
    )
    parser.add_argument(
        "--size-multiplier", type=float, default=1.0,
        help="Scale test file sizes (2.0 = double, 0.5 = half)"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output path for HTML report (default: disk_duel_report.html in current directory)"
    )
    parser.add_argument(
        "--skip-charts", action="store_true",
        help="Skip chart generation (useful if matplotlib is not available)"
    )

    args = parser.parse_args()

    banner()

    # Host detection
    host = get_host_info()
    print(f"  {C.BOLD}Host:{C.RESET} {C.CYAN}{host_summary(host)}{C.RESET}")
    print()

    # Resolve paths + labels: explicit args take precedence, else interactive menu.
    drive_meta_a: Optional[dict] = None
    drive_meta_b: Optional[dict] = None
    if args.path_a:
        print(f"{C.BOLD}Validating drives...{C.RESET}")
        path_a = validate_path(args.path_a)
        path_b = validate_path(args.path_b) if args.path_b else None
        # Best-effort metadata enrichment for upload payloads.
        all_drives = detect_drives()
        drive_meta_a = _drive_for_path(path_a, all_drives)
        drive_meta_b = _drive_for_path(path_b, all_drives) if path_b else None
        if path_b is None:
            label_a = (args.labels[0] if args.labels else None) \
                or (drive_meta_a or {}).get("volume_name") \
                or os.path.basename(path_a) or path_a
            label_b = None
        else:
            if args.labels and len(args.labels) >= 2:
                label_a, label_b = args.labels[0], args.labels[1]
            else:
                label_a = (drive_meta_a or {}).get("volume_name") or os.path.basename(path_a) or path_a
                label_b = (drive_meta_b or {}).get("volume_name") or os.path.basename(path_b) or path_b
    elif args.non_interactive:
        parser.error("path_a is required when --non-interactive is set")
    else:
        print(f"{C.BOLD}Detecting drives...{C.RESET}")
        drives = detect_drives()
        if not drives:
            print(f"{C.RED}No usable drives detected. Pass paths explicitly:{C.RESET}")
            print(f"  python3 disk_duel.py /path/a [/path/b]")
            sys.exit(1)
        drive_a, drive_b = pick_drives_interactive(drives)
        drive_meta_a = drive_a
        drive_meta_b = drive_b
        path_a = writable_test_path(drive_a)
        if path_a is None:
            print(f"{C.RED}No writable test path on {drive_a['volume_name']}.{C.RESET}")
            sys.exit(1)
        label_a = drive_a["volume_name"]
        if drive_b is None:
            path_b = None
            label_b = None
        else:
            path_b = writable_test_path(drive_b)
            if path_b is None:
                print(f"{C.RED}No writable test path on {drive_b['volume_name']}.{C.RESET}")
                sys.exit(1)
            label_b = drive_b["volume_name"]

    solo = path_b is None
    if solo:
        labels = (label_a,)
        print(f"  Drive:   {C.BLUE}{C.BOLD}{labels[0]}{C.RESET} ({path_a})")
        print(f"  {C.YELLOW}Solo mode -- no comparison.{C.RESET}")
    else:
        labels = (label_a, label_b)
        print(f"  Drive A: {C.BLUE}{C.BOLD}{labels[0]}{C.RESET} ({path_a})")
        print(f"  Drive B: {C.RED}{C.BOLD}{labels[1]}{C.RESET} ({path_b})")
    print()

    # Check fio
    print(f"{C.BOLD}Checking dependencies...{C.RESET}")
    check_fio()

    has_matplotlib = True
    if not args.skip_charts:
        try:
            import matplotlib
            import numpy
            print(f"  {C.DIM}matplotlib: {matplotlib.__version__}{C.RESET}")
        except ImportError:
            print(f"  {C.YELLOW}matplotlib not found -- charts will be skipped.{C.RESET}")
            print(f"  {C.YELLOW}Install with: pip3 install matplotlib numpy{C.RESET}")
            has_matplotlib = False
    else:
        has_matplotlib = False

    print()

    # Get test suite
    tests = get_test_suite(quick=args.quick, size_mult=args.size_multiplier)
    total_tests = len(tests)

    drive_count = 1 if solo else 2
    print(f"{C.BOLD}Running {total_tests} benchmarks on "
          f"{'the drive' if solo else 'each drive'} "
          f"({total_tests * drive_count} total tests)...{C.RESET}")
    if args.quick:
        print(f"  {C.YELLOW}(quick mode -- shorter runtimes){C.RESET}")
    print()

    # Run benchmarks
    all_results = []
    scored_results = []  # only populated in dual mode
    solo_results = []    # only populated in solo mode

    for i, test in enumerate(tests):
        test_num = i + 1
        print(f"{C.BOLD}[{test_num}/{total_tests}] {test['name']}{C.RESET}")

        # Drive A
        print(f"  {C.BLUE}{labels[0]}{C.RESET}...", end=" ", flush=True)
        t0 = time.time()
        result_a = run_fio_test(test, path_a, labels[0])
        elapsed_a = time.time() - t0

        if result_a.get("error"):
            print(f"{C.RED}FAILED{C.RESET}")
            continue
        val_a = result_a["primary_value"]
        print(f"{C.GREEN}{val_a:,.1f} {test['unit']}{C.RESET} ({elapsed_a:.1f}s)")

        if solo:
            all_results.append(result_a)
            solo_results.append({
                "test_name": test["name"],
                "category": test["category"],
                "primary_unit": test["unit"],
                "primary_value": val_a,
            })
            print()
            continue

        # Drive B
        print(f"  {C.RED}{labels[1]}{C.RESET}...", end=" ", flush=True)
        t0 = time.time()
        result_b = run_fio_test(test, path_b, labels[1])
        elapsed_b = time.time() - t0

        if result_b.get("error"):
            print(f"{C.RED}FAILED{C.RESET}")
            continue
        val_b = result_b["primary_value"]
        print(f"{C.GREEN}{val_b:,.1f} {test['unit']}{C.RESET} ({elapsed_b:.1f}s)")

        # Score
        is_latency = test["category"] == "latency"
        score = score_test(val_a, val_b, is_latency=is_latency)

        if score["winner"] == "A":
            print(f"  {C.BLUE}{C.BOLD}>>> {labels[0]} wins (+{score['pct_diff']}%){C.RESET}")
        elif score["winner"] == "B":
            print(f"  {C.RED}{C.BOLD}>>> {labels[1]} wins (+{score['pct_diff']}%){C.RESET}")
        else:
            print(f"  {C.DIM}>>> TIE{C.RESET}")

        result_a["score"] = score
        result_b["score"] = score
        all_results.append(result_a)
        all_results.append(result_b)

        scored_entry = {
            "test_name": test["name"],
            "category": test["category"],
            "primary_unit": test["unit"],
            "score": score,
        }
        scored_results.append(scored_entry)

        print()

    # Print console summary
    if solo:
        print_summary_solo(solo_results, labels[0])
    else:
        print_summary(scored_results, labels)

    # Generate charts (dual mode only)
    charts = {}
    if not solo and has_matplotlib and not args.skip_charts:
        print(f"{C.BOLD}Generating charts...{C.RESET}")
        try:
            charts["sequential"] = chart_sequential(all_results, labels)
            charts["qd_scaling"] = chart_qd_scaling(all_results, labels)
            charts["latency"] = chart_latency(all_results, labels)
            charts["mixed"] = chart_mixed(all_results, labels)
            charts["scorecard"] = chart_scorecard(scored_results, labels)
            print(f"  {C.GREEN}Done{C.RESET}")
        except Exception as e:
            print(f"  {C.YELLOW}Chart generation failed: {e}{C.RESET}")
            charts = {}
        print()

    # Generate HTML report
    output_path = args.output or os.path.join(os.getcwd(), "disk_duel_report.html")
    print(f"{C.BOLD}Generating HTML report...{C.RESET}")
    if solo:
        generate_html_report_solo(
            results=solo_results,
            label=labels[0],
            output_path=output_path,
            path=path_a,
        )
    else:
        generate_html_report(
            scored_results=scored_results,
            labels=labels,
            charts=charts,
            output_path=output_path,
            paths=(path_a, path_b),
        )
    print(f"  {C.GREEN}Report saved to: {output_path}{C.RESET}")

    # Also dump raw JSON results
    json_path = output_path.replace(".html", ".json")
    payload_drives = [_payload_drive(label_a, path_a, drive_meta_a)]
    if not solo:
        payload_drives.append(_payload_drive(label_b, path_b, drive_meta_b))

    if solo:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "solo",
            "host": host,
            "label": labels[0],
            "path": path_a,
            "drives": payload_drives,
            "quick": args.quick,
            "size_multiplier": args.size_multiplier,
            "script_version": SCRIPT_VERSION,
            "results": solo_results,
            "all_results": all_results,
        }
    else:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "dual",
            "host": host,
            "labels": list(labels),
            "paths": [path_a, path_b],
            "drives": payload_drives,
            "quick": args.quick,
            "size_multiplier": args.size_multiplier,
            "script_version": SCRIPT_VERSION,
            "results": scored_results,
            "all_results": [
                {k: v for k, v in r.items() if k != "score"}
                for r in all_results
            ],
        }
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"  {C.GREEN}Raw data saved to: {json_path}{C.RESET}")
    print()

    # Optional upload to public leaderboard. No API key required -- the
    # endpoint is intentionally unauthenticated (script is open source,
    # embedded keys are theater). DISK_DUEL_API_KEY is still respected if
    # set, for future admin-flagged uploads.
    upload_url = os.environ.get("DISK_DUEL_UPLOAD_URL", DEFAULT_UPLOAD_URL).strip()
    api_key = os.environ.get("DISK_DUEL_API_KEY", "").strip() or None
    should_upload = False
    if args.upload:
        should_upload = True
    elif args.no_upload:
        should_upload = False
    elif sys.stdin.isatty():
        try:
            ans = input(f"{C.BOLD}Upload to public leaderboard?{C.RESET} [y/N]: ").strip().lower()
            should_upload = ans == "y"
        except EOFError:
            should_upload = False

    if should_upload:
        # Proof-of-work: the public endpoint is unauthenticated, so a small
        # PoW makes scripted spam non-trivial (~0.5-2s per upload). The
        # nonce travels in the payload; the server recomputes the hash.
        serial_for_pow = (host.get("serial_number") or "").strip()
        ts = payload["timestamp"]
        print(f"{C.BOLD}Computing proof of work...{C.RESET}")
        with _PowSpinner():
            nonce = _compute_pow(serial_for_pow, ts, POW_DIFFICULTY_BITS)
        payload["pow_nonce"] = nonce
        payload["pow_difficulty"] = POW_DIFFICULTY_BITS
        payload["pow_version"] = POW_VERSION

        print(f"{C.BOLD}Uploading...{C.RESET}")
        try:
            resp = upload_results(payload, url=upload_url, api_key=api_key)
            run_url = resp.get("run_url", "")
            machine_url = resp.get("machine_url", "")
            # Pad to box width so the URL line stands clear of normal output.
            print()
            print(f"  {C.GREEN}{C.BOLD}Published.{C.RESET} View your run:")
            print()
            print(f"    {C.CYAN}{C.BOLD}{run_url}{C.RESET}")
            print()
            print(f"  {C.DIM}All runs from this machine:{C.RESET} {C.DIM}{machine_url}{C.RESET}")
        except Exception as e:
            print(f"  {C.RED}Upload failed: {e}{C.RESET}")
        print()

    print(f"{C.BOLD}{C.CYAN}Done! Open the HTML report in a browser for the full breakdown.{C.RESET}")


if __name__ == "__main__":
    main()
