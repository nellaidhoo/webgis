# WebGIS Usage Guide

Step-by-step guide for using the **Django Admin Panel** and the **WebGIS Frontend Map Portal**.

> Default map center: **Nellaidhoo, Maldives** (`lat 6.7156, lng 72.9467`, zoom 15).  
> Change it without code edits via `NEXT_PUBLIC_MAP_CENTER_LAT` / `NEXT_PUBLIC_MAP_CENTER_LNG` / `NEXT_PUBLIC_MAP_ZOOM` in `frontend/.env.local` (baked at build time).

---

## Part A — Django Admin Panel

**Access:** `http://<server-ip>/admin/` (or `http://localhost:8000/admin/` in local dev).  
**Login:** use a staff/superuser account (seeded: `admin` / `admin123`).

### A1. Log in
1. Open `/admin/` in your browser.
2. Enter **Username** and **Password**.
3. Click **Log in**.

### A2. Manage Facility Categories (lookups)
Facility types are data-driven — no code changes needed.
1. In the left sidebar, click **Facility Categories**.
2. Click **Add facility category** (top right).
3. Fill in:
   - **Name** — display name (e.g. `Mosque`)
   - **Code** — short uppercase code used for DXF layer matching (e.g. `MOSQUE`)
   - **Icon** — emoji or icon name (e.g. `🕌`)
   - **Color** — hex color (e.g. `#10b981`)
   - **Is active** — uncheck to hide from use
4. Click **Save**.
5. To edit inline, change **icon / color / is_active** directly in the list view and click **Save**.

### A3. Review Survey Sessions (uploads)
1. Click **Survey sessions** in the sidebar.
2. Filter by **Status** (`STAGED`, `PROCESSING`, `COMPLETED`, `APPROVED`, `REJECTED`) or **Session type** (`SURVEY`, `IMAGERY`).
3. Click a session ID to view its details (read-only `created_at`, `approved_at`).
4. For a **SURVEY** session that is ready, select it and choose **Approve selected sessions** from the **Action** dropdown, then click **Go**.  
   This merges all staged rows into production tables transactionally and writes an audit record.
5. Rejected sessions can be marked via the frontend; the admin can also inspect `Approval history` and `Audit log` entries.

### A4. Bulk-assign Facility Categories to staged facilities
1. Click **Staging facilities**.
2. Filter by session/status as needed.
3. Select the facilities to categorise (checkboxes).
4. Choose **Assign category to selected facilities** from the **Action** dropdown → **Go**.
5. Pick a category and click **Apply**.

### A5. Inspect / edit production GIS features
Every layer has a production and a staging table (e.g. `Roads` / `Staging roads`, `Buildings` / `Staging buildings`, utilities, `Land use`, `Facilities`, `Addresses`).
1. Click the model name (e.g. **Buildings**).
2. Use **search** (asset code, name) and **filters** (status, type) to find a feature.
3. Click the row to open the GIS editor (OpenLayers map widget) and edit attributes/geometry.
4. Click **Save**.

### A6. Manage User Registration Requests
1. Click **User registration requests**.
2. Filter by **Status** (`PENDING` by default).
3. Select one or more pending requests.
4. Choose **Approve selected registrations** or **Reject selected registrations** → **Go**.  
   Approval activates the account and adds it to the **Registered User** group; rejection deactivates it.

### A7. Force a password change / reset
1. Click **User account profiles**.
2. Select the user(s).
3. Choose **Reset password & require change at next login** → **Go**.  
   A temporary password is generated, the account is flagged `must_change_password`, and (if configured) an email notification is sent.

### A8. Validation Reports
1. Click **Survey validation reports** to review per-session data-quality results (`status`, `total_features`, `error_count`, `warning_count`, `validated_at`).

### A9. Uploaded files & processing jobs
- **Uploaded files**: view file name, size, session, upload time.
- **Processing jobs**: monitor status and start/complete timestamps.

---

## Part B — Frontend Map Portal

**Access:** `http://<server-ip>/` (root).  
**Default view:** map centered on Nellaidhoo, Maldives.

### B1. Navigate the map
1. **Pan:** click and drag.
2. **Zoom:** mouse wheel or the **+ / −** buttons (bottom-right).
3. **Layer toggle:** open the Layers panel (left sidebar) and check/uncheck layers:
   - Base maps: CartoDB Dark (default), OpenStreetMap, Orthophoto (drone tiles).
   - Core: Buildings, Roads, Land Use, Facilities.
   - Assets & Networks: Street Lights, Water Lines/Nodes, Sewer Lines/Manholes/Junctions, Electrical Lines/Nodes, Fiber Lines/Nodes.
4. **Search:** type at least 2 characters in the search box (top). Results cover houses, roads, facilities. Click a result to fly to it.

### B2. View feature details
1. Click any feature on the map.
2. A popup/panel shows its attributes (asset code, name, type, etc.).
3. Use the tabs: **Details**, **Lineage**, **History**.

### B3. Measure distances / areas
1. Click the **Measure** tool.
2. Click points on the map to draw a polyline; distance accumulates.
3. Double-click or use the close action to form a polygon and see its area.
4. Click again to clear.

### B4. Authenticate (login / register)
1. Click the **Account / Login** button (top-right header).
2. **Login:** enter username + password → **Login**.
3. **Register:** switch to **Create Account**, fill username/email/password → **Create Account** (creates a read-only Registered User).
4. **Demo bypass:** click **Simulate Admin Mode (Bypass)** to enter presentation mode as Super Admin (local demos only).
5. On login, if `must_change_password` is set, a forced-change modal appears — set a new password before continuing.

### B5. Role-based capabilities
| Role | What you can do |
|------|-----------------|
| Guest | View core layers (roads, buildings, facilities), search |
| Registered User | + view utility network layers |
| Council Staff | + update addresses, edit metadata attributes |
| Section Admin | + upload surveys/imagery |
| Super Admin | + draw/edit geometries, approve/reject sessions, manage users |

Role is selected via the dropdown in the top-right header (demo) or determined by the logged-in account.

### B6. Upload a survey (Section/Super Admin)
1. Click **Approvals / Ingestion** (or the upload entry point).
2. In the left panel **Ingest CAD Package**, choose a file:
   - `.dxf` → Survey (staged, requires approval)
   - `.tif` / `.tiff` → Imagery (auto-tiled, auto-approved)
3. Add optional notes and submit.
4. The session appears in the list with status `PROCESSING` → `COMPLETED`.

### B7. Review & approve a staged session (Super Admin)
1. Open the **Approval Dashboard**.
2. Filter by status/type.
3. Click a session to **Preview** staged features overlaid on the map (toggle layers, click features for attributes).
4. Optionally click **Validate** to run the data-quality report.
5. Click **Approve** to merge into production, or **Reject** to discard.

### B8. Export data (per layer)
1. Open the **Export** modal (Export button).
2. Select the layers to export and format (GeoJSON).
3. Confirm — downloads the selected layers.

### B9. Manage users (Super Admin)
1. Open the **Users** panel.
2. View accounts, activate/deactivate, or trigger password resets (mirrors Django admin actions).

### B10. Orthophoto (drone imagery)
- The latest published imagery session is auto-discovered; switch the base map to **Orthophoto** to view drone tiles.
- Imagery sessions are auto-approved once tiling completes — no manual approval needed.

---

## Quick reference — seeded accounts

| Username | Password | Role |
|----------|----------|------|
| (none) | — | Guest (public) |
| (self-register) | — | Registered User |
| `staff` | `staff123` | Council Staff |
| `admin` | `admin123` | Super Admin |

## Troubleshooting
- **Map blank / tiles missing:** check nginx tile route and `TILES_DIR`; for orthophoto, ensure an imagery session completed.
- **Login fails:** verify backend reachable at `NEXT_PUBLIC_API_URL`; check `ALLOWED_HOSTS`.
- **Staged data not appearing:** session must reach `COMPLETED` before approval; check Celery worker logs.
- **Geometry not saving:** account must have edit permission (Council Staff+); forced password change must be completed first.