# WebGIS — Implemented Features Outline

A full outline of every feature implemented across the project, organized by
sprint and by functional area. Status notes reflect the deployed state on the
production server (`192.168.150.33`) and local dev workstation.

---

## Feature Matrix (by Sprint)

| Area | Feature | Status |
|------|---------|--------|
| Sprint 1 | Broker fix, health checks, retry/idempotency, lightweight metrics | ✅ Complete |
| Sprint 2 | User registration, approval workflow, rate limiting, admin bulk actions | ✅ Complete |
| Sprint 3 | Survey ingestion: upload wizard, precheck, session grouping, staged preview, lineage/history | ✅ Complete |
| Sprint 4 | Data export (backend API + frontend UI) | ✅ Complete |
| Sprint 5 | Security & data governance: layer visibility, export gating, public read-only portal, lineage | 🔄 Implemented (pending deploy) |

---

## 1. Platform & Architecture

- **Stack:** Django REST Framework (backend) + FastAPI (import service) + Celery/Redis (worker) + Next.js/TypeScript (frontend) + PostgreSQL/PostGIS + nginx.
- **No Docker — native Linux deployment** via systemd units:
  - `webgis-backend` (gunicorn, port 8000)
  - `webgis-import` (uvicorn, port 8001)
  - `webgis-worker` (Celery)
  - `webgis-frontend` (Next.js, port 3000)
- **Coordinate reference systems:**
  - Storage: UTM Zone 43N (EPSG:32643)
  - API/Export: WGS 84 (EPSG:4326)
  - Visualization: Web Mercator (EPSG:3857)
- **Portable dev stack** (`C:\Users\nella\webgis-stack`) mirrors the server for local e2e testing (PG 17.5 + PostGIS on port 5544).

---

## 2. Sprint 1 — Reliability & Observability

- **Message broker fix** for the async Celery + Redis pipeline.
- **Health checks** across all services (`/api/health/`, OpenAPI, Swagger, ReDoc).
- **Retry logic & idempotency** on import jobs (no duplicate side-effects on retries).
- **Lightweight metrics** (`/api/metrics/`, `metrics.increment(...)` counters for uploads/exports/errors).

---

## 3. Sprint 2 — Access Control & Workflow

- **Self-service user registration** (`/api/auth/register/`) and profile (`/api/auth/me/`).
- **JWT authentication** (`/api/auth/token/`, `webgis_token` stored in localStorage).
- **Role model:** Guest → Registered User → Council Staff → Section Admin → Super Admin.
- **Approval workflow** for staged survey data with transactional merge into production.
- **Rate limiting** on auth/upload/search/export endpoints (upload: 20/10 min).
- **Django admin bulk actions** + list filters/search on core GIS models.

---

## 4. Sprint 3 — Survey Ingestion Improvements

### 4.1 Pre-Upload Validation Wizard (`UploadWizard.tsx` + FastAPI precheck)
- 3-step drag-and-drop wizard: **Select → Validate & Preview → Upload & Process**.
- `POST /import/precheck/` on the FastAPI import service:
  - Extension / file-size / MD5 validation.
  - **Duplicate detection** against `gis_app_uploadedfile`.
  - **DXF sniffing** via `ezdxf` with utf-8 / cp1252 / latin-1 decode fallback; returns predicted layers + estimated feature count.
  - **Content-type sanity check** (advisory warning on unexpected MIME, non-blocking).
- Async progress via **polling** `GET /import/status/{id}` with progress bar + live log.
- Terminal-state handling: `STAGED`/`COMPLETED` = ingestion done (distinct from `APPROVED`, which is the separate human review step).

### 4.2 Grouped Session List (`ApprovalDashboard.tsx`)
- Sessions **grouped by status** with **status + session-type filters** and count pills.
- **Pagination** on the sessions list (`?limit=200`, `results`/`count` shape via `LimitOffsetPagination`).
- Per-session actions: **Preview** staged geometry / imagery tiles, **View Logs**, **Approve** (merge), **Reject** (purge staging), **Export**.

### 4.3 Interactive Staged-Geometry Preview
- Leaflet map rendering of staged draft features.
- **Per-layer `L.layerGroup` refs** with a color-coded layer-toggle sidebar (checkboxes with feature counts).
- **Click-to-inspect** attribute panel showing staged attributes.

### 4.4 Lineage & History Tracking
- **Details / Lineage / History** tabs in the feature attribute panel (`MapViewer.tsx`).
- Timeline honestly derived from existing metadata (upload time, approval, merge); full audit trail tracked at the survey-session level.
- `created_by_name` serializer field on all **14 production + 14 staging** feature serializers.

---

## 5. Sprint 4 — Data Export

### 5.1 Backend Export API (already present, verified)
- `backend/gis_app/export.py` — `DataExporter` class exporting all 14 layer types:
  - **GeoJSON** (FeatureCollection with per-layer metadata)
  - **CSV** (with `wkt_geometry` + `geometry_type` columns)
  - **Shapefile** (zipped; GDAL/OGR path with a manual CSV fallback)
  - **Spatial bbox filter** (`geometry__intersects` Polygon)
  - **Field filters** (`status=ACTIVE`, etc.)
- `backend/gis_app/views.py` — `ExportView` + `ExportLayersView`:
  - `GET /api/export/<layer>/?export_format=geojson&bbox=...&filters=...`
  - `GET /api/export/` — lists supported layers/formats with examples.
  - `permission_classes = [AllowAny]` (read-only, no auth required).
  - Metrics tracking (`exports.total`, `exports.{fmt}`, `exports.errors`).
  - Full validation (invalid format/layer → 400; parse errors → 500).
- `backend/gis_app/urls.py` — routes wired at lines 51–52.

### 5.2 Frontend Export UI
- **`ExportModal.tsx`** (new component):
  - Format picker: **GeoJSON / CSV / Shapefile (ZIP)** with icons + file-type hints.
  - Displays current **layer** + optional **bounding box** context.
  - Optional `Authorization: Bearer` header (backend is `AllowAny`, so auth is optional).
  - Filename resolved from `Content-Disposition` (fallback generated per layer/format).
  - Blob-download, inline **loading spinner** and **error state** with toast notifications.
  - Uses the codebase's real conventions: `useToast()`, `webgis_token` localStorage key, `apiBaseUrl` prop, hand-rolled modal overlay (no external Dialog lib), `lucide-react` icons.
- **`MapViewer.tsx` integration:**
  - **Export** button in the top toolbar (emerald accent, `Download` icon).
  - Passes current viewport bounds via `getMapBounds()` (west,south,east,north) as the bbox filter.
  - Renders `<ExportModal>` in the popups section.
- **`ApprovalDashboard.tsx` integration:**
  - **Export** button in each session card action area.
  - Opens the same modal (exports approved **production** data — the backend has no staged-export endpoint, so the button targets production layers).

### 5.3 Export Tests (harness)
- `webgis-stack/harness.py` covers export end-to-end (39/39 PASS):
  - GeoJSON FeatureCollection with features.
  - CSV with header + rows + `wkt_geometry`.
  - Invalid format → 400; invalid layer → 400.
  - v1 and legacy `/api/export/` routes.

---

## 6. Sprint 5 — Security & Data Governance

Backend-enforced access control; **no reliance on frontend layer hiding.** Security is
derived from a new `LayerRegistry` and applied uniformly across **REST viewsets,
`/api/public/*`, search, vector tiles/MVT, and exports.**

### 6.1 Layer Registry (`LayerRegistry` model + seed migration `0008`)
Central registry of every GIS layer. Defaults:
| Layer | Visibility | Exportable |
|-------|-----------|------------|
| roads, buildings, facilities, land_use | PUBLIC | ✅ yes |
| street_lights | AUTHENTICATED | ❌ no |
| water/sewer/electrical/fiber (lines+nodes) | COUNCIL | ❌ no |

- `is_enabled`, `min_zoom/max_zoom`, `style_config` drive public portal rendering.
- Unregistered/disabled layers are treated as fully **restricted by default** (defensive).

### 6.2 `security.py` helpers + permissions
- `user_has_layer_visibility(user, key)` / `can_export_layer(user, key)`.
- Role helpers: `is_admin` / `is_section_admin` / `is_staff`.
- DRF classes: `LayerVisibilityPermission`, `LayerWritePermission` (writes = Section Admin+),
  `PublicOnly` (rejects every non-safe method).
- `write_audit()` — generic `AuditLog` writer.

### 6.3 Enforcement across all access paths
- **Viewsets:** all 14 layer viewsets use `[LayerVisibilityPermission, LayerWritePermission]`
  with a `layer_key`; fixed the pre-existing broken singular `permission_class` on Road/Building.
  Anonymous can read/export only PUBLIC layers; utilities are 403/denied.
- **SearchView:** each layer's results are filtered by the caller's visibility
  (street_lights proximity only for authenticated; utilities never searched publicly).
- **VectorTileView:** each tile layer maps to a registry key; restricted tiles (e.g.
  `utilities`) return **403** to anonymous/low-clearance callers.
- **ExportView:** enforces `can_export_layer` → restricted/utility exports return **403**;
  writes `EXPORT_REQUESTED` / `EXPORT_DENIED` audit events.

### 6.4 Public field-stripping serializers
- `PublicRoad/Building/Facility/LandUseSerializer` expose **only** safe public fields
  (no `created_by`, `accuracy`, `source_file`, `source_session`, internal audit metadata).

### 6.5 Public read-only portal `/api/public/*`
- `views_public.py` + `urls_public.py` (wired once at the project level, not duplicated
  under the legacy include), all guarded by `PublicOnly`:
  - `GET /api/public/layers/` — metadata for enabled layers visible to anonymous callers.
  - `GET /api/public/search/` — public text + proximity search (public layers only).
  - `GET /api/public/<layer>/` — roads / buildings / facilities / land_use feature lists,
    with `?bbox=` and `?limit=` support.
  - `GET /api/public/imagery/` — latest public drone orthomosaic metadata (read-only).
- **Strictly read-only:** any POST/PUT/PATCH/DELETE is rejected.

### 6.6 Lineage
- `source_session` FK on `BaseGISModel` links every approved production record back to the
  survey session it was merged from; `_merge_layer` now records it.

### 6.7 Verification (S5)
- `manage.py check` clean, `py_compile` clean, migrations applied locally.
- Django-level tests confirmed: anonymous 403/denied on `water_lines`/`sewer_lines`/`street_lights`
  viewsets and on `utilities` tiles and utility exports; public layers readable/exportable;
  `/api/public/*` lists only the 4 PUBLIC layers and rejects mutations.
- Harness gained S5 security checks (public layers = PUBLIC only, public POST denied,
  restricted viewset/tile/export denied, public export still works).

---

## 7. Legacy / Base Features (pre-sprint, retained)

- **Vector tile serving** (`/api/tiles/<layer>/<z>/<x>/<y>/`) for fast map rendering.
- **Combined trigram + proximity search** (`/api/search/`).
- **Orthophoto (GeoTIFF) import pipeline:** COG conversion + `gdal2tiles` XYZ tiling, served by nginx at `/tiles/<session_id>/...`; latest imagery discovered via `/api/survey-sessions/latest-imagery/`.
- **Building addresses** linkage (`/api/buildings/{id}/addresses/`).
- **In-house measurement tool** (distance / area, no external deps) in `MapViewer.tsx`.
- **User registration + JWT + role simulation** UI helper in the toolbar.

---

## 8. Verification & Tooling

- **Harness e2e:** `webgis-stack/harness.py` — full lifecycle test (login → upload → parse → approve → verify production → export) currently **39/39 PASS**.
- **Frontend:** `npx tsc --noEmit` clean; `npm run build` clean (local + server).
- **Backend:** `manage.py check` clean.
- **Deployment:** `pscp` → `/tmp/`, sudo-copy + `chown webgis:webgis`, `systemctl restart <unit>`; frontend rebuilt on server then restarted.
- **Git mirror sync:** `git format-patch` + `git am` into a worktree, pushed to `/root/webgis.git`.

---

## 9. Known Notes / Decisions

- **Global DRF pagination is intentionally disabled** — MapViewer loads all features via `data.results || data`; pagination is scoped **only** to `SurveySessionViewSet`.
- **`created_by_name` must be declared in the serializer class body** (not inherited via mixin) due to DRF metaclass behavior.
- **Staged export is not yet a backend endpoint** — the Export button exports production layers. A staged-export endpoint (`/api/survey-sessions/{id}/export/`) would be a future enhancement.
