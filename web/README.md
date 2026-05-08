# Disk Duel — Web

Public leaderboard for Disk Duel benchmark runs. Sister project to the [`disk_duel.py`](../disk_duel.py) script.

- **API**: `POST /api/v1/runs/` accepts the script's JSON payload and returns public URLs.
- **Pages**: home (top-10 leaderboards), `/machine/<slug>/`, `/run/<slug>/`, `/browse/`, `/about/`.
- **Privacy**: serial numbers are hashed (`sha256`) before storage and never displayed. Public URLs use opaque `hashids` slugs.

## Stack

- Python 3.11, FastAPI, SQLAlchemy 2 (sync), psycopg 3 binary
- Jinja2 server-rendered templates; Chart.js for run comparison charts (CDN, no build step)
- Alembic for schema migrations
- Postgres on the shared instance (`$DB_HOST:5432`)

## Database setup

Connect to whatever Postgres instance you want to host the project-scoped DB.

1. As the `postgres` superuser, create the role + database:

   ```bash
   # Edit web/sql/01_bootstrap.sql, replace __REPLACE_ME__ with a strong password
   export DB_HOST=<your-pg-host>
   PGPASSWORD='<superuser-pw>' psql -h "$DB_HOST" -U postgres -f web/sql/01_bootstrap.sql
   ```

2. Create `web/.env` from `web/.env.example` and fill in:
   - `DATABASE_URL` — e.g. `postgresql+psycopg://diskduel:<pw>@$DB_HOST:5432/diskduel`
   - `HASHIDS_SALT` — `openssl rand -hex 16`. **Changing this invalidates every existing public URL.**
   - `ROOT_PATH` — `/disk-duel` in production, empty for local
   - `PUBLIC_BASE_URL` — base URL the API returns to the script
   - `DISK_DUEL_API_KEY` — *optional*; reserved for future admin endpoints, not used by the public submit path

3. Apply migrations:

   ```bash
   cd web
   python3 -m venv .venv && .venv/bin/pip install -e .
   .venv/bin/alembic upgrade head
   ```

## Run locally

```bash
cd web
.venv/bin/uvicorn app.main:app --reload --port 8000
# open http://localhost:8000/
```

Or via Docker:

```bash
cd web
docker compose up --build
```

## Submit a run from the script

```bash
export DISK_DUEL_UPLOAD_URL=http://localhost:8000/api/v1/runs/   # for local dev
python3 ../disk_duel.py --upload
```

The script does a proof-of-work hash before posting (`POW_DIFFICULTY_BITS = 20` by default) which the server verifies. There's no API key on the public submit endpoint — the script is open source so an embedded key would be theater. Spam protection is layered:

1. **Per-IP token bucket** in-process (`ip_limit_per_minute`, default 30/min)
2. **Per-`serial_hash` cooldown** in DB (`serial_cooldown_seconds`, default 60s)
3. **PoW verify** — `sha256("disk-duel:v1:{serial}:{timestamp}:{nonce}")` must have N leading zero bits

`DISK_DUEL_API_KEY` is reserved for future admin endpoints (delete a run, ban a serial, etc.) and isn't checked on the public submit path.

## Deployment

Built for Dokploy on studiomac (matches existing infra patterns):

1. New service from this repo, build context = `web/`.
2. Set the env vars from `.env.example` in Dokploy's UI (do **not** commit a real `.env`).
3. Reverse-proxy `apps.cleartextlabs.com/disk-duel/*` to the container's port 8000. The app is `root_path` aware, so set `ROOT_PATH=/disk-duel`.
4. Migrations run automatically on container start (`alembic upgrade head` is in the `CMD`).

## Schema

```
machines
  ├── id (pk)
  ├── serial_hash (sha256 of host serial — unique)
  ├── slug (hashids — public URL token)
  ├── machine_name, machine_model, chip_type, physical_memory, platform
  └── first_seen, last_seen

drives
  ├── id (pk)
  ├── machine_id (fk → machines)
  ├── media_name (e.g. "WD_BLACK SN850X 4000GB")
  ├── bus_protocol, internal, solid_state, size_gb
  ├── enclosure_name, enclosure_vendor
  └── unique (machine_id, media_name)

runs
  ├── id (pk)
  ├── machine_id (fk), slug (hashids)
  ├── mode ('solo' | 'dual'), ts
  ├── drive_a_id (fk → drives), drive_b_id (fk → drives, nullable)
  ├── label_a, label_b
  ├── quick, size_multiplier, script_version
  └── raw_payload (jsonb — full script output, kept for re-rendering)

test_results
  ├── id (pk), run_id (fk), drive_id (fk)
  ├── test_name, category, primary_unit, primary_value
  └── read_*/write_* (bw_mb, iops, lat_us_{mean,p50,p99,p999})
```

## Leaderboard rule

Latest run per machine. The query uses `ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY ts DESC)` to pick one row per machine before sorting by metric. This means re-running the script on the same machine replaces, rather than augments, that machine's standing — keeps rankings honest.

## Privacy

- Serial number is sha256'd in `_upsert_machine` and stored as `machines.serial_hash`. Raw serial is never persisted.
- Public URLs are hashids of the row id, with separate salts for machines vs runs (so the two namespaces can't collide).
- Hostname is intentionally optional and not surfaced in the UI.
- API auth is a single shared key rotated by changing `DISK_DUEL_API_KEY`.
