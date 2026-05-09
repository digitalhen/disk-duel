# Disk Duel

Comprehensive `fio`-based drive benchmark with a scored HTML report. Compare two drives head-to-head, or benchmark a single drive on its own. Includes an interactive drive picker with auto-detection of host hardware and mounted drives on macOS.

Optionally publish your results to the public leaderboard at **[apps.cleartextlabs.com/disk-duel](https://apps.cleartextlabs.com/disk-duel/)** with `--upload`. Serials are hashed before storage and never displayed.

The benchmark suite covers sequential throughput (incl. SEQ1M-QD8), random 4K IOPS at QD1/4/16/32/64, large-block random, mixed read/write, sustained sequential write, and QD1 latency — 23 tests total.

## Quick start

One line. Downloads the script and launches the interactive drive menu — no install, no clone.

```bash
curl -fsSL https://raw.githubusercontent.com/digitalhen/disk-duel/main/disk_duel.py -o /tmp/disk_duel.py && python3 /tmp/disk_duel.py
```

The HTML/JSON report lands in your current directory. Make sure `fio` is installed (`brew install fio` on macOS, `sudo apt-get install fio` on Debian/Ubuntu) — the script tells you if it's missing.

> Why download-then-run instead of `curl … | python3 -`? The interactive menu reads from stdin, which the pipe would have already consumed.

If you'd rather skip the menu and pass paths directly, append them — `python3 /tmp/disk_duel.py /Volumes/A /Volumes/B` (dual) or `python3 /tmp/disk_duel.py /Volumes/A` (solo).

## Publishing to the leaderboard

The site at [apps.cleartextlabs.com/disk-duel](https://apps.cleartextlabs.com/disk-duel/) collects runs from anyone running the script. To submit yours:

```bash
python3 /tmp/disk_duel.py --upload
```

No API key required. The script does a small proof-of-work (~1–2 s on a recent laptop) before submitting; that, plus per-machine and per-IP rate limits on the server, is the spam protection.

On success the script prints stable public URLs for your run and your machine. The serial number is sha256'd before storage and never displayed; URLs use opaque hashids.

The web app lives in [`web/`](./web/) — see [web/README.md](./web/README.md) for deployment.

## What the interactive menu does

When you run with no positional arguments (which is what the curl one-liner above does), the script:

1. **Identify the host** — model, chip, RAM, and serial number (via `system_profiler SPHardwareDataType`). The serial is included in the JSON output so reports from different machines can be told apart.
2. **List local physical drives** — by walking `/` and `/Volumes/*`, calling `diskutil info -plist` on each, and collapsing volumes that share a parent disk. Network shares (SMB/NFS/AFP) and APFS snapshots are filtered out. For each drive you see: volume name, media name (e.g. `WD_BLACK SN850X 4000GB`), Internal vs External, bus protocol (Apple Fabric / PCI-Express / USB / Thunderbolt), and free/total space.
3. **Ask for the first drive**, then **optionally a second** (enter `0` for solo mode).
4. **Auto-pick a writable test directory** on each chosen drive — `~` for the boot volume (since `/` is read-only on Apple Silicon), the mount point otherwise. If the chosen drive isn't writable, the script offers to `sudo mkdir`+`chown` a scratch directory on it.

Add `--non-interactive` to disable the menu and require explicit paths (useful for scripting/CI).

## Requirements

```bash
brew install fio                     # macOS
sudo apt-get install fio             # Debian/Ubuntu

pip3 install matplotlib numpy        # optional; only used for dual-mode charts
```

You also need at least ~5 GB free on each drive for the default test sizes.

## Dual mode (compare two drives)

Pass two paths. Every test runs on both drives, gets a percentage-scored winner, and the report includes side-by-side bar/line charts plus an overall scorecard.

```bash
python3 disk_duel.py /path/to/drive_a /path/to/drive_b
```

Examples:

```bash
# Internal SSD vs an external Thunderbolt enclosure
python3 disk_duel.py /Volumes/Internal /Volumes/External \
    --labels "Internal SSD" "TB5 Enclosure"

# Quick run for sanity checks (5–10s per test instead of 10–30s)
python3 disk_duel.py /tmp/a /tmp/b --quick

# Larger test files for more accurate sustained-write numbers
python3 disk_duel.py /tmp/a /tmp/b --size-multiplier 2
```

Outputs (in the current directory by default):

- `disk_duel_report.html` — full report with charts, comparison table, and overall winner
- `disk_duel_report.json` — raw fio data for every test on both drives

## Solo mode (single drive)

Pass one path. Same 23-test suite, but no comparison: the report is a single-column scorecard with absolute numbers.

```bash
python3 disk_duel.py /path/to/drive
```

Examples:

```bash
# Benchmark just the boot drive
python3 disk_duel.py /

# Benchmark an external SSD with a custom label
python3 disk_duel.py /Volumes/T705 --labels "Crucial T705"

# Quick run
python3 disk_duel.py /Volumes/T705 --quick
```

Solo outputs are the same filenames but with a simpler structure:

- `disk_duel_report.html` — single-drive results table (no charts)
- `disk_duel_report.json` — `{"mode": "solo", "label": ..., "path": ..., "results": [...], "all_results": [...]}`

`matplotlib` and `numpy` are not required in solo mode.

## Common options

| Flag | Description |
|---|---|
| `--labels LABEL [LABEL ...]` | Override drive labels. One in solo mode, two in dual mode. Defaults to the basenames of the paths. |
| `--quick` | Halves the per-test runtime. Good for shaking down a setup; numbers are noisier. |
| `--size-multiplier N` | Scale test file sizes (e.g. `2.0` doubles, `0.5` halves). Larger files give more accurate sustained-write numbers but take longer. |
| `--output PATH`, `-o PATH` | Where to write the HTML report. JSON is always written next to it with a `.json` extension. |
| `--skip-charts` | Skip chart generation in dual mode. (Solo mode never generates charts.) |

## What the tests measure

| Category | Tests | Primary metric |
|---|---|---|
| Sequential | Read/Write at 1M and 128K block sizes, plus 1M QD8 (matches AmorphousDiskMark SEQ1M-QD8) | MB/s |
| Random 4K | Read/Write at QD1, QD4, QD16, QD32, QD64 | IOPS |
| Large random | Read/Write at 64K QD16 | MB/s |
| Mixed | 70/30 R/W at 4K QD16 and 64K QD16 | IOPS or MB/s |
| Sustained | 30s sequential write at 1M QD4 | MB/s |
| Latency | QD1 random read/write | p99 microseconds |

All tests run with `--direct=1` where supported (falls back gracefully on filesystems that don't allow it) and `--end_fsync=1`. On macOS, queue depths > 1 use `posixaio` since the default `psync` engine ignores `iodepth`.

## Notes & gotchas

- The script writes a temp file `.disk_duel_testfile` at each path during the run and removes it afterward. If a previous run was interrupted, you may want to delete it manually.
- Results vary with drive temperature, fill level (especially APFS past ~85% capacity), and background I/O. Quitting heavy apps and letting the drive cool between runs gives more consistent numbers.
- On Apple Silicon, the internal SSD always runs through hardware encryption via the Secure Enclave, which adds a per-IO latency floor that external drives can avoid. Don't be surprised if a fast external NVMe beats the internal on QD1 latency.
- `fio --version` and `matplotlib.__version__` are printed at startup so you can check what's actually in use.
