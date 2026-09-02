import os
import uuid
import traceback
import json
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.contrib.gis.geos import GEOSGeometry, Point as GeosPoint, LineString as GeosLineString, Polygon as GeosPolygon
from django.contrib.auth.models import User
from django.conf import settings
import ezdxf
from shapely.geometry import shape, Point as ShapelyPoint, LineString as ShapelyLineString, Polygon as ShapelyPolygon
from shapely.validation import make_valid
from pyproj import Transformer

from .models import (
    SurveySession, ProcessingJob, UploadedFile,
    StagingRoad, StagingBuilding, StagingLandUse, StagingFacility,
    StagingStreetLight, StagingWaterLine, StagingWaterNode, StagingSewerLine,
    StagingManhole, StagingSewerJunction, StagingElectricalLine, StagingElectricalNode,
    StagingFiberLine, StagingFiberNode
)
from .tile_pipeline import process_orthophoto

# Project coordinates to storage coordinate standard EPSG:32643
def reproject_geometry(geom_obj, from_srid=4326, to_srid=4326):
    """
    Reproject a django GEOSGeometry between coordinate reference systems.
    Default: convert to WGS84 (EPSG:4326) for map display
    """
    # If already in target SRID, return as-is
    if geom_obj.srid == to_srid:
        return geom_obj
    
    try:
        # Try GEOS transform first
        geom_obj.transform(to_srid)
        return geom_obj
    except Exception as e:
        # Fallback using pyproj
        try:
            transformer = Transformer.from_crs(f"EPSG:{from_srid}", f"EPSG:{to_srid}", always_xy=True)
            
            if geom_obj.geom_type == 'Point':
                x, y = transformer.transform(geom_obj.x, geom_obj.y)
                return GeosPoint(x, y, srid=to_srid)
            elif geom_obj.geom_type == 'LineString':
                coords = [transformer.transform(x, y) for x, y in geom_obj.coords]
                return GeosLineString(coords, srid=to_srid)
            elif geom_obj.geom_type == 'Polygon':
                # Handle outer boundary
                outer_coords = [transformer.transform(x, y) for x, y in geom_obj.exterior.coords]
                # Handle holes
                holes = []
                for ring in geom_obj.interiors:
                    holes.append([transformer.transform(x, y) for x, y in ring.coords])
                return GeosPolygon(outer_coords, *holes, srid=to_srid)
            else:
                raise e
        except Exception as pyproj_err:
            print(f"Reprojection failed: {pyproj_err}")
            return geom_obj

@shared_task(name="gis_app.tasks.process_survey_import")
def process_survey_import(session_id, file_path):
    """
    Background worker task to parse, validate, and stage DXF survey files.
    """
    # Create processing job record or find existing
    session = SurveySession.objects.get(id=session_id)
    job = ProcessingJob.objects.create(session=session, status='PROCESSING', started_at=timezone.now())
    
    session.status = 'PROCESSING'
    session.save()

    logs = []
    def log(msg):
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        logs.append(f"[{timestamp}] {msg}")
        print(msg)

    try:
        log(f"Starting ingestion process for session {session_id}")
        log(f"Reading file from path: {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        # Check if DXF
        if file_path.lower().endswith('.dxf'):
            parse_dxf(file_path, session, log)
        else:
            raise ValueError("Unsupported file format. Only DXF is supported in this pipeline.")

        job.status = 'SUCCESS'
        job.completed_at = timezone.now()
        job.log_output = "\n".join(logs)
        job.save()

        session.status = 'COMPLETED'
        session.save()
        log("Ingestion successfully completed!")

    except Exception as e:
        tb = traceback.format_exc()
        log(f"CRITICAL ERROR: {str(e)}")
        log("Stack trace:")
        log(tb)

        job.status = 'FAILED'
        job.completed_at = timezone.now()
        job.log_output = "\n".join(logs)
        job.save()

        session.status = 'ERROR'
        session.save()

@shared_task(name="gis_app.tasks.process_orthophoto_import")
def process_orthophoto_import(session_id, file_path):
    """
    Background worker task that converts a drone GeoTIFF into an XYZ tile
    package under /opt/webgis/tiles/<session_id> using the gdal tile pipeline.
    """
    session = SurveySession.objects.get(id=session_id)
    job = ProcessingJob.objects.create(session=session, status='PROCESSING', started_at=timezone.now())

    session.status = 'PROCESSING'
    session.save()

    logs = []
    def log(msg):
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        logs.append(f"[{timestamp}] {msg}")
        print(msg)

    try:
        log(f"Starting orthophoto ingestion for session {session_id}")
        log(f"Reading GeoTIFF from path: {file_path}")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        output_dir = os.path.join(settings.TILES_DIR, str(session_id))
        process_orthophoto(file_path, output_dir)

        job.status = 'SUCCESS'
        job.completed_at = timezone.now()
        job.log_output = "\n".join(logs)
        job.save()

        session.status = 'COMPLETED'
        session.save()
        log(f"Orthophoto tiles exported to: {output_dir}")

    except Exception as e:
        tb = traceback.format_exc()
        log(f"CRITICAL ERROR: {str(e)}")
        log("Stack trace:")
        log(tb)

        job.status = 'FAILED'
        job.completed_at = timezone.now()
        job.log_output = "\n".join(logs)
        job.save()

        session.status = 'ERROR'
        session.save()

def parse_dxf(file_path, session, log_fn):
    """
    Parses DXF entities and categorizes them into staging tables.
    Supports auto-detection of facility categories from layer/block names.
    """
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    
    # 1. Detect CRS and ensure we convert to WGS84 (EPSG:4326)
    source_srid = 32643  # Default: UTM Zone 43N
    target_srid = 4326   # Target: WGS84 for map display

    test_points = list(msp.query('POINT'))
    if test_points:
        p = test_points[0].dxf.location
        if -180 <= p.x <= 180 and -90 <= p.y <= 90:
            source_srid = 4326
            log_fn("Coordinates detected as lat/lng (WGS84). Source CRS: EPSG:4326.")
        else:
            log_fn(f"Coordinates detected as projected grid. Source CRS: EPSG:{source_srid}.")
    else:
        # Check from limits
        limmin = doc.header.get('$LIMMIN', (0, 0))
        if -180 <= limmin[0] <= 180 and -90 <= limmin[1] <= 90:
            source_srid = 4326
            log_fn("Drawing limits indicate lat/lng coordinates. Source CRS: EPSG:4326.")
        else:
            log_fn(f"Drawing limits indicate projected grid coordinates. Source CRS: EPSG:{source_srid}.")

    log_fn(f"Will reproject all geometries to EPSG:{target_srid} (WGS84) for map display.")
    
    # 2. Extract Text entities for spatial attribute mapping
    text_entities = []
    for text in msp.query('TEXT MTEXT'):
        text_entities.append({
            'text': text.dxf.text.strip(),
            'location': ShapelyPoint(text.dxf.insert.x, text.dxf.insert.y)
        })
    log_fn(f"Indexed {len(text_entities)} text labels for attribute associations.")
    
    def get_facility_category(layer_name, block_name=None):
        """
        Auto-detect facility category from layer or block name
        """
        from .models import FacilityCategory
        
        # Try to find by layer name
        if layer_name:
            # Check if layer name contains a category code
            for category in FacilityCategory.objects.filter(is_active=True):
                if category.code in layer_name.upper():
                    return category
        
        # Try to find by block name
        if block_name:
            for category in FacilityCategory.objects.filter(is_active=True):
                if category.code == block_name.upper():
                    return category
        
        # Default: return None (will be uncategorized)
        return None
    
    def parse_fiber_provider(layer_name):
        """
        Derive the fiber service provider from the DXF layer-name suffix.
        Layers are named FIBER_LINE or FIBER_LINE_<PROVIDER> (e.g. FIBER_LINE_RAE).
        Unknown/absent providers return '' so the map uses a neutral style.
        """
        name = (layer_name or '').strip()
        if name.upper().startswith('FIBER_LINE'):
            suffix = name[len('FIBER_LINE'):]
        else:
            suffix = name
        return suffix.strip(' _-')[:100]

    def find_nearest_text(geom, max_distance=3.0):
        """Helper to find text labels within threshold of geometry"""
        try:
            shapely_geom = shape(json.loads(geom.geojson)) if hasattr(geom, 'geojson') else geom
            best_label = None
            best_dist = max_distance
            for t in text_entities:
                dist = shapely_geom.distance(t['location'])
                if dist < best_dist:
                    best_dist = dist
                    best_label = t['text']
            return best_label
        except Exception:
            return None

    # Helper to count records created
    counts = {}
    def inc_count(table_name):
        counts[table_name] = counts.get(table_name, 0) + 1

    # Helper to mint a unique asset code
    def gen_code(prefix):
        return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

    # 3. Process Entities
    with transaction.atomic():
        for entity in msp:
            layer = entity.dxf.layer.upper()
            etype = entity.dxftype()
            
            # Skip if not one of our target layers
            target_prefixes = [
                'BLDG', 'ROAD', 'LAND_USE', 'FACILITY', 'SL',
                'WATER_LINE', 'WATER_NODE', 'SEWER_LINE', 'MANHOLE',
                'SEWER_JUNCTION', 'ELECTRICAL_LINE', 'ELECTRICAL_NODE',
                'FIBER_LINE', 'FIBER_NODE',
                'PL', 'BUILDING LINE', 'DRAFT', 'DRAFTLINE',  # Add these layers
                '0-DRAFT LINES', 'PLANTIN DRAFT', 'A-ADDRESS', 'HOUSING UNITS'
            ]
            if not any(layer.startswith(prefix) for prefix in target_prefixes):
                continue

            geom = None

            try:
                # Extract coordinates based on entity type
                if etype == 'POINT':
                    coords = (entity.dxf.location.x, entity.dxf.location.y)
                    geom = GeosPoint(coords[0], coords[1], srid=source_srid)
                elif etype in ['LINE']:
                    coords = [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
                    geom = GeosLineString(coords, srid=source_srid)
                elif etype in ['LWPOLYLINE', 'POLYLINE']:
                    # IMPORTANT: Extract only X,Y, ignore Z (elevation)
                    vertices = [(p[0], p[1]) for p in entity.get_points()]
                    if len(vertices) < 2:
                        continue
                    
                    if entity.is_closed and len(vertices) >= 3:
                        if vertices[0] != vertices[-1]:
                            vertices.append(vertices[0])
                        geom = GeosPolygon(vertices, srid=source_srid)
                    else:
                        geom = GeosLineString(vertices, srid=source_srid)
                else:
                    continue

                if geom is None:
                    continue

                # Reproject to WGS84 (EPSG:4326) for map display
                geom_projected = reproject_geometry(geom, from_srid=source_srid, to_srid=4326)

                # Convert to shapely for topology check
                shapely_geom = make_valid(shape(json.loads(geom_projected.geojson)))
                if not shapely_geom.is_valid:
                    log_fn(f"Skipping invalid geometry on layer {layer}")
                    continue

                # Recreate clean Django geometry from valid shapely (now in WGS84)
                geom_final = GEOSGeometry(shapely_geom.wkt, srid=4326)

                # --- BUILDINGS ---
                if layer.startswith('BLDG') and geom_final.geom_type == 'Polygon':
                    code = find_nearest_text(shapely_geom) or f"BLDG-{uuid.uuid4().hex[:6].upper()}"
                    StagingBuilding.objects.create(
                        session=session,
                        asset_code=gen_code('BLDG'),
                        building_code=code,
                        house_name=find_nearest_text(shapely_geom, max_distance=6.0) or "",
                        building_type="Residential",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path),
                        accuracy=0.1
                    )
                    inc_count('buildings')

                # --- ROADS ---
                elif layer.startswith('ROAD') and geom_final.geom_type == 'LineString':
                    code = find_nearest_text(shapely_geom) or f"ROAD-{uuid.uuid4().hex[:6].upper()}"
                    StagingRoad.objects.create(
                        session=session,
                        asset_code=gen_code('ROAD'),
                        road_code=code,
                        road_name=find_nearest_text(shapely_geom, max_distance=5.0) or "Unnamed Road",
                        surface_type="Asphalt",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path),
                        accuracy=0.2
                    )
                    inc_count('roads')

                # --- LAND USE ---
                elif (layer.startswith('LAND_USE') or 
                    layer == 'PL' or 
                    layer == 'pl' or 
                    layer == 'Building Line' or
                    layer == 'Draft' or
                    layer == '0-Draft Lines' or
                    layer == 'Plantin Draft') and geom_final.geom_type == 'Polygon':
                    
                    # Try to get zone name from nearby text
                    zone_name = find_nearest_text(shapely_geom, max_distance=10.0) or f"Zone on {layer}"
                    zone_class = "Residential"  # Default
                    
                    # Try to detect zone class from layer or text
                    layer_upper = layer.upper()
                    if 'RESIDENTIAL' in zone_name.upper() or 'RES' in zone_name.upper():
                        zone_class = "Residential"
                    elif 'COMMERCIAL' in zone_name.upper() or 'COM' in zone_name.upper():
                        zone_class = "Commercial"
                    elif 'CONSERVATION' in zone_name.upper() or 'CONS' in zone_name.upper():
                        zone_class = "Conservation"
                    elif 'INDUSTRIAL' in zone_name.upper() or 'IND' in zone_name.upper():
                        zone_class = "Industrial"
                    
                    StagingLandUse.objects.create(
                        session=session,
                        asset_code=gen_code('ZONE'),
                        zone_class=zone_class,
                        zone_name=zone_name,
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('land_use')
                    log_fn(f"  Land use polygon on {layer}: {zone_name} ({zone_class})")

                # --- FACILITIES (with Category Support!) ---
                elif layer.startswith('FACILITY') and geom_final.geom_type == 'Point':
                    # Get the facility name from text or layer
                    facility_name = find_nearest_text(shapely_geom) or f"Facility on {layer}"
                    
                    # Try to get category from layer name
                    category = get_facility_category(layer)
                    
                    StagingFacility.objects.create(
                        session=session,
                        asset_code=gen_code('FAC'),
                        name=facility_name,
                        category=category,  # ForeignKey to FacilityCategory ✅
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('facilities')

                # --- STREET LIGHTS ---
                elif layer.startswith('SL') and geom_final.geom_type == 'Point':
                    StagingStreetLight.objects.create(
                        session=session,
                        asset_code=gen_code('SL'),
                        light_type="LED",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('street_lights')

                # --- UTILITIES: WATER ---
                elif layer.startswith('WATER_LINE') and geom_final.geom_type == 'LineString':
                    StagingWaterLine.objects.create(
                        session=session,
                        asset_code=gen_code('WLINE'),
                        diameter_mm=110,
                        pipe_material="HDPE",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('water_lines')

                elif layer.startswith('WATER_NODE') and geom_final.geom_type == 'Point':
                    StagingWaterNode.objects.create(
                        session=session,
                        asset_code=gen_code('WNODE'),
                        node_type="Valve",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('water_nodes')

                # --- UTILITIES: SEWER ---
                elif layer.startswith('SEWER_LINE') and geom_final.geom_type == 'LineString':
                    StagingSewerLine.objects.create(
                        session=session,
                        asset_code=gen_code('SLINE'),
                        diameter_mm=160,
                        pipe_material="uPVC",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('sewer_lines')

                elif layer.startswith('MANHOLE') and geom_final.geom_type == 'Point':
                    StagingManhole.objects.create(
                        session=session,
                        asset_code=gen_code('MH'),
                        depth_m=1.8,
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('manholes')

                elif layer.startswith('SEWER_JUNCTION') and geom_final.geom_type == 'Point':
                    StagingSewerJunction.objects.create(
                        session=session,
                        asset_code=gen_code('SJ'),
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('sewer_junctions')

                # --- UTILITIES: ELECTRICAL ---
                elif layer.startswith('ELECTRICAL_LINE') and geom_final.geom_type == 'LineString':
                    StagingElectricalLine.objects.create(
                        session=session,
                        asset_code=gen_code('ELINE'),
                        voltage="230V",
                        cable_type="Underground",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('electrical_lines')

                elif layer.startswith('ELECTRICAL_NODE') and geom_final.geom_type == 'Point':
                    StagingElectricalNode.objects.create(
                        session=session,
                        asset_code=gen_code('ENODE'),
                        node_type="DistributionBox",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('electrical_nodes')

                # --- UTILITIES: FIBER ---
                elif layer.startswith('FIBER_LINE') and geom_final.geom_type == 'LineString':
                    StagingFiberLine.objects.create(
                        session=session,
                        asset_code=gen_code('FLINE'),
                        provider=parse_fiber_provider(layer),
                        core_count=24,
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('fiber_lines')

                elif layer.startswith('FIBER_NODE') and geom_final.geom_type == 'Point':
                    StagingFiberNode.objects.create(
                        session=session,
                        asset_code=gen_code('FNODE'),
                        node_type="SpliceBox",
                        geometry=geom_final,
                        source_file=os.path.basename(file_path)
                    )
                    inc_count('fiber_nodes')

            except Exception as ent_err:
                log_fn(f"Error parsing entity of type {etype} on layer {layer}: {str(ent_err)}")
                continue

    # Final summary log
    log_fn(f"Ingestion staging summary:")
    for k, v in counts.items():
        log_fn(f" - {k}: {v} features staged.")
    log_fn(f"✅ All geometries stored in EPSG:4326 (WGS84) for map display.")