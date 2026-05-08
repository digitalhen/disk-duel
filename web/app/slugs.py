"""Stable opaque slugs derived from numeric IDs (so URLs don't leak counts
or sequential ordering). Two namespaces with disjoint salts keep machine
slugs and run slugs from collapsing into the same string accidentally."""
import hashlib

from hashids import Hashids

from app.config import settings


_machine_hashids = Hashids(salt=f"{settings.hashids_salt}:machine", min_length=8)
_run_hashids = Hashids(salt=f"{settings.hashids_salt}:run", min_length=8)


def machine_slug(machine_id: int) -> str:
    return _machine_hashids.encode(machine_id)


def run_slug(run_id: int) -> str:
    return _run_hashids.encode(run_id)


def hash_serial(serial: str | None) -> str:
    """Stable, irreversible identifier for a machine. Empty/missing serial
    falls back to a constant so anonymous uploads collapse into one bucket
    rather than spawning fresh machines on each call."""
    s = (serial or "").strip()
    if not s:
        return "anon-" + hashlib.sha256(b"anonymous").hexdigest()[:16]
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
