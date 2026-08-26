import re
from pyproj import Transformer
from django.contrib.gis.geos import GEOSGeometry, LineString, Point, Polygon
import os
import sys
import uuid
import hashlib
import base64
import json
import requests
import psycopg2
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import time
from functools import wraps

def detect_and_reproject_coordinates(coords):
    """
    Detect if coordinates are in UTM (meters) or WGS84 (decimal degrees)
    and reproject to WGS84 if needed
    """
    if not coords:
        return coords
    # Check if coordinates look like UTM (large numbers > 100,000)
    # UTM Zone 43N typically has X: 100,000-900,000, Y: 0-10,000,000
    avg_x = sum(c[0] for c in coords) / len(coords)
    avg_y = sum(c[1] for c in coords) / len(coords)
    
    # If coordinates are in UTM (meters), reproject to WGS84
    if avg_x > 10000 and avg_y > 10000:
        print(f"🔍 Detected UTM coordinates - reprojecting to WGS84")
        try:
            # UTM Zone 43N (Northern Hemisphere)
            transformer = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)
            reprojected = []
            for x, y in coords:
                lon, lat = transformer.transform(x, y)
                reprojected.append((lon, lat))
            print(f"✅ Reprojected {len(coords)} coordinates from UTM to WGS84")
            return reprojected
        except Exception as e:
            print(f"⚠️ Reprojection failed: {e}")
            return coords
    
    return coords

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=False)

print(f"REDIS_URL: {os.getenv('REDIS_URL', 'NOT SET')}")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL', 'NOT SET')}")
print(f"BACKEND_URL: {os.getenv('BACKEND_URL', 'NOT SET')}")

# Initialize Celery with error handling
try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    print("⚠️ Celery not available")

app = FastAPI(title="Island GIS Import Service", description="Handles survey drawing parsing and ingestion workflows")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Celery app
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = None

if CELERY_AVAILABLE:
    try:
        # No result backend: task outcomes are persisted by the tasks
        # themselves (SurveySession/ImagerySession rows in Django).
        celery_app = Celery("gis_project", broker=REDIS_URL)
        celery_app.conf.update(
            task_serializer='json',
            accept_content=['json'],
            result_serializer='json',
            timezone='UTC',
            enable_utc=True,
            task_track_started=True,
            task_time_limit=3600,
            task_soft_time_limit=3000,
        )
        # Test connection
        celery_app.control.ping(timeout=1.0)
        print("✅ Celery initialized successfully")
    except Exception as e:
        print(f"❌ Celery initialization failed: {e}")
        celery_app = None
else:
    print("⚠️ Celery not installed - running without background tasks")

# Database connection helper
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/webgisdb")

# libpq only understands postgresql:// URIs; Django-style postgis:// DSNs
# must be normalised before being handed to psycopg2.
if DATABASE_URL.startswith("postgis://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgis://"):]

# Shared directory where uploaded survey files are persisted for the Celery worker
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/opt/webgis/uploads")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database connection failed: {str(e)}"
        )

# Helper to compute MD5 checksum
def compute_md5(file_content):
    hash_md5 = hashlib.md5()
    hash_md5.update(file_content)
    return hash_md5.hexdigest()

# Django backend base URL used for JWT token verification
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

def decode_jwt_payload(token):
    """Extract the payload from a JWT without validating the signature."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}

def verify_token(authorization):
    """
    Validate a Bearer JWT against the Django backend and return the user_id.
    Returns None when the token is missing or invalid.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/auth/token/verify/",
            json={"token": token},
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        return decode_jwt_payload(token).get("user_id")
    except Exception:
        return None

@app.post("/import/")
async def upload_survey(
    file: UploadFile = File(...),
    notes: str = Form(""),
    authorization: str = Header(None)
):
    """
    Accepts DXF survey drawings or GeoTIFF orthophotos, computes md5, saves the
    file, creates a SurveySession in the database, and enqueues the matching
    background Celery task (DXF staging vs orthophoto tiling).
    """
    user_id = verify_token(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required. Provide a valid Bearer token.")

    filename = (file.filename or "").lower()
    if filename.endswith('.dxf'):
        session_type = 'SURVEY'
    elif filename.endswith('.tif') or filename.endswith('.tiff'):
        session_type = 'IMAGERY'
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Provide a DXF drawing or GeoTIFF (.tif/.tiff) orthophoto.")

    file_content = await file.read()
    file_size = len(file_content)
    md5_hash = compute_md5(file_content)

    # 1. Establish persistent uploads directory
    uploads_dir = UPLOADS_DIR
    os.makedirs(uploads_dir, exist_ok=True)

    session_id = str(uuid.uuid4())
    file_ext = os.path.splitext(file.filename)[1]
    saved_filename = f"{session_id}{file_ext}"
    saved_filepath = os.path.join(uploads_dir, saved_filename)

    # Write file to disk
    with open(saved_filepath, "wb") as f:
        f.write(file_content)

    # 2. Write lineage metadata directly to Postgres database
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if file has already been uploaded (MD5 collision check)
        cursor.execute("SELECT session_id, file_name FROM gis_app_uploadedfile WHERE md5_checksum = %s", (md5_hash,))
        collision = cursor.fetchone()
        if collision:
            # We allow it, but note it in the survey notes
            notes = f"[WARNING: MD5 duplicate of {collision[1]} in session {collision[0]}] " + notes

        now = datetime.utcnow()

        # Insert Survey Session record
        cursor.execute(
            """
            INSERT INTO gis_app_surveysession (id, session_type, status, notes, created_at, uploaded_by_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (session_id, session_type, 'STAGED', notes, now, user_id)
        )

        # Insert Uploaded File record
        file_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO gis_app_uploadedfile (id, session_id, file_name, file_size, md5_checksum, file_path, uploaded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (file_id, session_id, file.filename, file_size, md5_hash, saved_filepath, now)
        )

        conn.commit()
    except Exception as e:
        conn.rollback()
        # Clean up saved file
        if os.path.exists(saved_filepath):
            os.remove(saved_filepath)
        raise HTTPException(status_code=500, detail=f"Database record creation failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()

    # 3. Enqueue parsing/tiling job to Redis/Celery queue
    task_name = (
        "gis_app.tasks.process_orthophoto_import"
        if session_type == 'IMAGERY'
        else "gis_app.tasks.process_survey_import"
    )
    
    if celery_app is not None:
        last_err = None
        for attempt in range(3):
            try:
                celery_app.send_task(task_name, args=[session_id, saved_filepath])
                print(f"✅ Task {task_name} queued for session {session_id} (attempt {attempt + 1})")
                last_err = None
                break
            except Exception as cel_err:
                last_err = cel_err
                print(f"⚠️ Celery send_task attempt {attempt + 1} failed: {cel_err}")
                if attempt < 2:
                    time.sleep(min(2 ** attempt, 10))
        if last_err is not None:
            print(f"❌ Celery error after 3 attempts: {last_err}")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE gis_app_surveysession SET status = 'ERROR' WHERE id = %s", (session_id,))
            conn.commit()
            cursor.close()
            conn.close()
            raise HTTPException(status_code=500, detail=f"Failed to queue background task after retries: {str(last_err)}")
    else:
        # Fallback: mark as processed
        print("⚠️ Celery not available - file saved but no background processing")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE gis_app_surveysession SET status = 'PROCESSED' WHERE id = %s", (session_id,))
        conn.commit()
        cursor.close()
        conn.close()

    return {
        "status": "QUEUED" if celery_app is not None else "PROCESSED",
        "survey_session_id": session_id,
        "session_type": session_type,
        "filename": file.filename,
        "md5_checksum": md5_hash,
        "file_size_bytes": file_size
    }

@app.get("/import/status/{session_id}")
def get_import_status(session_id: str):
    """Return the processing status, job details, and per-layer staging counts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, session_type, status, notes, created_at, approved_at
            FROM gis_app_surveysession
            WHERE id = %s
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")

        cursor.execute(
            """
            SELECT status, log_output, started_at, completed_at
            FROM gis_app_processingjob
            WHERE session_id = %s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (session_id,),
        )
        job_row = cursor.fetchone()
        job_info = None
        if job_row:
            job_info = {
                "status": job_row[0],
                "log_output": job_row[1],
                "started_at": job_row[2],
                "completed_at": job_row[3],
            }

        staging_tables = [
            "stagingroad", "stagingbuilding", "staginglanduse", "stagingfacility",
            "stagingstreetlight", "stagingwaterline", "stagingwaternode",
            "stagingsewerline", "stagingmanhole", "stagingsewerjunction",
            "stagingelectricalline", "stagingelectricalnode",
            "stagingfiberline", "stagingfibernode",
        ]
        staged_counts = {}
        for table in staging_tables:
            cursor.execute(
                f"SELECT COUNT(*) FROM gis_app_{table} WHERE session_id = %s",
                (session_id,),
            )
            staged_counts[table.replace("staging", "")] = cursor.fetchone()[0]

        return {
            "survey_session_id": row[0],
            "session_type": row[1],
            "status": row[2],
            "notes": row[3],
            "created_at": row[4],
            "approved_at": row[5],
            "job": job_info,
            "staged_counts": staged_counts,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status lookup failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()

@app.get("/health/")
def health_check():
    return {"status": "healthy", "service": "import_service", "celery": celery_app is not None}
