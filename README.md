# Island GIS Web Application -- MVP

A production-grade municipal GIS platform designed for island-level mapping, daily survey ingestion, precise spatial measurements, and strict data lineage auditing. Runs directly on a Linux server/VPS (no Docker) with PostgreSQL/PostGIS, Redis, nginx, and systemd managing the application services.

## Architecture & Layout

```
├── db/                     # Database setup SQL (PostGIS + pg_trgm extensions)
├── backend/                # Django REST Framework API & Celery worker
│   └── gis_project/        # Django project configuration & settings
│   └── gis_app/            # Core models (buildings, roads, utilities, lineage)
├── frontend/               # Next.js (TypeScript + Leaflet + Tailwind CSS)
│   └── src/components/     # MapViewer, SearchBar, Ingestion dashboards
├── import_service/         # FastAPI import service (ezdxf + shapely + pyproj)
├── nginx.conf              # Reverse proxy gateway routing and static XYZ tile serving
├── deploy/systemd/         # systemd unit files for backend, worker, import, frontend
├── .env.example            # Environment variable template
└── README.md               # Setup & operation manual
```

## Technical Features

1. **Spatial Coordinate Reference System (CRS)**:
   - **Database Storage CRS**: **UTM Zone 43N (EPSG:32643)** (projected coordinate system in meters; optimal for accurate measurements of distance, area, buffer, and routing in the Maldives).
   - **Public API / Export CRS**: **WGS 84 (EPSG:4326)** (unprojected lat/lng, standard for GeoJSON outputs, reprojected on the fly by serializers).
   - **Visualization CRS**: **Web Mercator (EPSG:3857)** (used natively by Leaflet/MapLibre).
2. **Dedicated Import Service**:
   - Built on FastAPI. Files are processed asynchronously via a **Celery + Redis** background worker queue to handle heavy parsing tasks.
   - DXF geometries (Points, LineStrings, Polygons) are parsed, cleaned, and associated with text labels (like building house codes) using spatial indexes.
   - Every upload creates a `SurveySession` with a **session type**: `SURVEY` (DXF vector drawings, require manual approval) or `IMAGERY` (GeoTIFF drone orthophotos, auto-approved after tiling).
3. **Orthophoto Tile Pipeline**:
   - GeoTIFF uploads are tiled by the Celery worker (`process_orthophoto_import`) using GDAL (`gdaladdo` + `gdal_translate` COG conversion + `gdal2tiles.py --xyz`).
   - Tiles are written to `/opt/webgis/tiles/<session_id>` and served by nginx at `/tiles/<session_id>/{z}/{x}/{y}.png`; the map portal discovers the latest imagery via `GET /api/survey-sessions/latest-imagery/`.
3. **Staging & Approvals Workflow**:
   - Uploaded survey drawings write to `staging` tables.
   - Super Admins review staged layers overlaid on production maps and merge them transactionally via `/api/survey-sessions/{id}/approve/` which runs database upserts (updating existing asset codes, inserting new ones).
4. **Trigram & Proximity Search**:
   - Combines Postgres `pg_trgm` fuzzy text matching on names/codes and PostGIS-native distance checks.

---

## Server Requirements

- **OS**: Linux (Debian/Ubuntu recommended for the commands below)
- **PostgreSQL 15+** with the **PostGIS** extension (installed on the server, not containerized)
- **Redis 7+** (Celery broker)
- **nginx**
- **Python 3.11** + `venv`
- **Node.js 20+** + `npm`
- **GDAL/GEOS/PROJ system binaries** (GeoDjango requires these compiled libraries)

## Installation (Bare Metal / VPS)

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgis redis-server nginx \
    python3.11 python3.11-venv python3.11-dev \
    nodejs npm \
    binutils libproj-dev gdal-bin libgdal-dev gcc g++ libc-dev
```

### 2. Create the Database & Extensions

Start PostgreSQL and create the `webgis` database and user:

```bash
sudo systemctl enable --now postgresql redis-server
sudo -u postgres psql -c "CREATE USER postgres WITH PASSWORD 'postgres';"
sudo -u postgres psql -c "CREATE DATABASE webgis OWNER postgres;"
sudo -u postgres psql -d webgis -f /opt/webgis/db/init.sql
```

`db/init.sql` enables the `postgis` and `pg_trgm` extensions.

### 3. Prepare the Application Layout

```bash
sudo mkdir -p /opt/webgis/uploads /opt/webgis/tiles
sudo useradd --system --home /opt/webgis --shell /usr/sbin/nologin webgis
sudo chown -R webgis:webgis /opt/webgis
sudo cp -r backend import_service frontend db /opt/webgis/
```

### 4. Configure Environment Files

```bash
cp /opt/webgis/.env.example /opt/webgis/import_service/.env
sudo -u webgis nano /opt/webgis/backend/.env   # set DATABASE_URL, SECRET_KEY, DEBUG, ALLOWED_HOSTS
```

The import service reads `BACKEND_URL` and `UPLOADS_DIR` from its `.env`.

Django parses `DATABASE_URL` with [dj-database-url](https://pypi.org/project/dj-database-url/); use a `postgis://` scheme so the PostGIS engine is selected automatically, e.g. `postgis://user:password@host:5432/webgis`.

### 5. Install Python Dependencies

```bash
cd /opt/webgis/backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

cd /opt/webgis/import_service
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 6. Build the Frontend

```bash
cd /opt/webgis/frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost/api npm run build
```

`NEXT_PUBLIC_API_URL` is baked in at build time; set it to your public domain (e.g. `https://gis.example.com/api`) before building.

### 7. Run Migrations & Seed Data

```bash
cd /opt/webgis/backend
sudo -u webgis .venv/bin/python manage.py migrate
sudo -u webgis .venv/bin/python manage.py collectstatic --noinput
sudo -u webgis .venv/bin/python manage.py seed_data
```

`collectstatic` copies Django admin assets to `/opt/webgis/backend/static`, which nginx serves at `/static/` so the admin console at `/admin/` renders correctly.

### 8. Install systemd Services

```bash
sudo cp /opt/webgis/deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now webgis-backend webgis-worker webgis-import webgis-frontend
sudo systemctl status webgis-backend webgis-worker webgis-import webgis-frontend
```
cp /opt/webgis/.env.example /opt/webgis/backend/.env

The unit files run:
- `webgis-backend` -- gunicorn (Django REST API) on `127.0.0.1:8000`
- `webgis-worker` -- Celery worker consuming the import queue
- `webgis-import` -- uvicorn (FastAPI) on `127.0.0.1:8001`
- `webgis-frontend` -- Next.js production server on `127.0.0.1:3000`

### 9. Configure nginx

```bash
sudo cp /opt/webgis/nginx.conf /etc/nginx/nginx.conf
sudo nginx -t
sudo systemctl enable --now nginx
```

`nginx.conf` routes `/tiles/` from `/opt/webgis/tiles`, proxies `/api/import/` to the FastAPI service, `/api/` to Django, and everything else to the Next.js app.

### 10. Open the Web Application

Navigate to:
- **Interactive Map Portal**: `http://<server-ip>` (or your domain)
- **Django Admin Console**: `http://<server-ip>/admin/`
- **FastAPI Documentation**: `http://<server-ip>/api/import/docs`

---

## User Roles (Auth Demo Matrix)

To test the role-based permissions matrix, use the dropdown selector in the top-right header of the map portal. Alternatively, log in using the credentials seeded by `seed_data`:

| Username | Password | Role | Permissions |
| :--- | :--- | :--- | :--- |
| **Guest** | - | Guest (Public) | View-only core layers (roads, buildings, facilities), search |
| **Registered** | - | Registered User | View-only including utility network layers |
| **staff** | `staff123` | Council Staff | View layers, update addresses, and edit metadata attributes |
| **admin** | `admin123` | Super Admin | Full privileges, draw/edit geometries, upload surveys, merge approvals |

---

## Operations Notes

- **Uploaded DXF files** are stored in `UPLOADS_DIR` (`/opt/webgis/uploads` by default); the Celery worker reads them from the same path. GeoTIFF imagery is tiled into `/opt/webgis/tiles/<session_id>` per session.
- **Generated XYZ tiles** (drone orthophoto) are served by nginx at `/tiles/<session_id>/{z}/{x}/{y}.png`. Approvals are only required for `SURVEY` (DXF) sessions; `IMAGERY` sessions are auto-approved once tiling completes.
- **CLI approvals** mirror the admin action exactly (same transactional merge, audit trail and staging cleanup):
  ```bash
  sudo -u webgis .venv/bin/python manage.py approve_session <session_id> --comments "checked"
  sudo -u webgis .venv/bin/python manage.py approve_all            # every COMPLETED survey session
  ```
- `seed_data` also seeds the `FacilityCategory` lookup (Mosque, Clinic, School, Council Office, Port / Harbour, Power House); DXF facility layers whose name contains a category code (e.g. `FACILITY_MOSQUE`) are linked to it automatically on import.
- **Backups**: use `pg_dump` for the `webgis` database; the uploads and tiles directories are plain files you can snapshot with `rsync`.
- Set `DEBUG=False` and a strong `SECRET_KEY` in `backend/.env` for production.

---

## Local Development (Windows, portable PostGIS)

Everything in this stack can be run on a Windows workstation **without Docker/WSL and without admin rights** by keeping every component inside a user-writable directory **outside of any temp-cleaned path** (example: `C:\Users\<you>\webgis-stack` — directories under `%TEMP%` are periodically wiped by cleanup tools and will destroy the database cluster and venv). This is how the migrate/seed steps and the end-to-end import → approve → tiling flow are exercised before deploying to the VPS.

1. **Portable PostgreSQL + PostGIS** (system services may already own ports 5432/5433, so use 5544):
   - Download the EDB PostgreSQL 17 binaries zip and the matching `postgis-bundle-pg17-*x64` zip, extract the former, then merge the bundle's `bin/lib/share/utils/gdal-data` into it.
   - Initialize a data dir and start the server detached (Task Scheduler keeps it alive independently of the shell):
     ```cmd
     pgsql\bin\initdb -D data -U postgres -A trust --encoding=UTF8 --no-locale
     schtasks /create /tn webgis_pg /tr "%~dp0start_pg.cmd" /sc once /st 00:00 /f
     schtasks /run /tn webgis_pg
     pgsql\bin\pg_isready -h 127.0.0.1 -p 5544
     ```
     `start_pg.cmd` runs `pgsql\bin\pg_ctl -D data -o "-p 5544" -l pg.log start`.
   - Create the database and extensions:
     ```
     createdb -h 127.0.0.1 -p 5544 -U postgres webgis
     psql -h 127.0.0.1 -p 5544 -U postgres -d webgis -f E:\DEV\webgis\db\init.sql
     ```
2. **Python**: create a 3.12 venv (`python -m venv .venv`) and install `backend/requirements.txt`. For the import service add `fastapi uvicorn python-multipart httpx requests` if you run it locally.
3. **GDAL CLIs** (*optional*): `gis_app.tile_pipeline` uses `gdaladdo` / `gdal_translate` / `gdal2tiles.py` when present on `PATH`, and otherwise falls back to a pure-Python XYZ tiler built on `rasterio` + `Pillow` (`pip install rasterio pillow numpy`). The CLI path is what the production server uses; the fallback exists so a workstation needs no external GDAL install.
4. **GeoDjango shared libraries**: PyPI ships no GDAL wheel for cp312+Windows, so point GeoDjango at the GDAL/GEOS DLLs bundled inside the `rasterio` wheel, and set `GDAL_DATA`/`PROJ_LIB` to rasterio's bundled data directories (otherwise every coordinate transform fails with `Cannot find proj.db`):
   ```powershell
   $env:GDAL_LIBRARY_PATH = "...\venv\Lib\site-packages\rasterio.libs\gdal-*.dll"
   $env:GEOS_LIBRARY_PATH = "...\venv\Lib\site-packages\rasterio.libs\geos_c-*.dll"
   $env:GDAL_DATA         = "...\venv\Lib\site-packages\rasterio\gdal_data"
   $env:PROJ_LIB          = "...\venv\Lib\site-packages\rasterio\proj_data"
   ```
5. **Database URL**: one `DATABASE_URL=postgis://postgres:postgres@127.0.0.1:5544/webgis` serves both sides — Django's `env.db` reads it natively, and the import service normalises the scheme to `postgresql://` before handing it to `psycopg2`.
6. **Run the stack**:
   ```powershell
   cd E:\DEV\webgis\backend
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py seed_data
   python manage.py runserver 127.0.0.1:8000
   ```
   Then start the import service (`uvicorn main:app --port 8001`) and a Celery worker. If no Redis is available locally, drive the two task bodies (`gis_app.tasks.process_survey_import` / `process_orthophoto_import`) directly — they are plain callables that write real rows to the same PostGIS database.
7. **Full async broker round-trip without Redis** (kombu filesystem transport): the import service and the worker agree on a shared mailbox directory.
   - Kombu's naming is counter-intuitive: the **producer writes to `data_folder_out`** and the **consumer reads from `data_folder_in`** (both default to CWD-relative `data_in`/`data_out` and must pre-exist). Point both sides at one mailbox by making the worker's `data_in` a junction to `data_out`:
     ```cmd
     mkdir broker\data_out broker\processed broker\control
     mklink /J broker\data_in broker\data_out
     ```
   - Run both processes with `cd /d ...\broker`, `REDIS_URL=filesystem://`, `PYTHONPATH=E:\DEV\webgis\backend` (worker) or `E:\DEV\webgis;E:\DEV\webgis\import_service` (import service), plus the GDAL env above. Launch each through a scheduled task whose `.cmd` uses `start "title" /min cmd /c ""...python.exe" ... >> log 2>&1"` — starting the server in a *new console* makes it survive the parent shell being terminated (otherwise the shell's job object Ctrl+C-kills it within a minute). Then:
     ```cmd
     schtasks /create /tn webgis_worker /tr "run_worker.cmd" /sc once /st 00:00 /f
     schtasks /run /tn webgis_worker
     ```
     A `POST /import/` should now show `status: QUEUED`, and the worker log shows the task consumed and completed; `GET /import/status/{id}` then returns `COMPLETED` with staged counts.
