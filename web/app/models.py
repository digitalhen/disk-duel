from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    machine_name: Mapped[str | None] = mapped_column(String(128))
    machine_model: Mapped[str | None] = mapped_column(String(64), index=True)
    chip_type: Mapped[str | None] = mapped_column(String(64), index=True)
    physical_memory: Mapped[str | None] = mapped_column(String(32))
    platform: Mapped[str | None] = mapped_column(String(32))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    drives: Mapped[list["Drive"]] = relationship(back_populates="machine", cascade="all,delete-orphan")
    runs: Mapped[list["Run"]] = relationship(back_populates="machine", cascade="all,delete-orphan")


class Drive(Base):
    __tablename__ = "drives"
    __table_args__ = (
        UniqueConstraint("machine_id", "media_name", name="uq_drives_machine_media"),
        Index("ix_drives_media_name", "media_name"),
        Index("ix_drives_enclosure_name", "enclosure_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    device: Mapped[str | None] = mapped_column(String(32))
    media_name: Mapped[str] = mapped_column(String(128))
    bus_protocol: Mapped[str | None] = mapped_column(String(32), index=True)
    internal: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    solid_state: Mapped[bool] = mapped_column(Boolean, default=True)
    size_gb: Mapped[float | None] = mapped_column(Float)
    enclosure_name: Mapped[str | None] = mapped_column(String(128))
    enclosure_vendor: Mapped[str | None] = mapped_column(String(128))

    machine: Mapped[Machine] = relationship(back_populates="drives")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(8))  # 'solo' | 'dual'
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    drive_a_id: Mapped[int] = mapped_column(ForeignKey("drives.id", ondelete="CASCADE"))
    drive_b_id: Mapped[int | None] = mapped_column(ForeignKey("drives.id", ondelete="CASCADE"))
    label_a: Mapped[str] = mapped_column(String(128))
    label_b: Mapped[str | None] = mapped_column(String(128))
    quick: Mapped[bool] = mapped_column(Boolean, default=False)
    size_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    script_version: Mapped[str | None] = mapped_column(String(32))
    raw_payload: Mapped[dict] = mapped_column(JSONB)

    machine: Mapped[Machine] = relationship(back_populates="runs")
    drive_a: Mapped[Drive] = relationship(foreign_keys=[drive_a_id])
    drive_b: Mapped[Drive | None] = relationship(foreign_keys=[drive_b_id])
    test_results: Mapped[list["TestResult"]] = relationship(back_populates="run", cascade="all,delete-orphan")


class TestResult(Base):
    __tablename__ = "test_results"
    __table_args__ = (
        Index("ix_test_results_test_value", "test_name", "primary_value"),
        Index("ix_test_results_drive_test", "drive_id", "test_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    drive_id: Mapped[int] = mapped_column(ForeignKey("drives.id", ondelete="CASCADE"), index=True)
    test_name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), index=True)
    primary_unit: Mapped[str] = mapped_column(String(16))
    primary_value: Mapped[float] = mapped_column(Float)
    read_bw_mb: Mapped[float | None] = mapped_column(Float)
    read_iops: Mapped[float | None] = mapped_column(Float)
    read_lat_us_mean: Mapped[float | None] = mapped_column(Float)
    read_lat_us_p50: Mapped[float | None] = mapped_column(Float)
    read_lat_us_p99: Mapped[float | None] = mapped_column(Float)
    read_lat_us_p999: Mapped[float | None] = mapped_column(Float)
    write_bw_mb: Mapped[float | None] = mapped_column(Float)
    write_iops: Mapped[float | None] = mapped_column(Float)
    write_lat_us_mean: Mapped[float | None] = mapped_column(Float)
    write_lat_us_p50: Mapped[float | None] = mapped_column(Float)
    write_lat_us_p99: Mapped[float | None] = mapped_column(Float)
    write_lat_us_p999: Mapped[float | None] = mapped_column(Float)

    run: Mapped[Run] = relationship(back_populates="test_results")
    drive: Mapped[Drive] = relationship()
