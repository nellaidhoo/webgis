import uuid
from django.contrib.gis.db import models
from django.contrib.auth.models import User

# ==========================================
# 1. ABSTRACT METADATA MODEL
# ==========================================
class BaseGISModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_code = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Metadata tracking fields
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_created")
    survey_date = models.DateField(null=True, blank=True)
    source_file = models.CharField(max_length=255, blank=True)
    # Lineage: link an approved production record back to the survey session it
    # was merged from, so every asset is traceable to its authoritative source.
    source_session = models.ForeignKey('SurveySession', on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_production")
    accuracy = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Accuracy in meters")
    updated_at = models.DateTimeField(auto_now=True)
    
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    class Meta:
        abstract = True

# Abstract model for staging tables
class BaseStagingModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey('SurveySession', on_delete=models.CASCADE, related_name="%(class)s_features")
    asset_code = models.CharField(max_length=50, db_index=True, null=True, blank=True)
    
    # Metadata fields (can be null/empty during staging)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_staged")
    survey_date = models.DateField(null=True, blank=True)
    source_file = models.CharField(max_length=255, blank=True)
    accuracy = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, default='DRAFT')

    class Meta:
        abstract = True
# ==========================================
# 1.5 FACILITY CATEGORIES (Admin-managed)
# ==========================================
class FacilityCategory(models.Model):
    """
    User-defined facility categories managed via Django Admin
    This allows you to add/edit facility types without coding
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, help_text="Display name (e.g., 'Council Office')")
    code = models.CharField(max_length=50, unique=True, help_text="Short code for layer/block matching (e.g., 'COUNCIL')")
    icon = models.CharField(max_length=50, blank=True, null=True, help_text="Emoji or icon name (e.g., '🏛️')")
    color = models.CharField(max_length=7, default='#007bff', help_text="Hex color code (e.g., '#FF0000')")
    description = models.TextField(blank=True, help_text="Optional description")
    is_active = models.BooleanField(default=True, help_text="Inactive categories won't be used")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.icon or ''} {self.name} ({self.code})"

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Facility Categories'

# ==========================================
# 2. SURVEY LINEAGE & SESSION TABLES
# ==========================================
class SurveySession(models.Model):
    STATUS_CHOICES = (
        ('STAGED', 'Staged for Review'),
        ('PROCESSING', 'Processing file'),
        ('COMPLETED', 'Staged (Success)'),
        ('ERROR', 'Processing Failed'),
        ('APPROVED', 'Approved & Merged'),
        ('REJECTED', 'Rejected & Discarded'),
    )
    SESSION_TYPE_CHOICES = (
        ('SURVEY', 'Survey'),
        ('IMAGERY', 'Imagery'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default='SURVEY')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='STAGED')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_sessions')

    def __str__(self):
        return f"Session {self.id} ({self.status})"

    class Meta:
        permissions = [
            ("can_upload_data", "Can upload survey drawings and imagery"),
        ]

class UploadedFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(SurveySession, on_delete=models.CASCADE, related_name='files')
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField()
    md5_checksum = models.CharField(max_length=32)
    file_path = models.CharField(max_length=512)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class ProcessingJob(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(SurveySession, on_delete=models.CASCADE, related_name='jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    log_output = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

class ApprovalHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(SurveySession, on_delete=models.CASCADE, related_name='approvals')
    action = models.CharField(max_length=20, choices=(('APPROVE', 'Approve'), ('REJECT', 'Reject')))
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comments = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

# ==========================================
# 3. CORE GEOMETRY MODELS & STAGING TABLES
# ==========================================

# --- ROADS ---
class Road(BaseGISModel):
    road_name = models.CharField(max_length=150)
    road_code = models.CharField(max_length=50)
    surface_type = models.CharField(max_length=50)
    geometry = models.LineStringField(srid=32643) # UTM Zone 43N

    class Meta:
        indexes = [
            models.Index(fields=['road_name']),
            models.Index(fields=['road_code']),
            models.Index(fields=['asset_code']),
            models.Index(name='road_geom_gist', fields=['geometry']), # Spatial index
        ]

class StagingRoad(BaseStagingModel):
    road_name = models.CharField(max_length=150, blank=True)
    road_code = models.CharField(max_length=50, blank=True)
    surface_type = models.CharField(max_length=50, blank=True)
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_road_geom_gist', fields=['geometry']),
        ]

# --- BUILDINGS ---
class Building(BaseGISModel):
    building_code = models.CharField(max_length=50)
    house_name = models.CharField(max_length=150, blank=True)
    building_type = models.CharField(max_length=50) # Residential, Commercial, Gov, etc.
    usage = models.CharField(max_length=100, blank=True)
    floors = models.IntegerField(default=1)
    geometry = models.PolygonField(srid=32643)

    class Meta:
        indexes = [
            models.Index(fields=['building_code']),
            models.Index(fields=['house_name']),
            models.Index(fields=['asset_code']),
            models.Index(name='building_geom_gist', fields=['geometry']),
        ]

class StagingBuilding(BaseStagingModel):
    building_code = models.CharField(max_length=50, blank=True)
    house_name = models.CharField(max_length=150, blank=True)
    building_type = models.CharField(max_length=50, blank=True)
    usage = models.CharField(max_length=100, blank=True)
    floors = models.IntegerField(default=1)
    geometry = models.PolygonField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_bldg_geom_gist', fields=['geometry']),
        ]

# --- ADDRESS REGISTRY (Tabular: 1-to-many from Building to Addresses) ---
class Address(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_code = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    building = models.ForeignKey(Building, on_delete=models.SET_NULL, null=True, blank=True, related_name='addresses')
    road = models.ForeignKey(Road, on_delete=models.SET_NULL, null=True, blank=True, related_name='addresses')
    address_label = models.CharField(max_length=255) # House name, floor details, etc.
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['address_label']),
        ]

# --- LAND USE ---
class LandUse(BaseGISModel):
    zone_class = models.CharField(max_length=50) # Residential, Commercial, Industrial, Green Area, Conservation
    zone_name = models.CharField(max_length=100)
    geometry = models.PolygonField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='landuse_geom_gist', fields=['geometry']),
        ]

class StagingLandUse(BaseStagingModel):
    zone_class = models.CharField(max_length=50, blank=True)
    zone_name = models.CharField(max_length=100, blank=True)
    geometry = models.PolygonField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_landuse_geom_gist', fields=['geometry']),
        ]

# --- FACILITIES ---
class Facility(BaseGISModel):
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        'FacilityCategory', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='facilities'
    )
    # Keep old category field for backward compatibility (will be removed later)
    category_old = models.CharField(max_length=50, blank=True, null=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(name='facility_geom_gist', fields=['geometry']),
        ]

class StagingFacility(BaseStagingModel):
    name = models.CharField(max_length=150, blank=True)
    category = models.ForeignKey(
        'FacilityCategory', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='staging_facilities'
    )
    # Keep old category field for backward compatibility
    category_old = models.CharField(max_length=50, blank=True, null=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_facility_geom_gist', fields=['geometry']),
        ]
# ==========================================
# 4. ASSETS & UTILITY NETWORKS
# ==========================================

# --- STREET LIGHTS ---
class StreetLight(BaseGISModel):
    light_type = models.CharField(max_length=50, blank=True) # LED, Solar, Halogen
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='streetlight_geom_gist', fields=['geometry']),
        ]

class StagingStreetLight(BaseStagingModel):
    light_type = models.CharField(max_length=50, blank=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_streetlight_geom_gist', fields=['geometry']),
        ]

# --- WATER NETWORK ---
class WaterLine(BaseGISModel):
    diameter_mm = models.IntegerField(null=True, blank=True)
    pipe_material = models.CharField(max_length=50, blank=True) # PVC, HDPE, Iron
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='waterline_geom_gist', fields=['geometry']),
        ]

class StagingWaterLine(BaseStagingModel):
    diameter_mm = models.IntegerField(null=True, blank=True)
    pipe_material = models.CharField(max_length=50, blank=True)
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_waterline_geom_gist', fields=['geometry']),
        ]

class WaterNode(BaseGISModel):
    node_type = models.CharField(max_length=50) # Valve, Meter, Hydrant, Pump
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='waternode_geom_gist', fields=['geometry']),
        ]

class StagingWaterNode(BaseStagingModel):
    node_type = models.CharField(max_length=50, blank=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_waternode_geom_gist', fields=['geometry']),
        ]

# --- SEWER NETWORK ---
class SewerLine(BaseGISModel):
    diameter_mm = models.IntegerField(null=True, blank=True)
    pipe_material = models.CharField(max_length=50, blank=True)
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='sewerline_geom_gist', fields=['geometry']),
        ]

class StagingSewerLine(BaseStagingModel):
    diameter_mm = models.IntegerField(null=True, blank=True)
    pipe_material = models.CharField(max_length=50, blank=True)
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_sewerline_geom_gist', fields=['geometry']),
        ]

class Manhole(BaseGISModel):
    depth_m = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='manhole_geom_gist', fields=['geometry']),
        ]

class StagingManhole(BaseStagingModel):
    depth_m = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_manhole_geom_gist', fields=['geometry']),
        ]

class SewerJunction(BaseGISModel):
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='sewerjunction_geom_gist', fields=['geometry']),
        ]

class StagingSewerJunction(BaseStagingModel):
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_sewerjunction_geom_gist', fields=['geometry']),
        ]

# --- ELECTRICAL NETWORK ---
class ElectricalLine(BaseGISModel):
    voltage = models.CharField(max_length=50) # 230V, 11kV, 22kV
    cable_type = models.CharField(max_length=50, blank=True) # Underground, Overhead
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='electricalline_geom_gist', fields=['geometry']),
        ]

class StagingElectricalLine(BaseStagingModel):
    voltage = models.CharField(max_length=50, blank=True)
    cable_type = models.CharField(max_length=50, blank=True)
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_electricalline_geom_gist', fields=['geometry']),
        ]

class ElectricalNode(BaseGISModel):
    node_type = models.CharField(max_length=50) # Transformer, DistributionBox, Generator
    capacity_kva = models.IntegerField(null=True, blank=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='electricalnode_geom_gist', fields=['geometry']),
        ]

class StagingElectricalNode(BaseStagingModel):
    node_type = models.CharField(max_length=50, blank=True)
    capacity_kva = models.IntegerField(null=True, blank=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_electricalnode_geom_gist', fields=['geometry']),
        ]

# --- FIBER NETWORK ---
class FiberLine(BaseGISModel):
    core_count = models.IntegerField(null=True, blank=True)
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='fiberline_geom_gist', fields=['geometry']),
        ]

class StagingFiberLine(BaseStagingModel):
    core_count = models.IntegerField(null=True, blank=True)
    geometry = models.LineStringField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_fiberline_geom_gist', fields=['geometry']),
        ]

class FiberNode(BaseGISModel):
    node_type = models.CharField(max_length=50) # Cabinet, SpliceEnclosure, OLT
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='fibernode_geom_gist', fields=['geometry']),
        ]

class StagingFiberNode(BaseStagingModel):
    node_type = models.CharField(max_length=50, blank=True)
    geometry = models.PointField(srid=32643)

    class Meta:
        indexes = [
            models.Index(name='stg_fibernode_geom_gist', fields=['geometry']),
        ]

# ==========================================
# 5. AUDIT LOG TABLE
# ==========================================
class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(SurveySession, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50) # e.g. MERGE_SESSION, CREATE_BUILDING, EDIT_ROAD, DELETE_ASSET
    details = models.JSONField() # JSON object containing details of changes
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']


# ==========================================
# 6. USER REGISTRATION APPROVAL WORKFLOW
# ==========================================
class UserRegistrationRequest(models.Model):
    """
    Tracks user registration requests pending admin approval.
    New users are created in INACTIVE state until an admin approves.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='registration_request')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_registrations'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, help_text="Reason if rejected")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.status})"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Registration Request'
        verbose_name_plural = 'Registration Requests'


# ==========================================
# 7. LAYER REGISTRY (Backend layer visibility/classification)
# ==========================================
class LayerRegistry(models.Model):
    """
    Central registry of every GIS layer: its public/private classification,
    visibility level, enablement, zoom range, style and export permission.

    Backend-enforced security is derived from this registry rather than from
    frontend layer hiding.
    """
    class Visibility(models.TextChoices):
        PUBLIC = 'PUBLIC', 'Public'
        AUTHENTICATED = 'AUTHENTICATED', 'Authenticated'
        COUNCIL = 'COUNCIL', 'Council'
        RESTRICTED = 'RESTRICTED', 'Restricted'

    key = models.CharField(max_length=50, unique=True, help_text="Unique slug e.g. 'roads', 'water_lines'")
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    geometry_type = models.CharField(max_length=20, blank=True, help_text="Point | LineString | Polygon")

    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC,
        help_text="Minimum clearance required to read this layer",
    )
    is_public = models.BooleanField(
        default=False,
        help_text="Layer is exposed through the anonymous public GIS portal",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Layer is available for loading/rendering",
    )
    is_exportable = models.BooleanField(
        default=False,
        help_text="Layer data may be exported via the export API",
    )

    min_zoom = models.IntegerField(default=0)
    max_zoom = models.IntegerField(default=22)
    style_config = models.JSONField(default=dict, blank=True, help_text="Frontend style hints (color, weight, fill)")

    # Maps this registry entry to the export LAYER_MAP key if exportable
    export_layer_key = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.display_name} ({self.key})"

    class Meta:
        ordering = ['key']
        verbose_name = 'Layer Registry'
        verbose_name_plural = 'Layer Registry'
