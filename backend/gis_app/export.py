"""
Lightweight data export service for WebGIS platform.
Supports GeoJSON, CSV, and Shapefile formats without heavy dependencies.
"""
import json
import csv
import io
import zipfile
from django.contrib.gis.geos import GEOSGeometry
from django.db import models


class DataExporter:
    """Export GIS data in various formats."""
    
    LAYER_MAP = {
        'roads': {
            'model': 'gis_app.Road',
            'fields': ['id', 'asset_code', 'road_name', 'road_code', 'surface_type', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'LineString'
        },
        'buildings': {
            'model': 'gis_app.Building',
            'fields': ['id', 'asset_code', 'building_code', 'house_name', 'building_type', 'usage', 'floors', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'Polygon'
        },
        'facilities': {
            'model': 'gis_app.Facility',
            'fields': ['id', 'asset_code', 'name', 'category_old', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'Point'
        },
        'land_use': {
            'model': 'gis_app.LandUseZone',
            'fields': ['id', 'asset_code', 'zone_name', 'zone_type', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'Polygon'
        },
        'street_lights': {
            'model': 'gis_app.StreetLight',
            'fields': ['id', 'asset_code', 'light_type', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'Point'
        },
        'water_lines': {
            'model': 'gis_app.WaterLine',
            'fields': ['id', 'asset_code', 'line_type', 'diameter', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'LineString'
        },
        'sewer_lines': {
            'model': 'gis_app.SewerLine',
            'fields': ['id', 'asset_code', 'line_type', 'diameter', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'LineString'
        },
        'electrical_lines': {
            'model': 'gis_app.ElectricalLine',
            'fields': ['id', 'asset_code', 'line_type', 'voltage', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'LineString'
        },
        'fiber_lines': {
            'model': 'gis_app.FiberLine',
            'fields': ['id', 'asset_code', 'provider', 'core_count', 'status'],
            'geometry_field': 'geometry',
            'geometry_type': 'LineString'
        },
    }
    
    def __init__(self, layer, fmt='geojson', filters=None, bbox=None, user=None):
        self.layer = layer
        self.fmt = fmt
        self.filters = filters or {}
        self.bbox = bbox
        self.user = user
        
        if layer not in self.LAYER_MAP:
            raise ValueError(f"Unsupported layer: {layer}. Valid: {list(self.LAYER_MAP.keys())}")
        
        self.config = self.LAYER_MAP[layer]
        
        # Import model lazily
        from django.apps import apps
        self.model = apps.get_model(self.config['model'])
    
    def get_queryset(self):
        """Build queryset with filters."""
        qs = self.model.objects.all()
        
        # Apply field filters
        if self.filters:
            qs = qs.filter(**self.filters)
        
        # Apply bbox filter (spatial intersection)
        if self.bbox and hasattr(self.model, self.config['geometry_field']):
            from django.contrib.gis.geos import Polygon
            min_lon, min_lat, max_lon, max_lat = self.bbox
            bbox_poly = Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat))
            geom_field = self.config['geometry_field']
            qs = qs.filter(**{f'{geom_field}__intersects': bbox_poly})
        
        return qs
    
    def export(self):
        """Main export method - returns (data, content_type, extension)."""
        qs = self.get_queryset()
        
        if self.fmt == 'geojson':
            return self._export_geojson(qs)
        elif self.fmt == 'csv':
            return self._export_csv(qs)
        elif self.fmt == 'shapefile':
            return self._export_shapefile(qs)
        else:
            raise ValueError(f"Unsupported format: {self.fmt}")
    
    def _export_geojson(self, qs):
        """Export as GeoJSON FeatureCollection."""
        features = []
        
        for obj in qs:
            geom = getattr(obj, self.config['geometry_field'], None)
            
            # Build properties
            properties = {}
            for field in self.config['fields']:
                if field == 'id':
                    continue  # Skip Django's auto ID in properties
                value = getattr(obj, field, None)
                if isinstance(value, models.Model):
                    value = str(value)
                elif hasattr(value, 'isoformat'):
                    value = value.isoformat()
                properties[field] = value
            
            # Build feature
            feature = {
                'type': 'Feature',
                'id': str(obj.pk),
                'properties': properties,
            }
            
            if geom:
                feature['geometry'] = json.loads(geom.geojson)
            else:
                feature['geometry'] = None
            
            features.append(feature)
        
        geojson = {
            'type': 'FeatureCollection',
            'features': features,
            'metadata': {
                'layer': self.layer,
                'count': len(features),
                'format': 'geojson'
            }
        }
        
        return json.dumps(geojson), 'application/geo+json', 'geojson'
    
    def _export_csv(self, qs):
        """Export as CSV with WKT geometry."""
        output = io.StringIO()
        
        # Build headers
        headers = ['id'] + [f for f in self.config['fields'] if f != 'id'] + ['wkt_geometry', 'geometry_type']
        writer = csv.writer(output)
        writer.writerow(headers)
        
        for obj in qs:
            row = [str(obj.pk)]
            
            for field in self.config['fields']:
                if field == 'id':
                    continue
                value = getattr(obj, field, None)
                if isinstance(value, models.Model):
                    value = str(value)
                elif hasattr(value, 'isoformat'):
                    value = value.isoformat()
                row.append(value)
            
            # Add WKT geometry
            geom = getattr(obj, self.config['geometry_field'], None)
            if geom:
                row.append(geom.wkt)
                row.append(geom.geom_type)
            else:
                row.append('')
                row.append('')
            
            writer.writerow(row)
        
        return output.getvalue(), 'text/csv', 'csv'
    
    def _export_shapefile(self, qs):
        """Export as Shapefile (zipped)."""
        # Use Django's built-in shapefile support via GDAL if available
        # Fallback: generate a minimal shapefile manually
        
        try:
            from osgeo import ogr, osr
            return self._export_shapefile_osgeo(qs)
        except ImportError:
            # Fallback to manual shapefile creation
            return self._export_shapefile_manual(qs)
    
    def _export_shapefile_osgeo(self, qs):
        """Export using GDAL/OGR (more reliable)."""
        from osgeo import ogr, osr
        
        # Create in-memory datasource
        driver = ogr.GetDriverByName('ESRI Shapefile')
        ds = driver.CreateDataSource('/vsimem/temp.shp')
        
        # Create spatial reference
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32643)  # UTM Zone 43N
        
        # Determine geometry type
        geom_type_map = {
            'Point': ogr.wkbPoint,
            'LineString': ogr.wkbLineString,
            'Polygon': ogr.wkbPolygon,
            'MultiPolygon': ogr.wkbMultiPolygon,
        }
        geom_type = geom_type_map.get(self.config['geometry_type'], ogr.wkbPoint)
        
        # Create layer
        layer = ds.CreateLayer('export', srs, geom_type)
        
        # Add fields
        for field in self.config['fields']:
            if field == 'id':
                layer.CreateField(ogr.FieldDefn('id', ogr.OFTString))
            else:
                layer.CreateField(ogr.FieldDefn(field, ogr.OFTString))
        
        # Add features
        for obj in qs:
            feature = ogr.Feature(layer.GetLayerDefn())
            
            # Set attributes
            for field in self.config['fields']:
                value = getattr(obj, field, '')
                if isinstance(value, models.Model):
                    value = str(value)
                elif hasattr(value, 'isoformat'):
                    value = value.isoformat()
                feature.SetField(field, str(value) if value else '')
            
            # Set geometry
            geom = getattr(obj, self.config['geometry_field'], None)
            if geom:
                geom_wkt = geom.wkt
                ogr_geom = ogr.CreateGeometryFromWkt(geom_wkt)
                feature.SetGeometry(ogr_geom)
            
            layer.CreateFeature(feature)
            feature = None
        
        # Save to memory
        ds.FlushCache()
        
        # Read all files into a zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Read shapefile components from /vsimem/
            for ext in ['shp', 'shx', 'dbf', 'prj']:
                vsimem_path = f'/vsimem/temp.{ext}'
                try:
                    f = gdal.Open(vsimem_path)
                    if f:
                        data = f.ReadAsBytes()
                        zf.writestr(f'export.{ext}', data)
                        f = None
                except:
                    pass
        
        ds = None
        zip_buffer.seek(0)
        
        return zip_buffer, 'application/zip', 'zip'
    
    def _export_shapefile_manual(self, qs):
        """Export as shapefile without GDAL (minimal implementation)."""
        # For simplicity, export as CSV with geometry
        # Full shapefile requires pyshp or similar
        csv_data, _, _ = self._export_csv(qs)
        
        # Zip the CSV as a workaround
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f'{self.layer}.csv', csv_data)
            zf.writestr('README.txt', 
                'Shapefile export requires GDAL/OGR.\n'
                'The CSV file contains all data with WKT geometry.\n'
                'Import into QGIS: Layer > Add Layer > Add Delimited Text Layer\n'
            )
        
        zip_buffer.seek(0)
        return zip_buffer, 'application/zip', 'zip'


def get_supported_layers():
    """Return list of supported export layers."""
    return list(DataExporter.LAYER_MAP.keys())


def get_supported_formats():
    """Return list of supported export formats."""
    return ['geojson', 'csv', 'shapefile']
