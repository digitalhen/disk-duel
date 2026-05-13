import hashlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import api, pages


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _static_version() -> str:
    """Hash of the static directory contents. Changes on every redeploy
    that touches CSS/JS, so the ?v=… query string busts CDN caches."""
    h = hashlib.sha1()
    for p in sorted(STATIC_DIR.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(STATIC_DIR).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


STATIC_VERSION = _static_version()
pages.templates.env.globals["static_version"] = STATIC_VERSION
# Absolute base for canonical / og:url tags. Strips trailing slash so the
# templates can do `canonical_base + request.url.path` cleanly.
pages.templates.env.globals["canonical_base"] = settings.public_base_url.rstrip("/")


app = FastAPI(
    title="Disk Duel",
    description="Public results portal for disk-duel benchmarks",
    root_path=settings.root_path,
)

app.include_router(pages.router)
app.include_router(api.router)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"ok": True}
