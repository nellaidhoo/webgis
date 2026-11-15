# Updating the Linux Deployment from GitHub

Guide for refreshing the production server (`263-linuxserver`, `192.168.150.33`)
from the GitHub repository `https://github.com/nellaidhoo/webgis.git`.

> Source of truth is now **GitHub**, not the on-server bare mirror `/root/webgis.git`.
> Run all commands below **on the server** (as `root` or via `sudo`).

---

## 0. Prerequisites

- SSH access to the server (root or a user with sudo).
- Outbound HTTPS access from the server to `github.com`.
- `git` installed (`sudo apt-get install -y git`).
- Existing deployment at `/opt/webgis` (see `DEPLOYMENT.md`).

Confirm connectivity:

```bash
curl -sI https://github.com/nellaidhoo/webgis.git | head -1
git --version
```

---

## 1. One-time setup: keep a clean source checkout

The runtime tree `/opt/webgis` holds secrets, data and venvs, so it must **not**
become a git working tree. Keep a separate clone that is only used as a source
of updates:

```bash
sudo mkdir -p /opt/webgis-src
sudo chown webgis:webgis /opt/webgis-src
sudo -u webgis git clone https://github.com/nellaidhoo/webgis.git /opt/webgis-src
```

> If the server has no outbound HTTPS, instead bundle locally and `scp`/`pscp`:
> ```bash
> # workstation
> git bundle create webgis.bundle --all
> scp webgis.bundle root@192.168.150.33:/tmp/
> # server
> sudo -u webgis git clone /tmp/webgis.bundle /opt/webgis-src
> ```

(Optional) also refresh the legacy bare mirror so existing tooling keeps working:

```bash
cd /root/webgis.git && git fetch https://github.com/nellaidhoo/webgis.git main:main
```

---

## 2. Update procedure (each release)

### 2.1 Back up the current deployment

```bash
TS=$(date +%Y%m%d_%H%M%S)
sudo mkdir -p /opt/webgis/deploy/backups/$TS
sudo cp -a /opt/webgis/backend /opt/webgis/deploy/backups/$TS/backend 2>/dev/null || true
sudo cp -a /opt/webgis/frontend /opt/webgis/deploy/backups/$TS/frontend 2>/dev/null || true
sudo cp -a /opt/webgis/import_service /opt/webgis/deploy/backups/$TS/import_service 2>/dev/null || true
```

### 2.2 Pull the latest source

```bash
cd /opt/webgis-src
sudo -u webgis git fetch origin
sudo -u webgis git reset --hard origin/main
sudo -u webgis git log --oneline -3
```

### 2.3 Sync source into the runtime tree (preserve secrets/data)

Copy the git-tracked components, **excluding** `.env`, `uploads`, `tiles`,
`venvs`, `node_modules`, `staticfiles`, `.next`:

```bash
cd /opt/webgis-src
# backend
sudo rsync -a --delete \
  --exclude='.env' --exclude='.venv' --exclude='staticfiles' --exclude='uploads' \
  backend/ /opt/webgis/backend/
# import service
sudo rsync -a --delete \
  --exclude='.env' --exclude='.venv' \
  import_service/ /opt/webgis/import_service/
# frontend
sudo rsync -a --delete \
  --exclude='.env*' --exclude='node_modules' --exclude='.next' --exclude='out' \
  frontend/ /opt/webgis/frontend/
# db + deploy units + nginx (only if changed)
sudo rsync -a db/ /opt/webgis/db/
sudo rsync -a deploy/ /opt/webgis/deploy/
sudo cp nginx.conf /opt/webgis/nginx.conf
sudo chown -R webgis:webgis /opt/webgis
```

### 2.4 Install/update dependencies (if requirements changed)

```bash
cd /opt/webgis/backend
sudo -u webgis .venv/bin/pip install -r requirements.txt
cd /opt/webgis/import_service
sudo -u webgis .venv/bin/pip install -r requirements.txt
```

### 2.5 Migrate the database (before any restart)

```bash
cd /opt/webgis/backend
sudo -u webgis .venv/bin/python manage.py check
sudo -u webgis .venv/bin/python manage.py migrate
sudo -u webgis .venv/bin/python manage.py collectstatic --noinput
```

### 2.6 Rebuild the frontend on the server

`NEXT_PUBLIC_*` values are baked at build time, so rebuild whenever frontend or
map config changes:

```bash
cd /opt/webgis/frontend
sudo -u webgis npm ci
sudo -u webgis env NEXT_PUBLIC_API_URL=http://192.168.150.33/api \
  NEXT_PUBLIC_MAP_CENTER_LAT=3.943 \
  NEXT_PUBLIC_MAP_CENTER_LNG=73.489 \
  NEXT_PUBLIC_MAP_ZOOM=15 \
  npm run build
```

(Adjust `NEXT_PUBLIC_API_URL` and map vars to your public origin as needed.)

### 2.7 Restart services (worker LAST)

```bash
sudo systemctl restart webgis-backend
sudo systemctl restart webgis-import
sudo systemctl restart webgis-frontend
sudo systemctl restart webgis-worker
```

### 2.8 Verify

```bash
systemctl is-active webgis-backend webgis-worker webgis-import webgis-frontend
# expect: active x4

curl -s -o /dev/null -w "%{http_code}\n" http://localhost/            # 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/admin/      # 200
curl -s http://127.0.0.1:8000/api/health/ 2>/dev/null || true

# nginx config if changed
sudo nginx -t && sudo systemctl reload nginx
```

Check logs if anything is off:

```bash
journalctl -u webgis-backend -n 50 --no-pager
journalctl -u webgis-worker  -n 50 --no-pager
journalctl -u webgis-import  -n 50 --no-pager
```

---

## 3. Rollback

Restore from the backup taken in step 2.1:

```bash
TS=<timestamp-from-backup-dir>
sudo systemctl stop webgis-backend webgis-worker webgis-import webgis-frontend
sudo rsync -a --delete /opt/webgis/deploy/backups/$TS/backend/  /opt/webgis/backend/
sudo rsync -a --delete /opt/webgis/deploy/backups/$TS/frontend/ /opt/webgis/frontend/
sudo rsync -a --delete /opt/webgis/deploy/backups/$TS/import_service/ /opt/webgis/import_service/
sudo chown -R webgis:webgis /opt/webgis
# Re-run migrations only if the previous code requires an older schema
sudo -u webgis /opt/webgis/backend/.venv/bin/python /opt/webgis/backend/manage.py migrate
sudo systemctl start webgis-backend webgis-import webgis-frontend webgis-worker
```

---

## 4. Notes

- `uploads/` and `tiles/` are runtime data — never delete them during an update.
- `.env` files are preserved by the `--exclude` flags above; re-check them after
  major releases in case new variables were added (see `.env.example`).
- The map default location is now configurable via
  `NEXT_PUBLIC_MAP_CENTER_LAT` / `NEXT_PUBLIC_MAP_CENTER_LNG` / `NEXT_PUBLIC_MAP_ZOOM`
  (baked at build time) — set them in the rebuild step (2.6).
- GitHub is the source of truth; the on-server bare mirror `/root/webgis.git` is
  only a legacy convenience and can be refreshed via `git fetch` (step 1).
- If the server lacks outbound internet, use the bundle method in section 1.