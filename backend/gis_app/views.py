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
from rest_framework.pagination import LimitOffsetPagination
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import HttpResponse

from .models import (
    SurveySession, SurveyValidationReport, UserAccountProfile, UploadedFile, ProcessingJob, ApprovalHistory,
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
    SurveyValidationReportSerializer,
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
from .security import (
    LayerVisibilityPermission, LayerWritePermission, PublicOnly,
    user_has_layer_visibility, can_export_layer, write_audit,
)

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


class LayerWriteAuditMixin:
    """
    Base for every gated layer viewset. Funnels create/update/delete through
    write_audit so feature edits (geometry/attribute changes, flagging INACTIVE,
    hard deletes) leave a traceable AuditLog entry alongside the record change.
    """

    # Asset-code prefix per layer_key (used when a new feature is created from
    # the map without an explicit code). Mirrors services._new_asset_code.
    ASSET_CODE_PREFIXES = {
        'roads': 'ROAD', 'buildings': 'BLDG', 'land_use': 'ZONE', 'facilities': 'FAC',
        'street_lights': 'SL', 'water_lines': 'WLINE', 'water_nodes': 'WNODE',
        'sewer_lines': 'SLINE', 'manholes': 'MH', 'sewer_junctions': 'SJ',
        'electrical_lines': 'ELINE', 'electrical_nodes': 'ENODE',
        'fiber_lines': 'FLINE', 'fiber_nodes': 'FNODE',
    }

    def _new_asset_code(self):
        import uuid
        prefix = self.ASSET_CODE_PREFIXES.get(getattr(self, 'layer_key', ''), 'ASSET')
        return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

    def perform_create(self, serializer):
        create_kwargs = {'created_by': self.request.user}
        if not (serializer.validated_data.get('asset_code') or '').strip():
            create_kwargs['asset_code'] = self._new_asset_code()
        instance = serializer.save(**create_kwargs)
        write_audit(self.request.user, 'LAYER_CREATE', obj=instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        write_audit(self.request.user, 'LAYER_UPDATE', obj=instance)

    def perform_destroy(self, instance):
        write_audit(self.request.user, 'LAYER_DELETE', obj=instance)
        instance.delete()

# --- CORE LAYER VIEWSETS ---
class RoadViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = Road.objects.filter(status='ACTIVE')
    serializer_class = RoadSerializer
    layer_key = 'roads'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class BuildingViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = Building.objects.filter(status='ACTIVE')
    serializer_class = BuildingSerializer
    layer_key = 'buildings'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

    @action(detail=True, methods=['get'])
    def addresses(self, request, pk=None):
        building = self.get_object()
        addresses = Address.objects.filter(building=building)
        serializer = AddressSerializer(addresses, many=True)
        return Response(serializer.data)

class AddressViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    layer_key = 'buildings'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class LandUseViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = LandUse.objects.filter(status='ACTIVE')
    serializer_class = LandUseSerializer
    layer_key = 'land_use'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class FacilityViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = Facility.objects.filter(status='ACTIVE')
    serializer_class = FacilitySerializer
    layer_key = 'facilities'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

# --- ASSETS & UTILITY VIEWSETS ---
class StreetLightViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = StreetLight.objects.filter(status='ACTIVE')
    serializer_class = StreetLightSerializer
    layer_key = 'street_lights'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class WaterLineViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = WaterLine.objects.filter(status='ACTIVE')
    serializer_class = WaterLineSerializer
    layer_key = 'water_lines'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class WaterNodeViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = WaterNode.objects.filter(status='ACTIVE')
    serializer_class = WaterNodeSerializer
    layer_key = 'water_nodes'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class SewerLineViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = SewerLine.objects.filter(status='ACTIVE')
    serializer_class = SewerLineSerializer
    layer_key = 'sewer_lines'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class ManholeViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = Manhole.objects.filter(status='ACTIVE')
    serializer_class = ManholeSerializer
    layer_key = 'manholes'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class SewerJunctionViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = SewerJunction.objects.filter(status='ACTIVE')
    serializer_class = SewerJunctionSerializer
    layer_key = 'sewer_junctions'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class ElectricalLineViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = ElectricalLine.objects.filter(status='ACTIVE')
    serializer_class = ElectricalLineSerializer
    layer_key = 'electrical_lines'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class ElectricalNodeViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = ElectricalNode.objects.filter(status='ACTIVE')
    serializer_class = ElectricalNodeSerializer
    layer_key = 'electrical_nodes'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class FiberLineViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = FiberLine.objects.filter(status='ACTIVE')
    serializer_class = FiberLineSerializer
    layer_key = 'fiber_lines'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

class FiberNodeViewSet(LayerWriteAuditMixin, viewsets.ModelViewSet):
    queryset = FiberNode.objects.filter(status='ACTIVE')
    serializer_class = FiberNodeSerializer
    layer_key = 'fiber_nodes'
    permission_classes = [LayerVisibilityPermission, LayerWritePermission]

# --- SURVEY SESSION & REVIEW VIEWSET ---
class SurveySessionViewSet(viewsets.ModelViewSet):
    queryset = SurveySession.objects.all().order_by('-created_at')
    serializer_class = SurveySessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LimitOffsetPagination

    def get_permissions(self):
        if self.action in ['create', 'destroy']:
            return [permissions.IsAuthenticated(), CanUploadData()]
        return super().get_permissions()

    def get_queryset(self):
        qs = SurveySession.objects.all().order_by('-created_at')
        session_type = self.request.query_params.get('session_type')
        if session_type:
            qs = qs.filter(session_type=session_type)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
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

    # Generate (or refresh) the data-quality validation report for a session.
    @action(detail=True, methods=['post'], permission_classes=[CanUploadData])
    def validate(self, request, pk=None):
        session = self.get_object()
        try:
            report = services.generate_validation_report(session, request.user)
        except Exception as e:
            return Response(
                {"error": f"Validation failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response(
            SurveyValidationReportSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )

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
            # Backend-enforced: only search layers the caller may read.
            can_see_buildings = user_has_layer_visibility(request.user, 'buildings')
            can_see_roads = user_has_layer_visibility(request.user, 'roads')
            can_see_facilities = user_has_layer_visibility(request.user, 'facilities')

            # Search Buildings
            if can_see_buildings:
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
            if can_see_roads:
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
            if can_see_facilities:
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
                if user_has_layer_visibility(request.user, 'facilities'):
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

                # Search Street Lights within distance (AUTHENTICATED layer)
                if user_has_layer_visibility(request.user, 'street_lights'):
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
                if user_has_layer_visibility(request.user, 'buildings'):
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

        if email and User.objects.filter(email=email).exists():
            return Response(
                {"error": "A user with this email already exists."},
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

        # Notify admin of pending registration
        try:
            from .notifications import notify_registration_pending
            notify_registration_pending(user)
        except Exception:
            pass  # Don't fail registration if email fails

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
        profile = UserAccountProfile.get_for(user)
        return Response({
            "user": UserSerializer(user).data,
            "role": primary_role(user),
            "roles": user_roles(user),
            "must_change_password": profile.must_change_password,
            "password_changed_at": profile.password_changed_at,
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

        profile = UserAccountProfile.get_for(user)
        return Response({
            "user": UserSerializer(user).data,
            "role": primary_role(user),
            "roles": user_roles(user),
            "must_change_password": profile.must_change_password,
            "updated_fields": updated,
        })


class ChangePasswordView(views.APIView):
    """
    Authenticated user changes their own password. Clears the forced-change
    flag (must_change_password) so a reset/initial-credential flow can require
    a new password exactly once.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        current = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')
        confirm = request.data.get('confirm_password', '')

        if not new_password:
            return Response({"error": "New password is required."}, status=status.HTTP_400_BAD_REQUEST)
        if new_password != confirm:
            return Response({"error": "Passwords do not match."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        if not user.check_password(current):
            return Response({"error": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from django.contrib.auth.password_validation import validate_password
            validate_password(new_password, user)
        except Exception as exc:
            return Response({"errors": getattr(exc, 'messages', [str(exc)])}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        profile = UserAccountProfile.get_for(user)
        if profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=['must_change_password'])

        write_audit(user, 'AUTH_PASSWORD_CHANGE', details={'user': user.username})

        return Response({"message": "Password updated successfully."})


class AdminResetPasswordView(views.APIView):
    """
    Super Admin resets a target user's password to a generated temp value and
    marks the account for a forced password change at next login.
    """
    permission_classes = [IsSuperAdmin]

    def post(self, request, user_id=None):
        if not user_id:
            return Response({"error": "A user id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        temp_password = ''.join(secrets.choice(alphabet) for _ in range(10))

        user.set_password(temp_password)
        user.save()

        profile = UserAccountProfile.get_for(user)
        profile.must_change_password = True
        profile.save(update_fields=['must_change_password'])

        try:
            from .notifications import notify_password_reset
            notify_password_reset(user, temp_password)
        except Exception:
            pass

        write_audit(request.user, 'AUTH_PASSWORD_RESET', details={'target_user': user.username})

        return Response({
            "message": "Password reset. User must change it at next login.",
            "temp_password": temp_password,
            "must_change_password": True,
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
    """Vector tile endpoint serving Mapbox Vector Tiles (MVT) from PostGIS.

    Backend-enforced visibility: each tile layer maps to a LayerRegistry key,
    and restricted layers (e.g. utilities) require the caller's clearance.
    """
    permission_classes = [permissions.AllowAny]

    # Each tile bucket maps to one or more LayerRegistry keys. A caller must
    # have visibility on EVERY key the bucket emits (intersection = strictest
    # clearance), so a composite bucket such as 'utilities' (which emits
    # street lights, water and electrical lines in a single tile) requires the
    # highest of those clearances rather than the least-restrictive one.
    VALID_LAYERS = {
        'roads': ('mvt_roads', ('roads',)),
        'buildings': ('mvt_buildings', ('buildings',)),
        'facilities': ('mvt_facilities', ('facilities',)),
        'landuse': ('mvt_landuse', ('land_use',)),
        'utilities': ('mvt_utilities', ('street_lights', 'water_lines', 'electrical_lines')),
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

        # Backend-enforced layer visibility (defensive: block restricted tiles
        # for anonymous/low-clearance callers regardless of frontend hiding).
        # The caller must clear EVERY registry key the bucket emits.
        function_name, registry_keys = self.VALID_LAYERS[layer]
        if not all(user_has_layer_visibility(request.user, key) for key in registry_keys):
            return Response(
                {"error": "You do not have permission to access this layer."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            from django.db import connection
            
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


class ExportView(views.APIView):
    """
    Export GIS data in various formats (GeoJSON, CSV, Shapefile).
    
    GET /api/export/<layer>/?export_format=geojson&bbox=min_lon,min_lat,max_lon,max_lat&filters=status=APPROVED
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, layer):
        from .export import DataExporter, get_supported_layers, get_supported_formats
        from .metrics import metrics
        
        # Track export request
        metrics.increment('exports.total')
        
        # Parse parameters - use 'export_format' to avoid DRF's 'format' query param conflict
        fmt = request.query_params.get('export_format', request.query_params.get('format', 'geojson'))
        bbox_str = request.query_params.get('bbox')
        filters_str = request.query_params.get('filters')
        
        # Validate format
        if fmt not in get_supported_formats():
            return Response(
                {"error": f"Unsupported format '{fmt}'. Valid: {get_supported_formats()}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate layer
        if layer not in get_supported_layers():
            return Response(
                {"error": f"Unsupported layer '{layer}'. Valid: {get_supported_layers()}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Backend-enforced export permission: the layer must be explicitly
        # exportable in the registry AND the caller must have read visibility.
        # This blocks anonymous/across-frontend calls to restricted layers such
        # as /api/export/fiber_lines/.
        if not can_export_layer(request.user, layer):
            write_audit(
                request.user if request.user.is_authenticated else None,
                'EXPORT_DENIED',
                details={'layer': layer, 'format': fmt},
            )
            return Response(
                {"error": "You do not have permission to export this layer."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Audit successful export requests (Sprint 5 governance)
        write_audit(
            request.user if request.user.is_authenticated else None,
            'EXPORT_REQUESTED',
            details={'layer': layer, 'format': fmt},
        )
        
        # Parse bbox
        bbox = None
        if bbox_str:
            try:
                coords = [float(c) for c in bbox_str.split(',')]
                if len(coords) == 4:
                    bbox = tuple(coords)
                else:
                    return Response(
                        {"error": "bbox must have 4 values: min_lon,min_lat,max_lon,max_lat"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except ValueError:
                return Response(
                    {"error": "bbox values must be numbers"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Parse filters
        filters = {}
        if filters_str:
            for pair in filters_str.split('&'):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    filters[key] = value
        
        try:
            exporter = DataExporter(
                layer=layer,
                fmt=fmt,
                filters=filters,
                bbox=bbox,
                user=request.user if request.user.is_authenticated else None
            )
            
            data, content_type, ext = exporter.export()
            
            # Track success
            metrics.increment(f'exports.{fmt}')
            
            # Build response
            if fmt == 'geojson':
                return Response(
                    json.loads(data),
                    content_type=content_type
                )
            else:
                response = HttpResponse(data, content_type=content_type)
                response['Content-Disposition'] = f'attachment; filename="{layer}.{ext}"'
                return response
                
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            metrics.increment('exports.errors')
            return Response(
                {"error": f"Export failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ExportLayersView(views.APIView):
    """List all available export layers and formats (authenticated only - enumeration is
    a reconnaissance surface that should not be open to anonymous callers)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .export import get_supported_layers, get_supported_formats
        
        return Response({
            "layers": get_supported_layers(),
            "formats": get_supported_formats(),
            "example": {
                "geojson": "/api/export/roads/?format=geojson",
                "csv": "/api/export/buildings/?format=csv",
                "shapefile": "/api/export/facilities/?format=shapefile",
                "with_bbox": "/api/export/roads/?format=geojson&bbox=72.5,4.2,73.0,4.8",
                "with_filters": "/api/export/facilities/?format=geojson&filters=status=ACTIVE"
            }
        })
