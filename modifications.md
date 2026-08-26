WebGIS System Modifications Summary
📋 Overview
This document summarizes all modifications made to the WebGIS system during deployment and troubleshooting on the server 263-linuxserver (IP: 192.168.150.33).

🗄️ Database & Backend Modifications
1. Database Configuration
File: /opt/webgis/backend/gis_project/settings.py

Changes:

Fixed PostGIS database engine configuration

Added dj_database_url for proper database URL parsing

Set correct database connection parameters

python
# Before: env.db() was not setting PostGIS engine properly
# After: Explicit PostGIS engine configuration
DATABASES = {
    'default': dj_database_url.config(
        default=DATABASE_URL,
        engine='django.contrib.gis.db.backends.postgis'
    )
}
2. Environment Configuration
File: /opt/webgis/backend/.env

Changes:

Updated ALLOWED_HOSTS to include server IP

Set DEBUG=True for troubleshooting (should be False in production)

Fixed database URL with proper password encoding

env
DATABASE_URL=postgresql://postgres:<REDACTED>@localhost:5432/webgisdb
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.150.33,263-linuxserver.local
DEBUG=True
3. Facility Category Model
File: /opt/webgis/backend/gis_app/models.py

Added:

FacilityCategory model for admin-managed facility types

ForeignKey relationship from StagingFacility and Facility to categories

python
class FacilityCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    icon = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=7, default='#007bff')
    is_active = models.BooleanField(default=True)
4. DXF Parser Enhancements
File: /opt/webgis/backend/gis_app/tasks.py

Changes:

Added support for multiple layer names (pl, Building Line, Draft, etc.)

Implemented auto-detection and reprojection of UTM coordinates to WGS84

Added facility category auto-detection from layer/block names

Enhanced land use polygon detection from multiple layers

python
# Added support for multiple land use layers
target_prefixes = [
    'BLDG', 'ROAD', 'LAND_USE', 'FACILITY', 'SL',
    'PL', 'BUILDING LINE', 'DRAFT', 'DRAFTLINE',
    # ... etc
]
5. Admin Interface Enhancements
File: /opt/webgis/backend/gis_app/admin.py

Changes:

Added FacilityCategoryAdmin for managing facility types

Added StagingFacilityAdmin with bulk category assignment

Enhanced SurveySessionAdmin with approval actions

Fixed duplicate admin registrations

6. Import Service Configuration
File: /opt/webgis/import_service/main.py

Changes:

Updated to bind to 0.0.0.0 instead of 127.0.0.1

Added proper environment variable loading

Fixed Celery/Redis connection handling

7. Management Commands Created
File: /opt/webgis/backend/gis_app/management/commands/approve_session.py

Added:

One-click session approval command

Automatic data movement from staging to main tables

Support for all data types (Buildings, Roads, Land Use, Facilities)

🗺️ Frontend Modifications
1. Map Component
File: /opt/webgis/frontend/src/components/MapViewer.tsx

Changes:

Updated map center to Nellaidhoo, Maldives ([3.94, 73.49])

Added Land Use layer to layer controls

Enhanced layer visibility management

Improved feature popup displays

tsx
// Map center updated to Nellaidhoo
const map = L.map(mapContainerRef.current, {
  center: [3.943, 73.489],
  zoom: 15,
});
2. Environment Variables
File: /opt/webgis/frontend/.env.local

Added:

env
NEXT_PUBLIC_API_URL=http://192.168.150.33/api
NEXT_PUBLIC_MAP_CENTER_LAT=3.94
NEXT_PUBLIC_MAP_CENTER_LNG=73.49
NEXT_PUBLIC_MAP_ZOOM=15
3. API Integration
File: /opt/webgis/frontend/app/page.tsx

Changes:

Added land use data fetching

Integrated all layer types (Buildings, Roads, Land Use, Facilities)

Improved loading states

🔧 System Service Modifications
1. Backend Service
File: /etc/systemd/system/webgis-backend.service

Changes:

Updated to bind to 0.0.0.0:8000

Fixed WSGI application path

ini
ExecStart=/opt/webgis/backend/.venv/bin/gunicorn gis_project.wsgi:application --bind 0.0.0.0:8000 --workers 3
2. Import Service
File: /etc/systemd/system/webgis-import.service

Changes:

Updated to bind to 0.0.0.0:8001

Added environment file loading

ini
ExecStart=/opt/webgis/import_service/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
3. Celery Worker
File: /etc/systemd/system/webgis-worker.service

Changes:

Verified Redis connection

Ensured proper Celery configuration

4. Nginx Configuration
File: /etc/nginx/sites-available/default

Changes:

Added static file serving configuration

Configured API proxy to backend

Added import service proxy

nginx
location /static/ {
    alias /opt/webgis/backend/staticfiles/;
    expires 1y;
    add_header Cache-Control "public, immutable";
}
📦 Python Package Additions
bash
# Installed packages
pip install dj-database-url
pip install pyproj
pip install psycopg2-binary
🗄️ Database Migrations
bash
python manage.py makemigrations
python manage.py migrate
Migrations created:

FacilityCategory model migration

StagingFacility category field migration

Facility category field migration

🔄 Workflow Changes
New Import Workflow
Upload DXF → Import Service (FastAPI)

Celery processes → Parses DXF in background

Data goes to staging → Staging tables

Admin approves → Django Admin or command line

Data moves to main → Main tables

Auto-reprojection → UTM to WGS84

Display on map → Frontend updates

Admin Actions Added
Approve selected sessions (bulk action)

Assign facility categories (bulk action)

One-click session approval command

🌐 Layer Support
Layer	Status	Notes
🏠 Buildings	✅ Working	BLDG layer, closed polygons
🛣️ Roads	✅ Working	ROAD layer, line strings
🗺️ Land Use	✅ Working	LAND_USE, pl, Building Line layers
📍 Facilities	✅ Ready	FACILITY layer with categories
💡 Street Lights	✅ Ready	SL layer
💧 Water Lines	✅ Ready	WATER_LINE layer
🔌 Electrical	✅ Ready	ELECTRICAL_LINE layer
🔗 Fiber	✅ Ready	FIBER_LINE layer
📊 Data Imported
Data Type	Count	Status
Buildings	14	✅ Displayed
Roads	2	✅ Displayed
Land Use	5+	✅ Displayed
Facilities	0	⏳ Pending
🔧 Key Troubleshooting Solutions
Issues Fixed
PostGIS engine not recognized → Fixed database configuration

Static files 404 → Configured nginx static serving

UTM coordinates not displaying → Added auto-reprojection

Celery worker not processing → Fixed Redis connection

Import service not accessible → Bound to 0.0.0.0

Buildings not importing → Fixed polygon closure detection

Land use not importing → Added support for multiple layers

Elevation/Z values → Flattened polygons to 2D

Coordinate System Handling
Storage: EPSG:32643 (UTM Zone 43N)

Display: EPSG:4326 (WGS84)

Auto-reprojection: ✅ Working

🚀 Access Points
Service	URL
Main Map	http://192.168.150.33/
Django Admin	http://192.168.150.33/admin/
API	http://192.168.150.33/api/
Import API	http://192.168.150.33/api/import/
Import Docs	http://192.168.150.33/api/import/docs
✅ System Status
All core functionality is now operational. The WebGIS system is ready for production use.
## 2026-08-26 Operations Hardening

Security
- Server login (nci-server) and Postgres role postgres passwords rotated; values are held in the password manager only, never in docs or repos.
- Redis now requires authentication (requirepass); broker URLs in both service .env files updated. Config backup kept at /root/redis.conf.bak.*
- Repo-wide sweep confirms zero copies of the retired credentials.

Server housekeeping
- Legacy root files moved to /opt/webgis-archive/ (Miniconda installer, stray main.py, incomplete.md, sample.html).
- Fixed two latent import-service crashes: numpy 2.4 OpenBLAS SIGILL on this CPU (pinned <2.4) and missing async-timeout for redis 8. Both captured in import_service/requirements.txt.

Backups and version control
- Nightly pg_dump of webgisdb at 02:30 UTC via /etc/cron.d/webgis-backup, 14-day retention, into /var/backups/webgis/.
- Code mirrored to bare repo /root/webgis.git on the server (refresh: git bundle --all, pscp, git fetch in the mirror).

Verification
- Local end-to-end harness: 22/22 checks passing.
- Live server flow through nginx re-tested post-rotation: upload -> COMPLETED -> approve -> search all green.
