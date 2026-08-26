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
    StagingFiberLine, StagingFiberNode
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
            return geom
        except Exception as e:
            raise serializers.ValidationError(f"Invalid GeoJSON geometry: {e}")

# User Serializer
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

# --- CORE LAYER SERIALIZERS ---
class RoadSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = Road
        fields = '__all__'

class BuildingSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
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

class LandUseSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = LandUse
        fields = '__all__'

class FacilitySerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    category = serializers.SerializerMethodField()

    class Meta:
        model = Facility
        fields = '__all__'

    def get_category(self, obj):
        return obj.category.name if obj.category else obj.category_old

# --- ASSETS & UTILITIES SERIALIZERS ---
class StreetLightSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StreetLight
        fields = '__all__'

class WaterLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = WaterLine
        fields = '__all__'

class WaterNodeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = WaterNode
        fields = '__all__'

class SewerLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = SewerLine
        fields = '__all__'

class ManholeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = Manhole
        fields = '__all__'

class SewerJunctionSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = SewerJunction
        fields = '__all__'

class ElectricalLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = ElectricalLine
        fields = '__all__'

class ElectricalNodeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = ElectricalNode
        fields = '__all__'

class FiberLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = FiberLine
        fields = '__all__'

class FiberNodeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
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
class StagingRoadSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingRoad
        fields = '__all__'

class StagingBuildingSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingBuilding
        fields = '__all__'

class StagingLandUseSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingLandUse
        fields = '__all__'

class StagingFacilitySerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    category = serializers.SerializerMethodField()

    class Meta:
        model = StagingFacility
        fields = '__all__'

    def get_category(self, obj):
        return obj.category.name if obj.category else obj.category_old

class StagingStreetLightSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingStreetLight
        fields = '__all__'

class StagingWaterLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingWaterLine
        fields = '__all__'

class StagingWaterNodeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingWaterNode
        fields = '__all__'

class StagingSewerLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingSewerLine
        fields = '__all__'

class StagingManholeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingManhole
        fields = '__all__'

class StagingSewerJunctionSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingSewerJunction
        fields = '__all__'

class StagingElectricalLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingElectricalLine
        fields = '__all__'

class StagingElectricalNodeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingElectricalNode
        fields = '__all__'

class StagingFiberLineSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingFiberLine
        fields = '__all__'

class StagingFiberNodeSerializer(serializers.ModelSerializer):
    geometry = GeometrySerializerField()
    class Meta:
        model = StagingFiberNode
        fields = '__all__'
