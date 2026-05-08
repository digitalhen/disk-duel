"""POST /api/v1/runs/ — accepts the script's JSON payload."""
from datetime import datetime
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Drive, Machine, Run, TestResult
from app.schemas import DriveInfo, RunIn, RunOut, TestResultIn
from app.slugs import hash_serial, machine_slug, run_slug

router = APIRouter(prefix="/api/v1", tags=["api"])


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or x_api_key != settings.disk_duel_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")


def _upsert_machine(db: Session, payload: RunIn) -> Machine:
    """Find-or-create a machine row keyed by sha256(serial)."""
    h = payload.host
    sh = hash_serial(h.serial_number)
    m = db.scalar(select(Machine).where(Machine.serial_hash == sh))
    now = datetime.now()
    if m is None:
        m = Machine(
            serial_hash=sh,
            slug="",  # filled after flush so we have an id
            machine_name=h.machine_name,
            machine_model=h.machine_model,
            chip_type=h.chip_type,
            physical_memory=h.physical_memory,
            platform=h.platform,
            first_seen=now,
            last_seen=now,
        )
        db.add(m)
        db.flush()
        m.slug = machine_slug(m.id)
    else:
        # Refresh hardware fields if the client sees something newer.
        if h.machine_name:
            m.machine_name = h.machine_name
        if h.machine_model:
            m.machine_model = h.machine_model
        if h.chip_type:
            m.chip_type = h.chip_type
        if h.physical_memory:
            m.physical_memory = h.physical_memory
        m.last_seen = now
    return m


def _resolve_drives(
    db: Session, machine: Machine, payload: RunIn
) -> dict[str, Drive]:
    """Return a {label: Drive} map. Uses payload.drives metadata when
    present; falls back to a stub Drive keyed only by label for older
    script versions that don't ship drive details."""
    by_label: dict[str, DriveInfo] = {d.label: d for d in payload.drives}

    # Guarantee an entry exists for every label that appears in test data.
    labels = {tr.label for tr in payload.all_results}
    for lbl in labels:
        if lbl not in by_label:
            by_label[lbl] = DriveInfo(label=lbl, media_name=lbl)

    resolved: dict[str, Drive] = {}
    for lbl, info in by_label.items():
        media_name = info.media_name or lbl
        d = db.scalar(
            select(Drive).where(
                Drive.machine_id == machine.id,
                Drive.media_name == media_name,
            )
        )
        if d is None:
            d = Drive(
                machine_id=machine.id,
                device=info.device,
                media_name=media_name,
                bus_protocol=info.bus_protocol,
                internal=info.internal,
                solid_state=info.solid_state,
                size_gb=info.size_gb,
                enclosure_name=info.enclosure_name,
                enclosure_vendor=info.enclosure_vendor,
            )
            db.add(d)
            db.flush()
        else:
            # Update sparse fields if the client now has data we lacked.
            d.device = info.device or d.device
            d.bus_protocol = info.bus_protocol or d.bus_protocol
            if info.size_gb:
                d.size_gb = info.size_gb
            d.enclosure_name = info.enclosure_name or d.enclosure_name
            d.enclosure_vendor = info.enclosure_vendor or d.enclosure_vendor
        resolved[lbl] = d
    return resolved


def _insert_test_results(
    db: Session, run: Run, drives: dict[str, Drive], rows: list[TestResultIn]
) -> None:
    for r in rows:
        d = drives.get(r.label)
        if d is None:
            continue
        db.add(TestResult(
            run_id=run.id,
            drive_id=d.id,
            test_name=r.test_name,
            category=r.category,
            primary_unit=r.primary_unit or "",
            primary_value=r.primary_value or 0.0,
            read_bw_mb=r.read_bw_mb,
            read_iops=r.read_iops,
            read_lat_us_mean=r.read_lat_us_mean,
            read_lat_us_p50=r.read_lat_us_p50,
            read_lat_us_p99=r.read_lat_us_p99,
            read_lat_us_p999=r.read_lat_us_p999,
            write_bw_mb=r.write_bw_mb,
            write_iops=r.write_iops,
            write_lat_us_mean=r.write_lat_us_mean,
            write_lat_us_p50=r.write_lat_us_p50,
            write_lat_us_p99=r.write_lat_us_p99,
            write_lat_us_p999=r.write_lat_us_p999,
        ))


@router.post("/runs/", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def submit_run(
    payload: RunIn,
    _: None = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> RunOut:
    machine = _upsert_machine(db, payload)
    drives = _resolve_drives(db, machine, payload)

    # In dual mode, labels[0/1] identify which drives were A/B; in solo it's
    # `label`. Fall back to the first/second key of `drives` if needed.
    if payload.mode == "dual":
        a = payload.labels[0] if payload.labels else next(iter(drives))
        b = payload.labels[1] if payload.labels and len(payload.labels) > 1 else None
    else:
        a = payload.label or (payload.labels[0] if payload.labels else next(iter(drives)))
        b = None

    drive_a = drives.get(a)
    drive_b = drives.get(b) if b else None
    if drive_a is None:
        raise HTTPException(status_code=400, detail=f"label {a!r} has no drive entry")

    run = Run(
        machine_id=machine.id,
        slug="",
        mode=payload.mode,
        ts=datetime.fromisoformat(payload.timestamp),
        drive_a_id=drive_a.id,
        drive_b_id=drive_b.id if drive_b else None,
        label_a=a,
        label_b=b,
        quick=payload.quick,
        size_multiplier=payload.size_multiplier,
        script_version=payload.script_version,
        raw_payload=payload.model_dump(mode="json"),
    )
    db.add(run)
    db.flush()
    run.slug = run_slug(run.id)

    _insert_test_results(db, run, drives, payload.all_results)
    db.commit()

    base = settings.public_base_url.rstrip("/") + (settings.root_path or "")
    return RunOut(
        run_slug=run.slug,
        machine_slug=machine.slug,
        run_url=f"{base}/run/{run.slug}/",
        machine_url=f"{base}/machine/{machine.slug}/",
    )
