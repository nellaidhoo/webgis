"""
Data validation framework for WebGIS platform.
Validates geometry, asset codes, and other data quality rules.
"""
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import GEOSGeometry
import re


class GeometryValidator:
    """Validate geometry properties."""
    
    def __init__(self, min_vertices=2, max_vertices=1000, min_length=0.1, min_area=0.1):
        self.min_vertices = min_vertices
        self.max_vertices = max_vertices
        self.min_length = min_length
        self.min_area = min_area
    
    def validate_linestring(self, geom, field_name='geometry'):
        """Validate a LineString geometry."""
        errors = []
        
        if not geom.valid:
            errors.append(f"Invalid {field_name}: {geom.valid_reason}")
        
        if geom.num_coords < self.min_vertices:
            errors.append(f"{field_name} has too few vertices: {geom.num_coords} < {self.min_vertices}")
        
        if geom.num_coords > self.max_vertices:
            errors.append(f"{field_name} has too many vertices: {geom.num_coords} > {self.max_vertices}")
        
        if hasattr(geom, 'length') and geom.length < self.min_length:
            errors.append(f"{field_name} is too short: {geom.length:.2f}m < {self.min_length}m")
        
        return errors
    
    def validate_polygon(self, geom, field_name='geometry'):
        """Validate a Polygon geometry."""
        errors = []
        
        if not geom.valid:
            errors.append(f"Invalid {field_name}: {geom.valid_reason}")
        
        if geom.num_coords < self.min_vertices:
            errors.append(f"{field_name} has too few vertices: {geom.num_coords} < {self.min_vertices}")
        
        if geom.num_coords > self.max_vertices:
            errors.append(f"{field_name} has too many vertices: {geom.num_coords} > {self.max_vertices}")
        
        if hasattr(geom, 'area') and geom.area < self.min_area:
            errors.append(f"{field_name} area is too small: {geom.area:.2f} < {self.min_area}")
        
        return errors
    
    def validate_point(self, geom, field_name='geometry'):
        """Validate a Point geometry."""
        errors = []
        
        if not geom.valid:
            errors.append(f"Invalid {field_name}: {geom.valid_reason}")
        
        return errors
    
    def validate_coordinates_in_maldives(self, geom, allowed_srid=32643):
        """Validate that coordinates are within Maldives bounds."""
        errors = []
        
        if geom.srid != allowed_srid:
            errors.append(f"Geometry SRID {geom.srid} != expected {allowed_srid}")
        
        # Maldives rough bounds in UTM Zone 43N
        bounds = geom.envelope
        if hasattr(bounds, 'xmin'):
            if not (50000 < bounds.xmin < 1000000 and 0 < bounds.ymin < 2000000):
                errors.append("Coordinates outside Maldives UTM zone bounds")
        
        return errors


class AssetCodeValidator:
    """Validate asset code formats."""
    
    PATTERNS = {
        'road': r'^(R|ROAD)-[A-Z0-9-]+$',
        'building': r'^(B|BLDG)-[A-Z0-9-]+$',
        'facility': r'^(F|FAC)-[A-Z0-9-]+$',
        'street_light': r'^SL-[A-Z0-9-]+$',
        'water_line': r'^(WL|WLINE)-[A-Z0-9-]+$',
        'sewer_line': r'^(SW|SLINE)-[A-Z0-9-]+$',
        'electrical_line': r'^(EL|ELINE)-[A-Z0-9-]+$',
        'fiber_line': r'^(FL|FLINE)-[A-Z0-9-]+$',
    }
    
    def validate(self, asset_code, asset_type):
        """Validate an asset code."""
        if asset_type not in self.PATTERNS:
            return []  # No pattern defined, skip validation
        
        pattern = re.compile(self.PATTERNS[asset_type], re.IGNORECASE)
        if not pattern.match(asset_code):
            return [f"Invalid {asset_type} asset code format: {asset_code}"]
        return []


class DataValidator:
    """Main data validator combining all validators."""
    
    def __init__(self):
        self.geometry_validator = GeometryValidator()
        self.asset_code_validator = AssetCodeValidator()
    
    def validate_road(self, road):
        """Validate a Road object."""
        errors = []
        
        # Geometry validation
        if road.geometry:
            errors.extend(self.geometry_validator.validate_linestring(road.geometry, 'geometry'))
            errors.extend(self.geometry_validator.validate_coordinates_in_maldives(road.geometry))
        
        # Asset code validation
        if road.asset_code:
            errors.extend(self.asset_code_validator.validate(road.asset_code, 'road'))
        
        return errors
    
    def validate_building(self, building):
        """Validate a Building object."""
        errors = []
        
        # Geometry validation
        if building.geometry:
            errors.extend(self.geometry_validator.validate_polygon(building.geometry, 'geometry'))
            errors.extend(self.geometry_validator.validate_coordinates_in_maldives(building.geometry))
        
        # Asset code validation
        if building.asset_code:
            errors.extend(self.asset_code_validator.validate(building.asset_code, 'building'))
        
        return errors
    
    def validate_facility(self, facility):
        """Validate a Facility object."""
        errors = []
        
        # Geometry validation
        if facility.geometry:
            errors.extend(self.geometry_validator.validate_point(facility.geometry, 'geometry'))
            errors.extend(self.geometry_validator.validate_coordinates_in_maldives(facility.geometry))
        
        # Asset code validation
        if facility.asset_code:
            errors.extend(self.asset_code_validator.validate(facility.asset_code, 'facility'))
        
        return errors

    def _validate_geometry_generic(self, geom):
        """Dispatch to the geometry validator by geometry type."""
        if geom is None:
            return []
        geom_type = getattr(geom, 'geom_type', '')
        if geom_type in ('Polygon', 'MultiPolygon'):
            return self.geometry_validator.validate_polygon(geom, 'geometry')
        if geom_type in ('LineString', 'MultiLineString'):
            return self.geometry_validator.validate_linestring(geom, 'geometry')
        if geom_type in ('Point', 'MultiPoint'):
            return self.geometry_validator.validate_point(geom, 'geometry')
        return []

    def validate_feature(self, feature, asset_type=None):
        """
        Validate a single (staged or production) feature generically.
        Works for every layer: uses the query-set geometry type to pick the
        right geometry rules and validates the asset code when a pattern
        exists for `asset_type`.
        """
        errors = []
        geom = getattr(feature, 'geometry', None)
        if geom is not None:
            errors.extend(self._validate_geometry_generic(geom))
            errors.extend(self.geometry_validator.validate_coordinates_in_maldives(geom))
        asset_code = getattr(feature, 'asset_code', None)
        if asset_code and asset_type:
            errors.extend(self.asset_code_validator.validate(asset_code, asset_type))
        return errors


# Global validator instance
validator = DataValidator()
