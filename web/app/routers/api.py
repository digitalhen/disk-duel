"""POST /api/v1/runs/ — accepts the script's JSON payload."""
import hashlib
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Drive, Machine, Run, TestResult
from app.schemas import DriveInfo, RunIn, RunOut, TestResultIn
from app.slugs import hash_serial, machine_slug, run_slug

router = APIRouter(prefix="/api/v1", tags=["api"])


# --- Anti-spam ---------------------------------------------------------------
# Three layers, ordered cheapest-first so an attacker pays the most expensive
# check (PoW) only after passing the free ones:
#   1. Per-IP token bucket (in-memory, free)
#   2. Per-serial_hash cooldown (one DB query)
#   3. Proof-of-work verify (one sha256)
# Cluster-wide IP limits should be added at the proxy/CDN layer too.

_ip_lock = threading.Lock()
_ip_buckets: dict[str, deque[float]] = defaultdict(deque)


def _has_leading_zero_bits(digest: bytes, bits: int) -> bool:
    full, partial = divmod(bits, 8)
    if any(b for b in digest[:full]):
        return False
    if partial == 0:
        return True
    return (digest[full] >> (8 - partial)) == 0


def _verify_pow(payload: RunIn) -> None:
    if payload.pow_nonce is None:
        raise HTTPException(400, detail="missing pow_nonce")
    if payload.pow_version != "v1":
        raise HTTPException(400, detail="unsupported pow_version")
    difficulty = settings.pow_difficulty_bits
    if (payload.pow_difficulty or 0) < difficulty:
        raise HTTPException(400, detail=f"pow_difficulty must be >= {difficulty}")

    # Freshness: payload.timestamp must be within ±5 minutes of server time,
    # otherwise a captured payload + valid PoW could be replayed forever.
    try:
        ts = datetime.fromisoformat(payload.timestamp)
    except ValueError:
        raise HTTPException(400, detail="invalid timestamp")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if abs((now - ts).total_seconds()) > 300:
        raise HTTPException(400, detail="timestamp not fresh (must be within 5 min)")

    serial = (payload.host.serial_number or "").strip()
    challenge = f"disk-duel:v1:{serial}:{payload.timestamp}:{payload.pow_nonce}"
    digest = hashlib.sha256(challenge.encode()).digest()
    if not _has_leading_zero_bits(digest, difficulty):
        raise HTTPException(400, detail="invalid proof of work")


def _check_ip_rate_limit(ip: str) -> None:
    now = time.monotonic()
    cutoff = now - 60.0
    with _ip_lock:
        bucket = _ip_buckets[ip]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= settings.ip_limit_per_minute:
            retry = int(60 - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=429,
                detail="rate limited",
                headers={"Retry-After": str(retry)},
            )
        bucket.append(now)


def _check_serial_cooldown(db: Session, serial_hash: str) -> None:
    cooldown = settings.serial_cooldown_seconds
    if cooldown <= 0:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown)
    machine = db.scalar(select(Machine).where(Machine.serial_hash == serial_hash))
    if machine is None:
        return
    last = db.scalar(
        select(Run.ts).where(Run.machine_id == machine.id).order_by(Run.ts.desc()).limit(1)
    )
    if last and last > cutoff:
        wait = int((last + timedelta(seconds=cooldown) - datetime.now(timezone.utc)).total_seconds()) + 1
        raise HTTPException(
            status_code=429,
            detail=f"machine on cooldown ({wait}s)",
            headers={"Retry-After": str(max(wait, 1))},
        )


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reserved for future admin-only endpoints (delete a run, ban a serial,
    etc.). The public submit endpoint is intentionally unauthenticated:
    the script is open source so embedded keys provide no real protection,
    and we'd rather control abuse via proxy-level rate limiting + payload
    sanity bounds than ship security theater. Keep this here so admin
    endpoints can `Depends(require_api_key)` when added."""
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
    provided; falls back to stubbing from all_results labels only when
    no drives field was supplied (older script versions). Test rows
    with labels that don't match any declared drive get silently
    dropped in _insert_test_results."""
    by_label: dict[str, DriveInfo] = {d.label: d for d in payload.drives}

    if not by_label:
        # Legacy payload: build stubs from whatever labels appear in tests.
        for tr in payload.all_results:
            if tr.label not in by_label:
                by_label[tr.label] = DriveInfo(label=tr.label, media_name=tr.label)

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
    request: Request,
    db: Session = Depends(get_db),
) -> RunOut:
    # Cheapest checks first, so a flooder pays most for the rejection.
    client_ip = request.client.host if request.client else "unknown"
    _check_ip_rate_limit(client_ip)
    serial_hash = hash_serial(payload.host.serial_number)
    _check_serial_cooldown(db, serial_hash)
    _verify_pow(payload)

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

    # Use server-side time, not client-supplied. Client clock is in
    # raw_payload if anyone wants it, but cooldown + ordering rely on this.
    run = Run(
        machine_id=machine.id,
        slug="",
        mode=payload.mode,
        ts=datetime.now(timezone.utc),
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
