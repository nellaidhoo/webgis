import json
from rest_framework import serializers
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.auth.models import User
from .models import (
    SurveySession, UploadedFile, ProcessingJob, ApprovalHistory,
    Road, Building, Address, LandUse, Facility,
    StreetLight, WaterLine, WaterNode, SewerLine, Manhole, SewerJunction,
    ElectricalLine, ElectricalNode, FiberLine, FiberNode, AuditLog,
    StagingRoad, StagingBuilding, StagingLandUse, StagingFacility,
    StagingStreetLight, StagingWaterLine, StagingWaterNode, StagingSewerLine,
    StagingManhole, StagingSewerJunction, StagingElectricalLine, StagingElectricalNode,
    StagingFiberLine, StagingFiberNode, SurveyValidationReport
)

# Custom field to handle GeoDjango geometry fields seamlessly in DRF
class GeometrySerializerField(serializers.Field):
    def to_representation(self, value):
        if value is None:
            return None
        # Geometries are stored in EPSG:32643 (UTM 43N).
        # We project them to EPSG:4326 (WGS 84) on the fly for API consumption.
        try:
            geom_4326 = value.transform(4326, clone=True)
            return json.loads(geom_4326.geojson)
        except Exception:
            # Fallback if projection fails
            return json.loads(value.geojson)

    def to_internal_value(self, data):
        if not data:
            return None
        try:
            # Convert incoming GeoJSON dictionary to GEOSGeometry object
            geom = GEOSGeometry(json.dumps(data))
            # If the incoming GeoJSON does not specify SRID, assume WGS 84 (4326)
            if geom.srid is None or geom.srid == 0:
                geom.srid = 4326
            # Reproject to our storage CRS: UTM Zone 43N (EPSG:32643)
            geom.transform(32643)
            # Validate the projected geometry before persisting so bad edits
            # (self-intersections, too-few vertices, out-of-bounds coords)
            # are rejected at the API boundary rather than reaching staging.
            from .validators import GeometryValidator
            gv = GeometryValidator()
            errors = []
            if getattr(geom, 'geom_type', '') in ('Polygon', 'MultiPolygon'):
                errors.extend(gv.validate_polygon(geom, 'geometry'))
            elif getattr(geom, 'geom_type', '') in ('LineString', 'MultiLineString'):
                errors.extend(gv.validate_linestring(geom, 'geometry'))
            elif getattr(geom, 'geom_type', '') in ('Point', 'MultiPoint'):
                errors.extend(gv.validate_point(geom, 'geometry'))
            errors.extend(gv.validate_coordinates_in_maldives(geom))
            if errors:
                raise ValueError(errors[0])
            return geom
        except Exception as e:
            raise serializers.ValidationError(f"Invalid GeoJSON geometry: {e}")

# Mixin adding a human-readable "created by" display name to any feature serializer
# (field must be declared in each subclass body for DRF's metaclass to pick it up)
class CreatedByNameMixin:
    def get_created_by_name(self, obj):
        u = obj.created_by
        if not u:
            return None
        return (u.get_full_name() or u.username) if u else None

# User Serializer
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

# --- CORE LAYER SERIALIZERS ---
class RoadSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = Road
        fields = '__all__'

class BuildingSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    addresses_count = serializers.IntegerField(source='addresses.count', read_only=True)
    
    class Meta:
        model = Building
        fields = '__all__'

class AddressSerializer(serializers.ModelSerializer):
    building_code = serializers.CharField(source='building.building_code', read_only=True)
    road_name = serializers.CharField(source='road.road_name', read_only=True)
    
    class Meta:
        model = Address
        fields = '__all__'

class LandUseSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = LandUse
        fields = '__all__'

class FacilitySerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = '__all__'

    def get_category(self, obj):
        return obj.category.name if obj.category else obj.category_old

# --- ASSETS & UTILITIES SERIALIZERS ---
class StreetLightSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StreetLight
        fields = '__all__'

class WaterLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = WaterLine
        fields = '__all__'

class WaterNodeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = WaterNode
        fields = '__all__'

class SewerLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = SewerLine
        fields = '__all__'

class ManholeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = Manhole
        fields = '__all__'

class SewerJunctionSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = SewerJunction
        fields = '__all__'

class ElectricalLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = ElectricalLine
        fields = '__all__'

class ElectricalNodeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = ElectricalNode
        fields = '__all__'

class FiberLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = FiberLine
        fields = '__all__'

class FiberNodeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = FiberNode
        fields = '__all__'

# --- LINEAGE & SESSION SERIALIZERS ---
class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = '__all__'

class ProcessingJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingJob
        fields = '__all__'

class SurveyValidationReportSerializer(serializers.ModelSerializer):
    validated_by_name = serializers.CharField(source='validated_by.username', read_only=True)
    class Meta:
        model = SurveyValidationReport
        fields = '__all__'

class ApprovalHistorySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    class Meta:
        model = ApprovalHistory
        fields = '__all__'

class SurveySessionSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.username', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    files = UploadedFileSerializer(many=True, read_only=True)
    jobs = ProcessingJobSerializer(many=True, read_only=True)
    validation_reports = SurveyValidationReportSerializer(many=True, read_only=True)
    
    # Counts of staged features
    staged_counts = serializers.SerializerMethodField()

    class Meta:
        model = SurveySession
        fields = '__all__'

    def get_staged_counts(self, obj):
        return {
            'buildings': obj.stagingbuilding_features.count(),
            'roads': obj.stagingroad_features.count(),
            'land_use': obj.staginglanduse_features.count(),
            'facilities': obj.stagingfacility_features.count(),
            'street_lights': obj.stagingstreetlight_features.count(),
            'water_lines': obj.stagingwaterline_features.count(),
            'water_nodes': obj.stagingwaternode_features.count(),
            'sewer_lines': obj.stagingsewerline_features.count(),
            'manholes': obj.stagingmanhole_features.count(),
            'sewer_junctions': obj.stagingsewerjunction_features.count(),
            'electrical_lines': obj.stagingelectricalline_features.count(),
            'electrical_nodes': obj.stagingelectricalnode_features.count(),
            'fiber_lines': obj.stagingfiberline_features.count(),
            'fiber_nodes': obj.stagingfibernode_features.count(),
        }

# --- AUDIT LOG SERIALIZER ---
class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    class Meta:
        model = AuditLog
        fields = '__all__'

# --- STAGING (DRAFT) SERIALIZERS ---
# Used by the staged preview endpoint to review unmerged survey features.
class StagingRoadSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingRoad
        fields = '__all__'

class StagingBuildingSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingBuilding
        fields = '__all__'

class StagingLandUseSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingLandUse
        fields = '__all__'

class StagingFacilitySerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()

    class Meta:
        model = StagingFacility
        fields = '__all__'

    def get_category(self, obj):
        return obj.category.name if obj.category else obj.category_old

class StagingStreetLightSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingStreetLight
        fields = '__all__'

class StagingWaterLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingWaterLine
        fields = '__all__'

class StagingWaterNodeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingWaterNode
        fields = '__all__'

class StagingSewerLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingSewerLine
        fields = '__all__'

class StagingManholeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingManhole
        fields = '__all__'

class StagingSewerJunctionSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingSewerJunction
        fields = '__all__'

class StagingElectricalLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingElectricalLine
        fields = '__all__'

class StagingElectricalNodeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingElectricalNode
        fields = '__all__'

class StagingFiberLineSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingFiberLine
        fields = '__all__'

class StagingFiberNodeSerializer(CreatedByNameMixin, serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    asset_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    created_by_name = serializers.SerializerMethodField()
    class Meta:
        model = StagingFiberNode
        fields = '__all__'


# ==========================================
# PUBLIC SERIALIZERS (anonymous / public portal)
# Expose ONLY approved public fields. Internal metadata (created_by,
# accuracy, source_file, source_session, audit info) is never serialized here.
# ==========================================

class PublicRoadSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = Road
        fields = ['id', 'asset_code', 'road_name', 'road_code', 'surface_type', 'geometry']


class PublicBuildingSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = Building
        fields = ['id', 'asset_code', 'building_code', 'house_name', 'building_type', 'usage', 'floors', 'geometry']


class PublicFacilitySerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    category = serializers.SerializerMethodField()
    class Meta:
        model = Facility
        fields = ['id', 'asset_code', 'name', 'category', 'geometry']

    def get_category(self, obj):
        return obj.category.name if obj.category else obj.category_old


class PublicLandUseSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = LandUse
        fields = ['id', 'asset_code', 'zone_class', 'zone_name', 'geometry']
