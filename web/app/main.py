from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import api, pages


app = FastAPI(
    title="Disk Duel",
    description="Public results portal for disk-duel benchmarks",
    root_path=settings.root_path,
)

app.include_router(pages.router)
app.include_router(api.router)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"ok": True}
