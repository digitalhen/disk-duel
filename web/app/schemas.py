from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HostInfo(BaseModel):
    platform: str | None = None
    hostname: str | None = None
    machine_name: str | None = None
    machine_model: str | None = None
    chip_type: str | None = None
    physical_memory: str | None = None
    serial_number: str | None = None
    platform_uuid: str | None = None


class DriveInfo(BaseModel):
    """Per-drive metadata captured by the script's interactive detection.
    Optional — older script versions only ship labels."""
    label: str
    path: str | None = None
    device: str | None = None
    media_name: str | None = None
    bus_protocol: str | None = None
    internal: bool = False
    solid_state: bool = True
    size_gb: float | None = None
    enclosure_name: str | None = None
    enclosure_vendor: str | None = None


class TestResultIn(BaseModel):
    """Per-(test, drive) row, matching the keys the script writes into
    all_results. Most lat/bw fields are optional because not every test
    populates both read and write sides."""
    # Allow extra keys (e.g. raw fio internals like write_bw_kb) so the full
    # script payload survives in raw_payload without being silently dropped.
    model_config = ConfigDict(extra="allow")

    test_name: str
    category: str
    label: str
    primary_value: float | None = None
    primary_unit: str | None = None
    read_bw_mb: float | None = None
    read_iops: float | None = None
    read_lat_us_mean: float | None = None
    read_lat_us_p50: float | None = None
    read_lat_us_p99: float | None = None
    read_lat_us_p999: float | None = None
    write_bw_mb: float | None = None
    write_iops: float | None = None
    write_lat_us_mean: float | None = None
    write_lat_us_p50: float | None = None
    write_lat_us_p99: float | None = None
    write_lat_us_p999: float | None = None
    # Multi-run dispersion (script ≥ v0.3). primary_value is the median
    # across `runs` trials; the rest describe the distribution.
    runs: int | None = None
    primary_value_samples: list[float] | None = None
    primary_value_min: float | None = None
    primary_value_max: float | None = None
    primary_value_stdev: float | None = None
    # Per-second bandwidth + per-N-second temperature samples produced by
    # `--sustained` runs. dict-shaped to keep the schema flexible:
    #   {"bw_samples": [[t_s, mb_s], ...],
    #    "temp_samples": [[t_s, celsius|null], ...],
    #    "device": "/dev/diskN", "bw_unit": "MB/s", "temp_unit": "C", ...}
    time_series: dict[str, Any] | None = None


class RunIn(BaseModel):
    """The script's JSON payload, with a few extra fields the API expects.
    `drives` is the new structured drive metadata (script ≥ v0.2);
    older payloads can omit it and labels alone become the drive identity."""
    timestamp: str
    mode: str  # 'solo' | 'dual'
    host: HostInfo
    label: str | None = None
    label_a: str | None = None
    labels: list[str] | None = None
    path: str | None = None
    paths: list[str] | None = None
    drives: list[DriveInfo] = Field(default_factory=list)
    quick: bool = False
    size_multiplier: float = 1.0
    runs: int | None = None
    script_version: str | None = None
    all_results: list[TestResultIn]
    results: list[dict[str, Any]] = Field(default_factory=list)

    # Proof-of-work: required on the public submit endpoint.
    pow_nonce: int | None = None
    pow_difficulty: int | None = None
    pow_version: str | None = None


class RunOut(BaseModel):
    run_slug: str
    machine_slug: str
    run_url: str
    machine_url: str


class ThermalDriveResult(BaseModel):
    """One drive's slice of an attach-thermal payload. Matches the keys
    `run_thermal_test` writes into all_results, plus the time_series dict."""
    model_config = ConfigDict(extra="allow")

    label: str
    primary_value: float
    primary_unit: str = "MB/s"
    write_bw_mb: float | None = None
    write_iops: float | None = None
    write_lat_us_mean: float | None = None
    write_lat_us_p50: float | None = None
    write_lat_us_p99: float | None = None
    write_lat_us_p999: float | None = None
    time_series: dict[str, Any]


class AttachThermalIn(BaseModel):
    """Body for POST /api/v1/admin/runs/{slug}/attach-thermal — adds a
    sustained-write thermal test (with bandwidth + temperature time series)
    to an existing run. Idempotent: re-posting replaces the test data for
    the same (run, drive, test_name) triple."""
    test_name: str = "Sustained Write 5min"
    category: str = "thermal"
    drives: list[ThermalDriveResult]


class AttachThermalOut(BaseModel):
    run_slug: str
    run_url: str
    drives_updated: int
