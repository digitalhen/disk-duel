from typing import Any

from pydantic import BaseModel, Field


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
    script_version: str | None = None
    all_results: list[TestResultIn]
    results: list[dict[str, Any]] = Field(default_factory=list)


class RunOut(BaseModel):
    run_slug: str
    machine_slug: str
    run_url: str
    machine_url: str
