"""Server-rendered HTML pages."""
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, distinct, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Drive, Machine, Run, TestResult
from app.slugs import drive_id_from_slug


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


# Tests featured on the leaderboard, with the direction that makes
# "best" the front of the list. Latency tests prefer LOW values.
LEADERBOARDS: list[tuple[str, str, str]] = [
    ("Sequential Read 1M", "MB/s", "desc"),
    ("Sequential Write 1M", "MB/s", "desc"),
    ("Random Read 4K QD32", "IOPS", "desc"),
    ("Random Write 4K QD32", "IOPS", "desc"),
    ("Latency: 4K Read QD1", "µs (lower better)", "asc"),
    ("Latency: 4K Write QD1", "µs (lower better)", "asc"),
]


def _latest_run_ids_subq(db: Session):
    """Returns a subquery yielding the latest run id per machine.
    Used to enforce 'one entry per machine' on the leaderboard."""
    return (
        select(
            Run.id,
            func.row_number().over(partition_by=Run.machine_id, order_by=desc(Run.ts)).label("rn"),
        )
        .subquery()
    )


def _leaderboard(db: Session, test_name: str, direction: str, limit: int = 10) -> list[dict]:
    latest = _latest_run_ids_subq(db)
    order_col = TestResult.primary_value if direction == "desc" else TestResult.primary_value
    order_clause = order_col.desc() if direction == "desc" else order_col.asc()

    stmt = (
        select(
            TestResult.primary_value,
            TestResult.primary_unit,
            Machine.slug.label("machine_slug"),
            Machine.machine_name,
            Machine.machine_model,
            Machine.chip_type,
            Drive.id.label("drive_id"),
            Drive.media_name,
            Drive.enclosure_name,
            Drive.internal,
            Run.slug.label("run_slug"),
        )
        .join(Run, TestResult.run_id == Run.id)
        .join(Machine, Run.machine_id == Machine.id)
        .join(Drive, TestResult.drive_id == Drive.id)
        .join(latest, (latest.c.id == Run.id) & (latest.c.rn == 1))
        .where(TestResult.test_name == test_name)
        .order_by(order_clause)
        .limit(limit)
    )
    rows = []
    for row in db.execute(stmt):
        m = dict(row._mapping)
        from app.slugs import drive_slug
        m["drive_slug"] = drive_slug(m["drive_id"])
        rows.append(m)
    return rows


def _browse_data(
    db: Session,
    chip: str | None, model: str | None, enclosure: str | None, internal: str | None,
) -> dict:
    stmt = select(Drive, Machine).join(Machine, Drive.machine_id == Machine.id)
    if chip:
        stmt = stmt.where(Machine.chip_type == chip)
    if model:
        stmt = stmt.where(Machine.machine_model == model)
    if enclosure:
        stmt = stmt.where(Drive.enclosure_name == enclosure)
    if internal == "yes":
        stmt = stmt.where(Drive.internal.is_(True))
    elif internal == "no":
        stmt = stmt.where(Drive.internal.is_(False))
    stmt = stmt.order_by(Machine.machine_model, Drive.media_name)
    rows = db.execute(stmt).all()

    chips = sorted({c for c, in db.execute(select(distinct(Machine.chip_type))) if c})
    models = sorted({m for m, in db.execute(select(distinct(Machine.machine_model))) if m})
    enclosures = sorted({e for e, in db.execute(select(distinct(Drive.enclosure_name))) if e})

    return {
        "rows": rows,
        "chips": chips, "models": models, "enclosures": enclosures,
        "filters": {"chip": chip, "model": model, "enclosure": enclosure, "internal": internal},
    }


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    chip: str | None = None,
    model: str | None = None,
    enclosure: str | None = None,
    internal: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    boards = []
    for name, label, direction in LEADERBOARDS:
        boards.append({
            "test_name": name,
            "unit_label": label,
            "rows": _leaderboard(db, name, direction),
        })

    recent = db.execute(
        select(Run, Machine)
        .join(Machine, Run.machine_id == Machine.id)
        .options(selectinload(Run.drive_a), selectinload(Run.drive_b))
        .order_by(Run.ts.desc())
        .limit(10)
    ).all()

    counts = {
        "machines": db.scalar(select(func.count(Machine.id))) or 0,
        "runs": db.scalar(select(func.count(Run.id))) or 0,
        "drives": db.scalar(select(func.count(distinct(Drive.media_name)))) or 0,
    }

    return templates.TemplateResponse(
        request, "home.html",
        {
            "boards": boards, "recent": recent, "counts": counts,
            **_browse_data(db, chip, model, enclosure, internal),
        },
    )


@router.get("/machine/{slug}/", response_class=HTMLResponse)
def machine(slug: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    m = db.scalar(
        select(Machine)
        .where(Machine.slug == slug)
        .options(
            selectinload(Machine.drives),
            selectinload(Machine.runs).selectinload(Run.drive_a),
            selectinload(Machine.runs).selectinload(Run.drive_b),
        )
    )
    if m is None:
        raise HTTPException(404)
    runs = sorted(m.runs, key=lambda r: r.ts, reverse=True)
    return templates.TemplateResponse(
        request, "machine.html",
        {"machine": m, "runs": runs},
    )


@router.get("/run/{slug}/", response_class=HTMLResponse)
def run_detail(slug: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    r = db.scalar(
        select(Run)
        .where(Run.slug == slug)
        .options(
            selectinload(Run.machine),
            selectinload(Run.drive_a),
            selectinload(Run.drive_b),
            selectinload(Run.test_results).selectinload(TestResult.drive),
        )
    )
    if r is None:
        raise HTTPException(404)

    # Group test_results by test_name → {drive_label: TestResult}
    grouped: dict[str, dict[str, TestResult]] = defaultdict(dict)
    for tr in r.test_results:
        # Match drive_id back to a label
        if tr.drive_id == r.drive_a_id:
            grouped[tr.test_name]["a"] = tr
        elif r.drive_b_id and tr.drive_id == r.drive_b_id:
            grouped[tr.test_name]["b"] = tr

    # Stable ordering by category + name as the script defines them
    ordered: list[tuple[str, dict[str, TestResult]]] = []
    seen = set()
    for tr in r.test_results:
        if tr.test_name in seen:
            continue
        seen.add(tr.test_name)
        ordered.append((tr.test_name, grouped[tr.test_name]))

    return templates.TemplateResponse(
        request, "run.html",
        {"run": r, "tests": ordered},
    )


@router.get("/drive/{slug}/", response_class=HTMLResponse)
def drive_detail(slug: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    drive_id = drive_id_from_slug(slug)
    if drive_id is None:
        raise HTTPException(404)
    drive = db.scalar(
        select(Drive).where(Drive.id == drive_id).options(selectinload(Drive.machine))
    )
    if drive is None:
        raise HTTPException(404)

    # Latest TestResult per test for this drive — gives the "current" stats line.
    latest_run = db.scalar(
        select(Run.id)
        .join(TestResult, TestResult.run_id == Run.id)
        .where(TestResult.drive_id == drive.id)
        .order_by(Run.ts.desc())
        .limit(1)
    )
    latest_results: list[TestResult] = []
    if latest_run is not None:
        latest_results = list(db.scalars(
            select(TestResult)
            .where(TestResult.run_id == latest_run, TestResult.drive_id == drive.id)
        ))

    # All runs that involved this drive, newest first.
    runs_rows = db.execute(
        select(Run)
        .where(or_(Run.drive_a_id == drive.id, Run.drive_b_id == drive.id))
        .options(selectinload(Run.drive_a), selectinload(Run.drive_b))
        .order_by(Run.ts.desc())
    ).scalars().all()

    return templates.TemplateResponse(
        request, "drive.html",
        {"drive": drive, "latest_results": latest_results, "runs": runs_rows, "latest_run_id": latest_run},
    )


@router.get("/about/", response_class=HTMLResponse)
def about(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "about.html", {})
