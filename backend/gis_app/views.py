import os
import json
from datetime import datetime
from django.db import transaction
from django.db.models import F, CharField
from django.db.models.functions import Coalesce
from django.contrib.auth.models import User, Group
from django.contrib.postgres.search import TrigramSimilarity
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

from rest_framework import viewsets, permissions, status, views
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import HttpResponse

from .models import (
    SurveySession, UploadedFile, ProcessingJob, ApprovalHistory,
    Road, Building, Address, LandUse, Facility,
    StreetLight, WaterLine, WaterNode, SewerLine, Manhole, SewerJunction,
    ElectricalLine, ElectricalNode, FiberLine, FiberNode, AuditLog,
    StagingRoad, StagingBuilding, StagingLandUse, StagingFacility,
    StagingStreetLight, StagingWaterLine, StagingWaterNode, StagingSewerLine,
    StagingManhole, StagingSewerJunction, StagingElectricalLine, StagingElectricalNode,
    StagingFiberLine, StagingFiberNode, UserRegistrationRequest
)
from .serializers import (
    SurveySessionSerializer, UploadedFileSerializer, ProcessingJobSerializer,
    ApprovalHistorySerializer, UserSerializer,
    RoadSerializer, BuildingSerializer, AddressSerializer, LandUseSerializer,
    FacilitySerializer, StreetLightSerializer, WaterLineSerializer, WaterNodeSerializer,
    SewerLineSerializer, ManholeSerializer, SewerJunctionSerializer,
    ElectricalLineSerializer, ElectricalNodeSerializer, FiberLineSerializer,
    FiberNodeSerializer, AuditLogSerializer,
    StagingRoadSerializer, StagingBuildingSerializer, StagingLandUseSerializer,
    StagingFacilitySerializer, StagingStreetLightSerializer, StagingWaterLineSerializer,
    StagingWaterNodeSerializer, StagingSewerLineSerializer, StagingManholeSerializer,
    StagingSewerJunctionSerializer, StagingElectricalLineSerializer,
    StagingElectricalNodeSerializer,     StagingFiberLineSerializer, StagingFiberNodeSerializer
)
from . import services

# Helper to check user roles
def user_roles(user):
    """Derive role names from the user's group memberships."""
    roles = []
    if user.is_superuser:
        roles.append('Super Admin')
    if user.groups.filter(name='Super Admin').exists():
        roles.append('Super Admin')
    if user.groups.filter(name='Section Admin').exists():
        roles.append('Section Admin')
    if user.groups.filter(name='Council Staff').exists():
        roles.append('Council Staff')
    if user.is_authenticated:
        roles.append('Registered User')
    return roles


def primary_role(user):
    """Highest-priority role for UI display."""
    if user.is_superuser or user.groups.filter(name='Super Admin').exists():
        return 'Super Admin'
    if user.groups.filter(name='Section Admin').exists():
        return 'Section Admin'
    if user.groups.filter(name='Council Staff').exists():
        return 'Council Staff'
    if user.is_authenticated:
        return 'Registered User'
    return 'Guest'


def is_admin(user):
    return user.is_superuser or user.groups.filter(name='Super Admin').exists()

def is_section_admin(user):
    return is_admin(user) or user.groups.filter(name='Section Admin').exists()

def is_staff(user):
    return is_section_admin(user) or user.groups.filter(name='Council Staff').exists()

# Custom Permission Classes
class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_admin(request.user)

class IsSectionAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and is_section_admin(request.user)

class IsStaffOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and is_staff(request.user)

class CanUploadData(permissions.BasePermission):
    """Restrict survey/imagery uploads to authenticated users with upload rights."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return (
            request.user.is_superuser
            or request.user.has_perm('gis_app.can_upload_data')
            or request.user.groups.filter(name__in=['Super Admin', 'Section Admin', 'Council Staff', 'Registered User']).exists()
        )

# --- CORE LAYER VIEWSETS ---
class RoadViewSet(viewsets.ModelViewSet):
    queryset = Road.objects.filter(status='ACTIVE')
    serializer_class = RoadSerializer
    permission_class = [IsSectionAdminOrReadOnly]

class BuildingViewSet(viewsets.ModelViewSet):
    queryset = Building.objects.filter(status='ACTIVE')
    serializer_class = BuildingSerializer
    permission_class = [IsSectionAdminOrReadOnly]

    @action(detail=True, methods=['get'])
    def addresses(self, request, pk=None):
        building = self.get_object()
        addresses = Address.objects.filter(building=building)
        serializer = AddressSerializer(addresses, many=True)
        return Response(serializer.data)

class AddressViewSet(viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsStaffOrReadOnly]

class LandUseViewSet(viewsets.ModelViewSet):
    queryset = LandUse.objects.filter(status='ACTIVE')
    serializer_class = LandUseSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.filter(status='ACTIVE')
    serializer_class = FacilitySerializer
    permission_classes = [IsSectionAdminOrReadOnly]

# --- ASSETS & UTILITY VIEWSETS ---
class StreetLightViewSet(viewsets.ModelViewSet):
    queryset = StreetLight.objects.filter(status='ACTIVE')
    serializer_class = StreetLightSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class WaterLineViewSet(viewsets.ModelViewSet):
    queryset = WaterLine.objects.filter(status='ACTIVE')
    serializer_class = WaterLineSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class WaterNodeViewSet(viewsets.ModelViewSet):
    queryset = WaterNode.objects.filter(status='ACTIVE')
    serializer_class = WaterNodeSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class SewerLineViewSet(viewsets.ModelViewSet):
    queryset = SewerLine.objects.filter(status='ACTIVE')
    serializer_class = SewerLineSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class ManholeViewSet(viewsets.ModelViewSet):
    queryset = Manhole.objects.filter(status='ACTIVE')
    serializer_class = ManholeSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class SewerJunctionViewSet(viewsets.ModelViewSet):
    queryset = SewerJunction.objects.filter(status='ACTIVE')
    serializer_class = SewerJunctionSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class ElectricalLineViewSet(viewsets.ModelViewSet):
    queryset = ElectricalLine.objects.filter(status='ACTIVE')
    serializer_class = ElectricalLineSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class ElectricalNodeViewSet(viewsets.ModelViewSet):
    queryset = ElectricalNode.objects.filter(status='ACTIVE')
    serializer_class = ElectricalNodeSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class FiberLineViewSet(viewsets.ModelViewSet):
    queryset = FiberLine.objects.filter(status='ACTIVE')
    serializer_class = FiberLineSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

class FiberNodeViewSet(viewsets.ModelViewSet):
    queryset = FiberNode.objects.filter(status='ACTIVE')
    serializer_class = FiberNodeSerializer
    permission_classes = [IsSectionAdminOrReadOnly]

# --- SURVEY SESSION & REVIEW VIEWSET ---
class SurveySessionViewSet(viewsets.ModelViewSet):
    queryset = SurveySession.objects.all().order_by('-created_at')
    serializer_class = SurveySessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [permissions.IsAuthenticated(), CanUploadData()]
        return super().get_permissions()

    def get_queryset(self):
        qs = SurveySession.objects.all().order_by('-created_at')
        session_type = self.request.query_params.get('session_type')
        if session_type:
            qs = qs.filter(session_type=session_type)
        return qs

    # Public discovery endpoint for the latest published orthophoto tiles
    @action(detail=False, methods=['get'], url_path='latest-imagery', permission_classes=[permissions.AllowAny])
    def latest_imagery(self, request):
        session = SurveySession.objects.filter(
            session_type='IMAGERY',
            status__in=['COMPLETED', 'APPROVED'],
        ).order_by('-created_at').first()
        if not session:
            return Response({"session_id": None})
        return Response({"session_id": str(session.id)})

    # Session approval and transaction merge endpoint
    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def approve(self, request, pk=None):
        session = self.get_object()

        if session.session_type != 'SURVEY':
            return Response(
                {"error": "Imagery sessions are approved automatically after tiling and cannot be merged."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if session.status not in ['STAGED', 'COMPLETED']:
            return Response(
                {"error": f"Cannot approve session in state '{session.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        comments = request.data.get('comments', '')
        user = request.user

        try:
            counts = services.approve_session(session, user, comments=comments)
        except services.SessionNotApprovable as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Merge failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({
            "status": "Session approved and merged successfully!",
            "counts": counts,
        })

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def reject(self, request, pk=None):
        session = self.get_object()

        if session.session_type != 'SURVEY':
            return Response(
                {"error": "Imagery sessions are approved automatically after tiling and cannot be rejected."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if session.status not in ['STAGED', 'COMPLETED', 'ERROR']:
            return Response(
                {"error": f"Cannot reject session in state '{session.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        comments = request.data.get('comments', '')
        user = request.user

        with transaction.atomic():
            # Clear staging data linked to this session
            StagingRoad.objects.filter(session=session).delete()
            StagingBuilding.objects.filter(session=session).delete()
            StagingLandUse.objects.filter(session=session).delete()
            StagingFacility.objects.filter(session=session).delete()
            StagingStreetLight.objects.filter(session=session).delete()
            StagingWaterLine.objects.filter(session=session).delete()
            StagingWaterNode.objects.filter(session=session).delete()
            StagingSewerLine.objects.filter(session=session).delete()
            StagingManhole.objects.filter(session=session).delete()
            StagingSewerJunction.objects.filter(session=session).delete()
            StagingElectricalLine.objects.filter(session=session).delete()
            StagingElectricalNode.objects.filter(session=session).delete()
            StagingFiberLine.objects.filter(session=session).delete()
            StagingFiberNode.objects.filter(session=session).delete()

            session.status = 'REJECTED'
            session.save()

            ApprovalHistory.objects.create(
                session=session,
                action='REJECT',
                user=user,
                comments=comments
            )

        return Response({"status": "Session rejected and staging layers purged."})

    # Staged feature preview endpoint: returns all draft staging features
    # grouped by layer for a given session (used for pre-approval review).
    @action(detail=True, methods=['get'])
    def staged(self, request, pk=None):
        session = self.get_object()
        data = {
            'buildings': StagingBuildingSerializer(StagingBuilding.objects.filter(session=session), many=True).data,
            'roads': StagingRoadSerializer(StagingRoad.objects.filter(session=session), many=True).data,
            'land_use': StagingLandUseSerializer(StagingLandUse.objects.filter(session=session), many=True).data,
            'facilities': StagingFacilitySerializer(StagingFacility.objects.filter(session=session), many=True).data,
            'street_lights': StagingStreetLightSerializer(StagingStreetLight.objects.filter(session=session), many=True).data,
            'water_lines': StagingWaterLineSerializer(StagingWaterLine.objects.filter(session=session), many=True).data,
            'water_nodes': StagingWaterNodeSerializer(StagingWaterNode.objects.filter(session=session), many=True).data,
            'sewer_lines': StagingSewerLineSerializer(StagingSewerLine.objects.filter(session=session), many=True).data,
            'manholes': StagingManholeSerializer(StagingManhole.objects.filter(session=session), many=True).data,
            'sewer_junctions': StagingSewerJunctionSerializer(StagingSewerJunction.objects.filter(session=session), many=True).data,
            'electrical_lines': StagingElectricalLineSerializer(StagingElectricalLine.objects.filter(session=session), many=True).data,
            'electrical_nodes': StagingElectricalNodeSerializer(StagingElectricalNode.objects.filter(session=session), many=True).data,
            'fiber_lines': StagingFiberLineSerializer(StagingFiberLine.objects.filter(session=session), many=True).data,
            'fiber_nodes': StagingFiberNodeSerializer(StagingFiberNode.objects.filter(session=session), many=True).data,
        }
        return Response(data)

# --- AUDIT LOG VIEWSET ---
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsSuperAdmin]

# ==========================================
# 6. COMBINED SEARCH VIEW (TRIGRAM + PROXIMITY)
# ==========================================
class SearchView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        radius = request.query_params.get('radius', 500) # Default 500m

        results = {
            'text_matches': [],
            'proximity_matches': []
        }

        # 1. Text Similarity Search (Trigram Similarity)
        if query:
            # Search Buildings
            buildings = Building.objects.annotate(
                similarity=TrigramSimilarity('house_name', query) + TrigramSimilarity('building_code', query)
            ).filter(similarity__gt=0.1, status='ACTIVE').order_by('-similarity')[:10]

            for b in buildings:
                results['text_matches'].append({
                    'type': 'building',
                    'id': b.id,
                    'asset_code': b.asset_code,
                    'building_code': b.building_code,
                    'house_name': b.house_name,
                    'building_type': b.building_type,
                    'similarity': float(b.similarity),
                    'geometry': json.loads(b.geometry.transform(4326, clone=True).geojson)
                })

            # Search Roads
            roads = Road.objects.annotate(
                similarity=TrigramSimilarity('road_name', query) + TrigramSimilarity('road_code', query)
            ).filter(similarity__gt=0.1, status='ACTIVE').order_by('-similarity')[:10]

            for r in roads:
                results['text_matches'].append({
                    'type': 'road',
                    'id': r.id,
                    'asset_code': r.asset_code,
                    'road_name': r.road_name,
                    'road_code': r.road_code,
                    'similarity': float(r.similarity),
                    'geometry': json.loads(r.geometry.transform(4326, clone=True).geojson)
                })

            # Search Facilities (match name plus the category display text:
            # the FK's related name, falling back to the legacy char column)
            facilities = Facility.objects.annotate(
                similarity=TrigramSimilarity('name', query)
                + TrigramSimilarity(
                    Coalesce(F('category__name'), F('category_old'), output_field=CharField()),
                    query,
                )
            ).filter(similarity__gt=0.1, status='ACTIVE').order_by('-similarity')[:10]

            for f in facilities:
                results['text_matches'].append({
                    'type': 'facility',
                    'id': f.id,
                    'asset_code': f.asset_code,
                    'name': f.name,
                    'category': f.category.name if f.category else f.category_old,
                    'similarity': float(f.similarity),
                    'geometry': json.loads(f.geometry.transform(4326, clone=True).geojson)
                })

            # Sort combined text matches by similarity
            results['text_matches'].sort(key=lambda x: x['similarity'], reverse=True)

        # 2. Proximity/Spatial Index Search
        if lat and lng:
            try:
                # Convert lat/lng coordinates to a WGS84 Point
                user_point = Point(float(lng), float(lat), srid=4326)
                # Reproject point to UTM Zone 43N (meters-based storage CRS)
                user_point_32643 = user_point.transform(32643, clone=True)
                radius_m = float(radius)

                # Search Facilities within distance
                facilities_near = Facility.objects.filter(
                    geometry__dwithin=(user_point_32643, radius_m),
                    status='ACTIVE'
                ).annotate(
                    distance=Distance('geometry', user_point_32643)
                ).order_by('distance')[:15]

                for f in facilities_near:
                    results['proximity_matches'].append({
                        'type': 'facility',
                        'id': f.id,
                        'name': f.name,
                        'category': f.category.name if f.category else f.category_old,
                        'distance_meters': round(f.distance.m, 2),
                        'geometry': json.loads(f.geometry.transform(4326, clone=True).geojson)
                    })

                # Search Street Lights within distance
                lights_near = StreetLight.objects.filter(
                    geometry__dwithin=(user_point_32643, radius_m),
                    status='ACTIVE'
                ).annotate(
                    distance=Distance('geometry', user_point_32643)
                ).order_by('distance')[:15]

                for l in lights_near:
                    results['proximity_matches'].append({
                        'type': 'street_light',
                        'id': l.id,
                        'light_type': l.light_type,
                        'distance_meters': round(l.distance.m, 2),
                        'geometry': json.loads(l.geometry.transform(4326, clone=True).geojson)
                    })

                # Search nearest building (find closest building polygon)
                buildings_near = Building.objects.filter(
                    geometry__dwithin=(user_point_32643, radius_m),
                    status='ACTIVE'
                ).annotate(
                    distance=Distance('geometry', user_point_32643)
                ).order_by('distance')[:5]

                for b in buildings_near:
                    results['proximity_matches'].append({
                        'type': 'building',
                        'id': b.id,
                        'building_code': b.building_code,
                        'house_name': b.house_name,
                        'distance_meters': round(b.distance.m, 2),
                        'geometry': json.loads(b.geometry.transform(4326, clone=True).geojson)
                    })

                # Sort proximity matches by distance
                results['proximity_matches'].sort(key=lambda x: x['distance_meters'])
            except ValueError:
                return Response(
                    {"error": "Invalid lat, lng, or radius formats."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(results)


# ==========================================
# 7. AUTH: SELF-SERVICE REGISTRATION & PROFILE
# ==========================================
class RegisterView(views.APIView):
    """
    Public self-service registration. Creates a pending registration request
    that requires admin approval before the account is activated.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '')
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()

        if not username or not password:
            return Response(
                {"error": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "A user with this username already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create user as inactive until approved
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False  # Inactive until admin approves
        )

        # Create pending registration request
        registration = UserRegistrationRequest.objects.create(
            user=user,
            status=UserRegistrationRequest.Status.PENDING
        )

        return Response(
            {
                "message": "Registration request submitted. An administrator will review your account.",
                "username": user.username,
                "status": "PENDING"
            },
            status=status.HTTP_201_CREATED
        )


class MeView(views.APIView):
    """Returns the authenticated user's profile and derived role. Supports PATCH for updates."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "user": UserSerializer(user).data,
            "role": primary_role(user),
            "roles": user_roles(user),
        })

    def patch(self, request):
        user = request.user
        allowed_fields = ['email', 'first_name', 'last_name']
        updated = []

        for field in allowed_fields:
            if field in request.data:
                setattr(user, field, request.data[field])
                updated.append(field)

        if updated:
            user.save(update_fields=updated)

        return Response({
            "user": UserSerializer(user).data,
            "role": primary_role(user),
            "roles": user_roles(user),
            "updated_fields": updated,
        })


class HealthCheckView(views.APIView):
    """Detailed health check for monitoring and load balancers."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'services': {}
        }

        # Database check
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                health_status['services']['database'] = 'ok'
        except Exception as e:
            health_status['services']['database'] = f'error: {str(e)}'
            health_status['status'] = 'unhealthy'

        # Redis/Celery check
        try:
            from celery import current_app
            inspect = current_app.control.inspect()
            active = inspect.active()
            health_status['services']['celery'] = 'ok' if active else 'error'
            health_status['celery_workers'] = len(active or {})
        except Exception as e:
            health_status['services']['celery'] = f'error: {str(e)}'
            health_status['status'] = 'unhealthy'

        # Redis check (if used)
        try:
            from celery import current_app
            if current_app.conf.broker_url.startswith('redis://'):
                import redis
                r = redis.from_url(current_app.conf.broker_url)
                r.ping()
                health_status['services']['redis'] = 'ok'
            else:
                health_status['services']['redis'] = 'skipped (filesystem broker)'
        except Exception as e:
            health_status['services']['redis'] = f'error: {str(e)}'
            health_status['status'] = 'unhealthy'

        # Disk space check
        try:
            import shutil
            total, used, free = shutil.disk_usage('/')
            free_gb = free / (1024**3)
            health_status['services']['disk'] = f'ok ({free_gb:.1f}GB free)'
            if free_gb < 1:
                health_status['services']['disk'] = f'warning ({free_gb:.1f}GB free)'
        except Exception as e:
            health_status['services']['disk'] = f'error: {str(e)}'

        # Tile directory check
        try:
            tiles_dir = '/opt/webgis/tiles'
            if os.path.exists(tiles_dir):
                health_status['services']['tiles'] = 'ok'
            else:
                health_status['services']['tiles'] = 'directory missing'
        except Exception as e:
            health_status['services']['tiles'] = f'error: {str(e)}'

        return Response(health_status)


class VectorTileView(views.APIView):
    """Vector tile endpoint serving Mapbox Vector Tiles (MVT) from PostGIS."""
    permission_classes = [permissions.AllowAny]

    VALID_LAYERS = {
        'roads': 'mvt_roads',
        'buildings': 'mvt_buildings',
        'facilities': 'mvt_facilities',
        'landuse': 'mvt_landuse',
        'utilities': 'mvt_utilities',
    }

    def get(self, request, layer, z, x, y):
        # Validate zoom level
        if not (0 <= z <= 22):
            return Response({"error": "Invalid zoom level (0-22)"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate layer
        if layer not in self.VALID_LAYERS:
            return Response(
                {"error": f"Invalid layer. Valid: {list(self.VALID_LAYERS.keys())}"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            from django.db import connection
            function_name = self.VALID_LAYERS[layer]
            
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT {function_name}(%s, %s, %s)", [z, x, y])
                result = cursor.fetchone()
                
                if result is None or len(result) == 0 or result[0] is None:
                    return HttpResponse(status=204)  # No content
                
                tile_data = result[0]
                
                response = HttpResponse(tile_data, content_type='application/vnd.mapbox-vector-tile')
                response['Content-Encoding'] = 'gzip'
                response['Cache-Control'] = 'public, max-age=3600'  # 1 hour cache
                return response
                
        except Exception as e:
            return Response(
                {"error": f"Tile generation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MetricsView(views.APIView):
    """Simple metrics endpoint for monitoring."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .metrics import metrics, update_system_metrics
        import json
        
        # Update system metrics before returning
        update_system_metrics()
        
        # Track this request
        metrics.increment('api.requests')
        
        return Response({
            'metrics': metrics.get_all_metrics(),
            'timestamp': datetime.now().isoformat()
        })
