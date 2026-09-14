# WebGIS — Deployment Guide (Ubuntu / Linux Server)

Runbook for installing and operating this stack on a bare-metal Ubuntu server
per the production system (`263-linuxserver`, `192.168.150.33`). It supersedes
the condensed install steps in `README.md` and documents the state of the
system as actually verified in production (Sprint 1–7).

> The application does **not** use Docker. Each component runs as a plain
> systemd service against system-installed PostgreSQL/PostGIS, Redis, nginx,
> Node and a Python venv.

---

## 1. Verified reference environment

This table is the environment measured on the production server. It is the
supported baseline for the guide.

| Component | Version (verified) | Notes |
|-----------|--------------------|-------|
| OS | **Ubuntu 22.04.5 LTS** | any 20.04/22.04 LTS is fine |
| PostgreSQL | **14.24** (package) | install together with `postgresql-14-postgis-3` |
| PostGIS | **3.x** | enabled via `db/init.sql` |
| Redis | **6.0.16** (package) | Celery broker (`redis://localhost:6379/0`) |
| nginx | **1.18.0** (package) | reverse proxy (supplied `nginx.conf`) |
| Node.js | **v24.20.0** | Next.js 16 requires Node ≥ 20 |
| Python | **3.11** | `python3.11` (deadsnakes PPA) + `venv` |
| GDAL | **3.4.1** | GeoDjango + orthophoto tiling (`gdal-bin`, `libgdal-dev`) |
| GEOS / PROJ | distro default | via `libgeos-dev`, `libproj-dev` |

Backend Python libs as pinned in `backend/requirements.txt` (Django 5.x, DRF,
SimpleJWT, Celery 5.x, gunicorn). Import service per `import_service/requirements.txt`
(FastAPI, uvicorn, ezdxf, shapely, pyproj). **Important:** import-service pins
`numpy>=2.0,<2.4` — numpy 2.4+ ships an OpenBLAS build that raises SIGILL on
pre-SSE4.2 CPUs (observed on the production box). Do not bump it.

---

## 2. Architecture & service map

```
Browser ─▶ nginx (80)
            ├─ /static/        ▶ /opt/webgis/backend/staticfiles   (Django admin assets)
            ├─ /tiles/         ▶ /opt/webgis/tiles/<session>/...   (orthophoto XYZ)
            ├─ /api/import/    ▶ 127.0.0.1:8001  FastAPI import service (uvicorn)
            ├─ /api/           ▶ 127.0.0.1:8000  Django API (gunicorn, 3 workers)
            ├─ /admin/         ▶ 127.0.0.1:8000  Django admin
            └─ /               ▶ 127.0.0.1:3000  Next.js frontend (`next start`)
```

| systemd unit | Service | Bind | Working dir | Venv |
|--------------|---------|------|-------------|------|
| `webgis-backend` | gunicorn `gis_project.wsgi` | `127.0.0.1:8000` | `/opt/webgis/backend` | `/opt/webgis/backend/.venv` |
| `webgis-worker` | celery `gis_project worker` | – (Redis broker) | `/opt/webgis/backend` | same |
| `webgis-import` | uvicorn `main:app` | `127.0.0.1:8001` | `/opt/webgis/import_service` | `/opt/webgis/import_service/.venv` |
| `webgis-frontend` | `next start -p 3000` | `0.0.0.0:3000` | `/opt/webgis/frontend` | npm (`node_modules`) |

Layout under `/opt/webgis/`:

```
/opt/webgis/
├── backend/            # Django project + Celery app (git-tracked source)
│   ├── .env            # DATABASE_URL, SECRET_KEY, DEBUG, REDIS_URL, ...
│   ├── staticfiles/    # collectstatic output (nginx /static/)
│   └── .venv/
├── import_service/     # FastAPI importer (git-tracked source)
│   ├── .env            # REDIS_URL, BACKEND_URL, UPLOADS_DIR
│   └── .venv/
├── frontend/           # Next.js app (git-tracked source)
├── db/                 # db/init.sql (PostGIS + pg_trgm)
├── deploy/systemd/     # *.service units (git-tracked)
├── nginx.conf          # reverse-proxy config (git-tracked)
├── uploads/            # incoming DXF/GeoTIFF (shared: import svc writes, worker reads)
└── tiles/              # generated orthophoto XYZ tiles (nginx serves /tiles/)
```

All files are owned by the `webgis` system user.

---

## 3. Base OS setup

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

Install Python 3.11 where the distro doesn't ship it (Ubuntu 22.04 default = 3.10):

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
```

---

## 4. System packages

```bash
sudo apt-get install -y \
  postgresql postgresql-14-postgis-3 \
  redis-server nginx \
  python3.11 python3.11-venv python3.11-dev \
  nodejs npm \
  binutils gcc g++ libc-dev \
  gdal-bin libgdal-dev libgeos-dev libproj-dev python3-dev
```

Enable the base services:

```bash
sudo systemctl enable --now postgresql redis-server nginx
```

---

## 5. Database & extensions

```bash
sudo -u postgres psql -c "CREATE USER webgis WITH PASSWORD '<strong-db-password>';"
sudo -u postgres psql -c "CREATE DATABASE webgis OWNER webgis;"
sudo -u postgres psql -d webgis -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres psql -d webgis -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

`db/init.sql` performs the two `CREATE EXTENSION` steps; run it instead of the
two `psql -c` extension lines if you prefer:

```bash
sudo -u postgres psql -d webgis -f /opt/webgis/db/init.sql
```

Add the **vector-tile functions** — required for `/api/tiles/<layer>/...`
(endpoint returns 500 until these exist):

```bash
sudo -u postgres psql -d webgis -f /opt/webgis/backend/gis_app/sql/tile_functions.sql
```

Record spatial conventions (enforced by the application, no action):
DB storage **EPSG:32643** (UTM 43N), API/export **EPSG:4326**, map tiles **EPSG:3857**.

---

## 6. Application layout & service user

```bash
sudo mkdir -p /opt/webgis/uploads /opt/webgis/tiles
sudo useradd --system --home /opt/webgis --shell /usr/sbin/nologin webgis
sudo chown -R webgis:webgis /opt/webgis
```

---

## 7. Getting the code onto the server

The production server keeps a **bare mirror** of the git repo at
`/root/webgis.git` (main branch, commits rewritten to identity
`ESMS <nellaidhoo@gmail.com>` for both author and committer). From the
developer workstation the source is delivered as `git format-patch` → `git am`
into the mirror, or copied directly:

```bash
# Option A — copy the fresh directories
sudo cp -r backend import_service frontend db deploy nginx.conf /opt/webgis/
sudo chown -R webgis:webgis /opt/webgis

# Option B — deliver a patch into the mirror on the server
# (workstation)   git format-patch -1 <sha> -o <dir> && pscp <dir>/0001-*.patch user@host:/tmp/
# (server)        cd /root/webgis.git && git am -q /tmp/0001-*.patch
```

Then extract into place:

```bash
sudo tar -xzf /tmp/app.tar.gz -C /opt/webgis/backend --strip-components=1
sudo chown -R webgis:webgis /opt/webgis
```

---

## 8. Environment files

### `/opt/webgis/backend/.env` (Django + Celery)

```env
# postgis:// scheme selects the GeoDjango engine automatically (dj-database-url)
DATABASE_URL=postgis://webgis:<strong-db-password>@127.0.0.1:5432/webgis
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<random-50+-char-string>
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,<server-ip>,<your-domain>
TILES_DIR=/opt/webgis/tiles

# Optional — real SMTP so password-rest/notifications leave the box
# (default EMAIL_BACKEND is console; Sprint 6 forced-reset flows rely on this)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=no-reply@example.com
EMAIL_HOST_PASSWORD=<smtp-password>
DEFAULT_FROM_EMAIL='WebGIS <no-reply@example.com>'
```

`SECRET_KEY` is also the SimpleJWT signing key. Generate with
`python3 -c "import secrets; print(secrets.token_urlsafe(60))"`.

### `/opt/webgis/import_service/.env`

```env
REDIS_URL=redis://localhost:6379/0
BACKEND_URL=http://127.0.0.1:8000
UPLOADS_DIR=/opt/webgis/uploads
```

### Frontend

`NEXT_PUBLIC_API_URL` is **baked at build time** (Next.js `NEXT_PUBLIC_*`). It
must point at the public origin the browser reaches, e.g.
`http://192.168.150.33/api` or `https://gis.example.com/api`. The
`Environment=...` line in `webgis-frontend.service` does **not** affect the
built bundle — always rebuild on the server after changing it (see §13).

---

## 9. Python venvs & dependencies

```bash
cd /opt/webgis/backend
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cd /opt/webgis/import_service
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

---

## 10. Build the frontend (on the server)

```bash
cd /opt/webgis/frontend
npm ci
NEXT_PUBLIC_API_URL=http://<public-origin>/api npm run build
```

A locally-built artifact is useless — the API base URL differs between local
(`http://localhost:8000`) and the server, and it is embedded at build time.

---

## 11. Migrate, static files, seed

```bash
cd /opt/webgis/backend
sudo -u webgis .venv/bin/python manage.py migrate
sudo -u webgis .venv/bin/python manage.py collectstatic --noinput
sudo -u webgis .venv/bin/python manage.py seed_data
```

> **Critical (known production incident):** if any service is already running,
> **run `manage.py migrate` BEFORE restarting the Celery worker.** A stale
> worker holding pre-migration task code will fail on new rows; because upload
> processing wraps the run in `transaction.atomic`, the whole staged survey
> session is rolled back (safe but surprising). Restart `webgis-worker` last in
> the restart sequence (§14).

Seed users (from `seed_data`, see README role matrix): `admin / admin123`
(Super Admin), `staff / staff123` (Council Staff). Change them or enforce a
forced-password-reset immediately.

Django admin static assets are collected into `backend/staticfiles/`, which
nginx serves at `/static/` so `/admin/` renders.

---

## 12. Install systemd units

```bash
sudo cp /opt/webgis/deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now webgis-backend webgis-worker webgis-import webgis-frontend
```

The shipped units end in:

- `webgis-backend`: `gunicorn gis_project.wsgi:application --bind 127.0.0.1:8000 --workers 3`
- `webgis-worker`: `celery -A gis_project worker --loglevel=info`
- `webgis-import`:  `uvicorn main:app --host 127.0.0.1 --port 8001`
- `webgis-frontend`: `next start -p 3000`

Production additionally runs the frontend on `0.0.0.0` via npm as
`ExecStart=/usr/bin/npm run start -- -p 3000 -H 0.0.0.0` — keep this variant if
anything other than nginx should reach the frontend directly.

Sanity check:

```bash
systemctl is-active webgis-backend webgis-worker webgis-import webgis-frontend
# expect: active x4
journalctl -u webgis-backend -n 50 --no-pager
```

---

## 13. nginx

```bash
sudo cp /opt/webgis/nginx.conf /etc/nginx/nginx.conf
sudo nginx -t && sudo systemctl reload nginx
```

The supplied `nginx.conf` routes `/static/`, `/tiles/`, `/api/import/`,
`/api/`, `/admin/` and `/`. Notes:

- `proxy_pass http://127.0.0.1:8001/;` must keep the **trailing slash** so
  uvicorn sees `/import/` — removing it breaks every browser upload.
- `client_max_body_size 100M;` on `/api/import/` supports large DXF/GeoTIFF.
- The `/sms/` block and the five `server_name` entries are host-specific to
  263-linuxserver (a sibling app on port 3001) — delete or rename them for a
  fresh server.

---

## 14. First-run verification

```bash
# gateways
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/            # 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/admin/      # 200

# API health
curl -s http://127.0.0.1:8000/api/health/            # {"status":"healthy"}
curl -s http://127.0.0.1:8000/api/v1/health/

# security posture (Sprint 5 + 7 expectations)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/export/                              # 401 (enumeration requires auth)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/tiles/utilities/14/7745/4304/        # 403 for anon/low-clearance
curl -s http://localhost/api/public/layers/           # only roads, buildings, facilities, land_use
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/export/fiber_lines/                  # 403 (utilities not exportable)
```

Full end-to-end assurance uses the stack harness (`webgis-stack/harness.py`,
**55/55** local): login → upload DXF → QUEUED/COMPLETED → staging → validate →
approve → production merge → export. There is also a server-side smoke script
(`webgis-stack/deploy_check.sh`, expects a fixture DXF at `/tmp/live_check.dxf`)
that exercises upload → staging → reject (staging-only, never writes prod).

---

## 15. Deploy / update runbook

Applied to the production server for every released change:

1. **Backup first** (on server):
   ```bash
   TS=$(date +%Y%m%d_%H%M%S); sudo mkdir -p /opt/webgis/deploy/backups/s$TS
   sudo cp /opt/webgis/backend/<changed-files> /opt/webgis/deploy/backups/s$TS/
   ```
2. **Ship & extract** (tarball rooted at `backend/`, `import_service/`, etc.):
   ```bash
   sudo tar -xzf /tmp/app.tar.gz -C /opt/webgis/<component> --strip-components=1
   sudo chown -R webgis:webgis /opt/webgis
   ```
3. **Static checks**: `sudo -u webgis .venv/bin/python manage.py check`
   (from `/opt/webgis/backend`).
4. **Migrate** (model changes): `manage.py migrate` before any restart.
5. **Rebuild frontend on server** if the frontend changed (§10).
6. **Restart in order**: `webgis-backend` → `webgis-import` →
   `webgis-frontend` → `webgis-worker` (worker last — see §11).
7. **Verify**: systemd `is-active`, health endpoints, the §14 checks that touch
   the changed surface, and an end-to-end upload via the harness/deploy_check.
8. **Mirror the git history** if the change came as a patch (re-map to the
   `ESMS` identity): `git am` into `/root/webgis.git`, then
   `git commit --amend --author="ESMS <nellaidhoo@gmail.com>" --no-edit`.

Rollback: the `deploy/backups/s*/` snapshots carry the previous versions of the
changed files — restore them, re-run `manage.py migrate` **backward only if the
previous migrations drop them** (downgrade = restore files + DB where needed),
and restart.

---

## 16. Operations notes

**Backups**
```bash
sudo -u postgres pg_dump -Fc webgis -f /var/backups/webgis_$(date +%F).dump
rsync -a /opt/webgis/uploads /opt/webgis/tiles backup-host:/backup/
```

**Logs**
```bash
journalctl -u webgis-worker  -f      # import queue activity
journalctl -u webgis-backend -f      # API/validation/audit
tail -f /var/log/nginx/access.log
```

**CLI approvals** (mirror the admin UI exactly — same transactional merge,
audit trail, staging cleanup):
```bash
cd /opt/webgis/backend
sudo -u webgis .venv/bin/python manage.py approve_session <session_id> --comments "checked"
sudo -u webgis .venv/bin/python manage.py approve_all
```

---

## 17. Security checklist (Sprint 5 + 7, in force since S5/S7)

- Public portal `/api/public/*` is **read-only**, exposes **only** PUBLIC
  layers (roads, buildings, facilities, land_use); all writes denied.
- Layer visibility is enforced **server-side** on reads, exports and tiles
  (`Layer` registry: public / registered / council staff+). The `utilities`
  tile bucket emits street lights + water + electrical and is gated by the
  **highest** of those clearances (`all()` over the emitted keys).
- Export-layer **enumeration** (`GET /api/export/`, `/api/v1/export/`)
  requires authentication; per-layer export follows `can_export_layer`.
- Production serializers strip `created_by`, `created_by_name`,
  `source_file`, `source_session`, `accuracy` for authenticated non-staff
  readers (public portal already strips them for everyone).
- Addresses are gated by the building-layer registry + shared write audit.
- `DEBUG=False`, strong `SECRET_KEY`, locked-down `ALLOWED_HOSTS`, no secrets
  in git (`.env*` ignored; repo ships `.env.example` only).
- Forced password reset for imported/seed accounts at first login (Sprint 6).
- Credentials pro-tip: the credentialed `webgis` DB role + SMTP creds are the
  only production secrets on the box — keep them out of backups of the source.

See `IMPLEMENTED_FEATURES.md` §5–§8 for the full matrix and §10 for the current
verification status.