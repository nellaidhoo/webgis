-- Vector Tile Functions for PostGIS MVT
-- Run this migration to enable efficient vector tile serving

-- Function to generate MVT tiles for roads
CREATE OR REPLACE FUNCTION mvt_roads(z integer, x integer, y integer)
RETURNS bytea AS $$
DECLARE
    tile_bbox geometry;
    result bytea;
BEGIN
    -- Convert XYZ to Web Mercator bounding box
    tile_bbox := ST_TileEnvelope(z, x, y);
    
    SELECT ST_AsMVT(q, 'roads', 4096, 'geom')
    INTO result
    FROM (
        SELECT 
            id::text,
            road_name,
            road_code,
            surface_type,
            ST_AsMVTGeom(
                ST_Transform(geometry, 3857), 
                tile_bbox, 
                4096, 
                256, 
                true
            ) AS geom
        FROM gis_app_road
        WHERE ST_Intersects(
            ST_Transform(geometry, 3857),
            tile_bbox
        )
    ) q;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to generate MVT tiles for buildings
CREATE OR REPLACE FUNCTION mvt_buildings(z integer, x integer, y integer)
RETURNS bytea AS $$
DECLARE
    tile_bbox geometry;
    result bytea;
BEGIN
    tile_bbox := ST_TileEnvelope(z, x, y);
    
    SELECT ST_AsMVT(q, 'buildings', 4096, 'geom')
    INTO result
    FROM (
        SELECT 
            id::text,
            building_code,
            house_name,
            building_type,
            usage,
            floors,
            ST_AsMVTGeom(
                ST_Transform(geometry, 3857), 
                tile_bbox, 
                4096, 
                256, 
                true
            ) AS geom
        FROM gis_app_building
        WHERE ST_Intersects(
            ST_Transform(geometry, 3857),
            tile_bbox
        )
    ) q;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to generate MVT tiles for facilities
CREATE OR REPLACE FUNCTION mvt_facilities(z integer, x integer, y integer)
RETURNS bytea AS $$
DECLARE
    tile_bbox geometry;
    result bytea;
BEGIN
    tile_bbox := ST_TileEnvelope(z, x, y);
    
    SELECT ST_AsMVT(q, 'facilities', 4096, 'geom')
    INTO result
    FROM (
        SELECT 
            f.id::text,
            f.asset_code,
            f.name,
            f.category_old,
            fc.name as category_name,
            fc.color as category_color,
            ST_AsMVTGeom(
                ST_Transform(f.geometry, 3857), 
                tile_bbox, 
                4096, 
                256, 
                true
            ) AS geom
        FROM gis_app_facility f
        LEFT JOIN gis_app_facilitycategory fc ON f.category_id = fc.id
        WHERE ST_Intersects(
            ST_Transform(f.geometry, 3857),
            tile_bbox
        )
    ) q;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to generate MVT tiles for land use zones
CREATE OR REPLACE FUNCTION mvt_landuse(z integer, x integer, y integer)
RETURNS bytea AS $$
DECLARE
    tile_bbox geometry;
    result bytea;
BEGIN
    tile_bbox := ST_TileEnvelope(z, x, y);
    
    SELECT ST_AsMVT(q, 'landuse', 4096, 'geom')
    INTO result
    FROM (
        SELECT 
            id::text,
            zone_name,
            zone_type,
            ST_AsMVTGeom(
                ST_Transform(geometry, 3857), 
                tile_bbox, 
                4096, 
                256, 
                true
            ) AS geom
        FROM gis_app_landusezone
        WHERE ST_Intersects(
            ST_Transform(geometry, 3857),
            tile_bbox
        )
    ) q;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function to generate MVT tiles for utility networks (combined)
CREATE OR REPLACE FUNCTION mvt_utilities(z integer, x integer, y integer)
RETURNS bytea AS $$
DECLARE
    tile_bbox geometry;
    result bytea;
BEGIN
    tile_bbox := ST_TileEnvelope(z, x, y);
    
    SELECT ST_AsMVT(q, 'utilities', 4096, 'geom')
    INTO result
    FROM (
        SELECT 
            'street_light' as utility_type,
            asset_code,
            ST_AsMVTGeom(
                ST_Transform(geometry, 3857), 
                tile_bbox, 
                4096, 
                256, 
                true
            ) AS geom
        FROM gis_app_streetlight
        WHERE ST_Intersects(ST_Transform(geometry, 3857), tile_bbox)
        
        UNION ALL
        
        SELECT 
            'water_line' as utility_type,
            asset_code,
            ST_AsMVTGeom(
                ST_Transform(geometry, 3857), 
                tile_bbox, 
                4096, 
                256, 
                true
            ) AS geom
        FROM gis_app_waterline
        WHERE ST_Intersects(ST_Transform(geometry, 3857), tile_bbox)
        
        UNION ALL
        
        SELECT 
            'electrical_line' as utility_type,
            asset_code,
            ST_AsMVTGeom(
                ST_Transform(geometry, 3857), 
                tile_bbox, 
                4096, 
                256, 
                true
            ) AS geom
        FROM gis_app_electricalline
        WHERE ST_Intersects(ST_Transform(geometry, 3857), tile_bbox)
    ) q;
    
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;
