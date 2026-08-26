# Municipal WebGIS Platform — Project Outline

## Architecture at a Glance

```
  Browser
    │  GET/POST
    ▼
┌───────────┐   proxy_pass    ┌──────────────────┐   proxy_pass   ┌──────────────────┐
│   nginx   │──/api/────────▶│   Django (gunicorn) │◀──DB──▶│  PostgreSQL/PostGIS │
│  gateway  │──/api/import/─▶│   :8000 / 443    │              │  :5432  (webgis)  │
│  :80/:443 │──/tiles/──────▶│   REST API + Admin│              └──────────────────┘
│           │──/              │                  │                      ▲
└───────────┘  (static SPA)  └──────────────────┘                      │
      │                              ▲                                 │
      │    filesystem broker         │     filesystem broker           │
      │   ┌──────────────┐    enqueue ┌──────────────────┐            │
      │   │ data_out/    │◀──────────│   Import Service  │            │
      │   │ (kombu)      │─────▶────▶│   FastAPI         │            │
      │   └──────────────┘           │   :8001           │            │
      │              ▲               │  (file + JWT)     │            │
      │              │               └──────────────────┘            │
      │         Celery Worker                                        │
      │         (solo, redis)                                        │
      │              │                                                │
      │              │ tasks: DXF parse, tiling                      │
      │              └──── writes staging rows ─────────────────────▶│
      │                         APPROVE merges staging → production ─▶│
      │                                                               │
      ▼                                                               │
┌─────────────┐                                                       │
│  Next.js    │                                                       │
│  SPA        │                                                       │
│  :3000      │                                                       │
└─────────────┘                                                       │
```

All five processes live on the same host; broker uses `kombu` **filesystem transport** (no Redis required locally for the sync loop; Redis is used for production and still recommended).

---

## Component Inventory

| Service | Framework | Port | Purpose |
|---------|-----------|------|---------|
| Django backend | Django 5.2 / GeoDjango / DRF | 8000 | Auth, models, REST API, approval, admin console |
| Import service | FastAPI | 8001 | File upload endpoint, JWT verification, Celery dispatch |
| Celery worker | Celery 5.x, solo pool | — | Background DXF parsing + GeoTIFF tiling |
| Next.js frontend | Next.js 14 | 3000 (dev) | Map portal, dashboard, search UI |
| nginx | nginx | 80/443 | Reverse proxy, static assets, tile serving |

---

## Database Schema

### Production tables (`gis_app`)

| Table | Purpose |
|-------|---------|
| `gis_app_facilitycategory` | FK lookup — Mosque, Clinic, School, Council Office, Port / Harbour, Power House (seeded by `seed_data`, auto-created by migration 0004 on legacy DBs) |
| `gis_app_road` | Approved roads (`road_name`, `road_code`, `road_class`, `status`, PostGIS geometry 32643) |
| `gis_app_building` | Approved buildings (polygon geometry, `building_code`, `house_name`) |
| `gis_app_facility` | Approved facilities (`category` FK → `FacilityCategory`, `category_old` legacy varchar preserved, `asset_code`, `geometry`) |
| `gis_app_landusezone` | Approved land-use polygons (`zone_name`, `zone_type`) |
| Utility tables | `street_light`, `water_line`, `water_node`, `sewer_line`, `manhole`, `sewer_junction`, `electrical_line`, `electrical_node`, `fiber_line`, `fiber_node` — all with `asset_code` + geometry |

### Staging tables (mirrors of production)

Every production model above has a `gis_app_staging*` counterpart carrying the same fields plus `session_id` FK → `SurveySession`. Staging rows are reviewed, then merged transactionally during approval.

### Workflow tables

| Table | Purpose |
|-------|---------|
| `gis_app_surveysession` | Upload session (`session_type`: SURVEY / IMAGERY, `status`: QUEUED → PROCESSING → COMPLETED / ERROR) |
| `gis_app_approvalhistory` | One row per approval (session, user, timestamp, comments) |
| `gis_app_auditlog` | Append-only audit trail for all merges |

### Key migrations

| Migration | What it does |
|-----------|-------------|
| `0001_initial` – `0003` | Base models, survey session fields |
| `0004` | Creates `FacilityCategory`, renames legacy `category` varchar → `category_old`, adds FK + self-healing RunPython that seeds categories and auto-links legacy strings |
| `0005` | `CREATE EXTENSION pg_trgm` (required by combined search view) |

---

## Backend (Django) — Key Modules

### `gis_app/services.py` (shared approval layer)

Single source of truth used by four call-sites:

```python
merge_session_to_production(session, user)   # @transaction.atomic
approve_session(session, user, comments)      # validates status, writes AuditLog + ApprovalHistory
clear_staging(session)
```

Consumed by:
1. **DRF view** (`views.py` → `POST /api/survey-sessions/{id}/approve/`)
2. **Django admin action** (`admin.py` → `approve_sessions` bulk action)
3. **Management command** `approve_session <id> --comments "..."`
4. **Management command** `approve_all`

### `gis_app/views.py`

| Endpoint | Auth | Method | Description |
|----------|------|--------|-------------|
| `/api/auth/token/` | public | POST | JWT login (`username`, `password`) → `access` + `refresh` |
| `/api/auth/token/verify/` | public | POST | Validate JWT |
| `/api/facilities/` | optional | GET | Paginated facilities list |
| `/api/survey-sessions/` | admin | GET | List upload sessions |
| `/api/survey-sessions/{id}/` | admin | GET | Session detail |
| `/api/survey-sessions/{id}/staged/` | admin | GET | Staged rows grouped by layer type (buildings, roads, land_use, facilities, 10 utility categories) |
| `/api/survey-sessions/{id}/approve/` | admin | POST | Merge session to production |
| `/api/survey-sessions/{id}/reject/` | admin | POST | Mark as REJECTED |
| `/api/search/?q=<query>` | public | GET | Combined search across facilities (name + category via `TrigramSimilarity`), roads, buildings, land use — with PostGIS proximity fallback |
| `/api/roads/`, `/api/buildings/` etc. | varies | GET | Layer-specific APIs |
| `/admin/` | staff | — | Full Django admin with custom `StagingFacilityAdmin`, `FacilityCategoryAdmin`, bulk approval action |

### `gis_app/serializers.py`

`FacilitySerializer` and `StagingFacilitySerializer` expose `category` as a `SerializerMethodField` returning the FK name (or legacy `category_old` string if FK is null) — keeping the old API shape for the frontend while storing clean FKs in the database.

### `gis_app/tasks.py`

| Task | Trigger | Actions |
|------|---------|---------|
| `process_survey_import(session_id, filepath)` | Celery task from import service | Parses DXF via `ezdxf` → extracts POINT/LINE/LWPOLYLINE entities → creates staging rows for every detected layer → auto-detects CRS (UTM 43N default; WGS84 for point-only/$LIMMIN-degree files) → creates facility categories automatically by layer name code matching → sets session status COMPLETED |
| `process_orthophoto_import(session_id, filepath)` | Celery task from import service | Tiles GeoTIFF via GDAL CLI (if available) or pure-Python rasterio+Pillow XYZ fallback → writes PNG tiles to `TILES_DIR/<session_id>/<z>/<x>/<y>.png` → sets session status COMPLETED (auto-approved for imagery) |

CRS detection rules:
- Default: `EPSG:32643` (UTM Zone 43N — Maldives projection)
- Switches to `EPSG:4326` when all entities are POINTs **and** coordinates look like decimal degrees (`$LIMMIN` / average < 10,000)

Layer parsing:
- `BUILDING` / `LAND_USE` / `ROAD` / `FACILITY_<CATEGORY>` / `SL` (street lights) / `WATER_LINE` / `WATER_NODE` / `SEWER_LINE` / `MANHOLE` / `SEWER_JUNCTION` / `ELECTRICAL_LINE` / `ELECTRICAL_NODE` / `FIBER_LINE` / `FIBER_NODE`
- `LWPOLYLINE` with `closed=True` → polygon
- Category auto-detection: `FacilityCategory.code` (uppercase) substring of `layer_name.upper()`

### `gis_app/tile_pipeline.py`

Layered tiling strategy (same for both codepaths):
1. **CLI path** (production Linux): `gdaladdo` → `gdal_translate COG` → `gdal2tiles.py` XYZ
2. **Pure-Python fallback** (Windows/local): `rasterio.open` → `rasterio.warp.reproject` → `PIL.Image.save` per tile — triggered when CLI binaries are absent (`_gdal_cli_available()` guard)

### `gis_app/admin.py`

- `StagingFacilityAdmin`: list display `asset_code`, `name`, `category_old`, `updated_at`; approval via bulk action
- `FacilityCategoryAdmin`: list display `name`, `code`, `color`, `icon`, `is_active`; searchable + sortable
- `RoadAdmin`, `BuildingAdmin`: standard with geometry display

---

## Import Service (FastAPI)

`import_service/main.py` — runs under uvicorn.

| Route | Auth | Description |
|-------|------|-------------|
| `GET /health/` | none | `{"status":"healthy","service":"import_service","celery":true/false}` |
| `POST /import/` | Bearer JWT | Accepts multipart `file` + `notes`; infers `session_type` from extension (`.dxf` → SURVEY, `.tif/.tiff` → IMAGERY); writes file to `UPLOADS_DIR`; creates `SurveySession` row via direct psycopg2; enqueues Celery task via `send_task` |
| `GET /docs` | none | FastAPI Swagger UI |

Key behaviors:
- `DATABASE_URL` is normalized from `postgis://` → `postgresql://` before `psycopg2.connect()` (psycopg2 does not accept PostGIS scheme URIs)
- Celery app instantiated with `broker=REDIS_URL` only (no `backend=` — task results are persisted by the tasks themselves via Django ORM)
- Import-time ping to Celery was removed (redundant; `send_task` fails loudly if broker is down)

---

## Frontend (Next.js)

Unmodified during this work. Key routing contracts consumed by the backend:

| Path | Purpose |
|------|---------|
| `/` | Interactive map portal (Mapbox GL / Leaflet) |
| `/approval` | Admin approval dashboard (list sessions, review staged layers, approve/reject) |
| `/admin` | Django admin console (served by nginx) |

Gateway routing assumptions in nginx:
- `/api/import/import/` — trailing slash required (FastAPI route)
- `/tiles/{session_id}/{z}/{x}/{y}.png` — XYZ tile path
- `/api/search/?q=` — text + proximity search

---

## Authentication & Authorisation

### JWT flow
```
POST /api/auth/token/  {username, password}
  → {"access": "<jwt>", "refresh": "<jwt>"}

All protected requests:  Authorization: Bearer <access>
```

The import service validates JWTs by calling `POST {BACKEND_URL}/api/auth/token/verify/` with the token — no local secret needed.

### Role matrix (seeded by `seed_data`)

| Role | Group | Capabilities |
|------|-------|-------------|
| Guest | — | View production layers, search |
| Registered User | Registered User | + utility layers |
| Council Staff | Council Staff | + update addresses, edit metadata |
| Super Admin | Super Admin | + upload, approve, draw/edit geometries |

Groups: `Super Admin`, `Section Admin`, `Council Staff`, `Registered User`; permission `can_upload_data` attached to Super Admin.

---

## Deployment (Production Linux)

### File layout on `192.168.150.33`

```
/opt/webgis/
├── backend/             # Django project
│   ├── .venv/           # Python 3.10 venv
│   ├── gis_app/         # Core application
│   ├── gis_project/     # Django settings/celery config
│   ├── staticfiles/     # collectstatic output
│   └── .env             # DATABASE_URL, SECRET_KEY, DEBUG=False, ALLOWED_HOSTS
├── import_service/      # FastAPI project
│   ├── .venv/           # Python 3.11 venv
│   ├── main.py
│   └── .env             # REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND, BACKEND_URL, UPLOADS_DIR
├── frontend/            # Next.js build output
├── uploads/             # Uploaded DXF/TIFF files
├── tiles/               # Generated XYZ tiles
├── db/                  # init.sql (postgis + pg_trgm extensions)
├── deploy/systemd/      # Unit files
├── nginx.conf           # Gateway config
└── archive/             # Moved legacy files
```

### systemd units

| Unit | ExecStart | Notes |
|------|-----------|-------|
| `webgis-backend.service` | gunicorn on 127.0.0.1:8000 | GeoDjango requires GEOS_LIBRARY_PATH, GDAL_LIBRARY_PATH in env |
| `webgis-worker.service` | `celery -A gis_project worker --loglevel=info` | Solo pool; filesystem broker URL via `REDIS_URL` |
| `webgis-import.service` | `uvicorn main:app --host 0.0.0.0 --port 8001` | Dies with SIGILL if numpy 2.4+ (Pentium E6700 CPU without SSE4.2); requires `async-timeout` for redis 8 |
| `webgis-frontend.service` | Next.js production server | Port 3000, proxied by nginx |

### nginx routing

```nginx
location /tiles/          alias /opt/webgis/tiles/;
location /api/import/     proxy_pass http://127.0.0.1:8001/api/import/;   # trailing slash
location /api/            proxy_pass http://127.0.0.1:8000/api/;
location /admin/          proxy_pass http://127.0.0.1:8000/admin/;
location /                proxy_pass http://127.0.0.1:3000/;               # Next.js SPA
```

Also includes WebSocket upgrade headers for the frontend, CORS headers, and `/sms` passthrough (external SMS gateway).

---

## Local Development (Windows, portable stack)

Everything runs inside `C:\Users\<you>\webgis-stack\` (NOT `%TEMP%` — temp directories are periodically wiped and will destroy the Postgres cluster, venv, and tile output).

### Quick start (launcher scripts at stack root)

```cmd
run_pg.cmd          # PostgreSQL 17 + PostGIS 3.6 on port 5544
run_django.cmd      # Django dev server on 127.0.0.1:8000
run_worker.cmd      # Celery worker (filesystem broker)
run_import.cmd      # FastAPI import service on 127.0.0.1:8001
```

All launchers share a common pattern:
- `cd /d ...\pgtest\broker` — ensures kombu filesystem broker writes relative paths into the junctioned mailbox
- `PYTHONPATH` includes both backend and import_service as needed
- `GDAL_DATA` and `PROJ_LIB` point at rasterio's bundled data directories (otherwise transforms fail with `Cannot find proj.db`)
- `PYTHONIOENCODING=utf-8` prevents cp1252 UnicodeEncodeError on emoji output
- `DJANGO_SETTINGS_MODULE=gis_project.settings` — required because `main.py` imports `django.contrib.gis.geos` at module level

### Broker mailbox layout

```
pgtest/broker/
├── data_out/    ← Celery worker reads from here
├── data_in/     → Junction to data_out (producer writes to data_out)
├── control/     ← Celery control queue (ping, shutdown)
└── processed/   ← Kombu ack markers
```

### Autostart (Windows Startup folder)

`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\webgis_stack.cmd` calls `start_stack.cmd` which idempotently checks ports (5544, 8000, 8001) and celery process presence before starting each service.

---

## E2E Verification Harness

`C:\Users\<you>\webgis-stack\harness.py` — 22 checks covering the full import → approve → search flow.

| Check | What it validates |
|-------|-------------------|
| Import service health | `GET /health/` + `celery: true` |
| JWT login | `POST /api/auth/token/` with seeded admin credentials |
| Upload DXF (UTM 43N) | `POST /import/` returns 201 + `survey_session_id` |
| Broker round-trip | Poll session status until `COMPLETED` |
| Staged counts | Buildings=2, roads=1, land_use=1, facilities=1, utilities=11 |
| Facility category | Auto-detected as `Mosque` from `FACILITY_MOSQUE` layer |
| Approve endpoint | `POST /api/survey-sessions/{id}/approve/` returns 200 |
| Production growth | Roads +1, buildings +2, facilities +1 after merge |
| Facility category API | Serialized `category` name matches `Mosque` |
| Combined search | `GET /api/search/?q=Masjid` returns facility text match |
| WGS84 DXF variant | Upload with degree-coords auto-detected and completed |
| GeoTIFF upload | `POST /import/` with `.tif` → COMPLETED + tile directory populated |
| XYZ tiles generated | At least 5 PNG tiles produced by rasterio fallback |
| Broker drained | No pending `.msg` files (ignoring celery pidbox replies) |

Run locally: `venv\Scripts\python.exe harness.py`

---

## Secret Management

| Item | Where stored | Where NOT stored |
|------|-------------|------------------|
| Linux login (nci-server) | Password manager only | Not in repo, not in any server file |
| Postgres `postgres` role password | Password manager only; both `.env` files updated | Repo scrubbed; old value grep-verified 0 hits |
| Redis requirepass | Both `.env` files; `/etc/redis/redis.conf` (backup at `/root/redis.conf.bak.*`) | Not in repo or docs |
| Django SECRET_KEY | Server `backend/.env` | Local dev uses insecure placeholder; server uses its own |
| Django `admin123` demo creds | `README.md` (documented, intentional) | N/A — not a real secret, per-project seed |

Rotation procedure (run on server):
```bash
# 1. Postgres
sudo -u postgres psql -c "ALTER ROLE postgres PASSWORD '<new>';"
sed -i "1s#.*#DATABASE_URL=postgresql://postgres:<new>@localhost:5432/webgisdb#" \
  /opt/webgis/backend/.env /opt/webgis/import_service/.env

# 2. Linux
echo "nci-server:<new>" | sudo chpasswd

# 3. Redis (if changing)
sudo sed -i "s/^requirepass .*/requirepass <new>/" /etc/redis/redis.conf
# Update REDIS_URL/CELERY_BROKER_URL in both .envs → redis://:<new>@localhost:6379/0

# 4. Restart
sudo systemctl restart webgis-backend webgis-worker webgis-import redis-server
```

---

## Backups & Code Mirror

| Asset | Method | Schedule | Retention |
|-------|--------|----------|-----------|
| PostgreSQL (`webgisdb`) | `pg_dump \| gzip` via `/etc/cron.d/webgis-backup` | Daily 02:30 UTC | 14 days |
| Code mirror | Bare git repo at `/root/webgis.git`; refreshed via bundle + fetch | On demand (per deploy) | All commits |

Refresh command:
```powershell
git bundle create webgis.bundle --all
pscp webgis.bundle nci-server@263-linuxserver:/tmp/
# on server: sudo git -C /root/webgis.git fetch /tmp/webgis.bundle "refs/*:refs/*"
```

---

## Known Hardware Constraints

The production server runs a **Pentium Dual-Core E6700** (Wolfdale, 2007) which lacks SSE4.2/POPCNT. This imposes:
- `numpy < 2.4` (OpenBLAS in newer builds emits instructions the CPU cannot execute → `SIGILL` / ILL illegal instruction crash)
- `async-timeout` must be present for redis-py 8 import chain on Python 3.11
- GDAL CLI tiling works; the pure-Python rasterio fallback also works

The import service previously crash-looped for days on this CPU before both constraints were identified and fixed. If migrating to newer hardware, the `numpy<2.4` ceiling can be lifted.

---

## Git History

| Commit | Hash | Content |
|--------|------|---------|
| Initial | `64ba3db` | Full platform: Django/GeoDjango, FastAPI import, Celery worker, Next.js frontend, nginx config, deploy units, seed data, e2e harness, README |
| Hardening | `a64ae1e` | Reproducible `requirements.txt` (python-dotenv, async-timeout, numpy<2.4), operations changelog in `modifications.md` |

Mirror: `a64ae1e` (head) at `/root/webgis.git` on `192.168.150.33`.

---

## Maintenance Commands Reference

```bash
# Server — restart services
sudo systemctl restart webgis-backend webgis-worker webgis-import
sudo systemctl status webgis-{backend,worker,import}

# Server — approve session via CLI
sudo -u webgis /opt/webgis/backend/.venv/bin/python manage.py approve_session <session_id> --comments "checked"
sudo -u webgis /opt/webgis/backend/.venv/bin/python manage.py approve_all

# Server — seed/reseed data (idempotent)
sudo -u webgis /opt/webgis/backend/.venv/bin/python manage.py seed_data

# Local — run e2e harness
venv\Scripts\python.exe C:\Users\<you>\webgis-stack\harness.py

# Local — manual DB operations (port 5544)
C:\Users\<you>\webgis-stack\pgtest\pgsql\bin\psql -h 127.0.0.1 -p 5544 -U postgres -d webgis

# Backups — manual dump
sudo -u postgres pg_dump webgisdb | gzip > /var/backups/webgis/manual-$(date +%F).sql.gz
```
