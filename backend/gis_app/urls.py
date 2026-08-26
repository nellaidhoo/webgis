from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RoadViewSet, BuildingViewSet, AddressViewSet, LandUseViewSet, FacilityViewSet,
    StreetLightViewSet, WaterLineViewSet, WaterNodeViewSet, SewerLineViewSet,
    ManholeViewSet, SewerJunctionViewSet, ElectricalLineViewSet, ElectricalNodeViewSet,
    FiberLineViewSet, FiberNodeViewSet, SurveySessionViewSet, AuditLogViewSet,
    SearchView, RegisterView, MeView
)

router = DefaultRouter()
# Core Layers
router.register(r'roads', RoadViewSet, basename='road')
router.register(r'buildings', BuildingViewSet, basename='building')
router.register(r'addresses', AddressViewSet, basename='address')
router.register(r'land_use', LandUseViewSet, basename='land_use')
router.register(r'facilities', FacilityViewSet, basename='facility')

# Asset & Utility Networks
router.register(r'assets/street_lights', StreetLightViewSet, basename='street_light')
router.register(r'assets/water_lines', WaterLineViewSet, basename='water_line')
router.register(r'assets/water_nodes', WaterNodeViewSet, basename='water_node')
router.register(r'assets/sewer_lines', SewerLineViewSet, basename='sewer_line')
router.register(r'assets/manholes', ManholeViewSet, basename='manhole')
router.register(r'assets/sewer_junctions', SewerJunctionViewSet, basename='sewer_junction')
router.register(r'assets/electrical_lines', ElectricalLineViewSet, basename='electrical_line')
router.register(r'assets/electrical_nodes', ElectricalNodeViewSet, basename='electrical_node')
router.register(r'assets/fiber_lines', FiberLineViewSet, basename='fiber_line')
router.register(r'assets/fiber_nodes', FiberNodeViewSet, basename='fiber_node')

# Import Lineage & Audits
router.register(r'survey-sessions', SurveySessionViewSet, basename='survey-session')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    # Router endpoints
    path('', include(router.urls)),
    # Custom combined search endpoint
    path('search/', SearchView.as_view(), name='search'),
    # Self-service registration & profile endpoints
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/me/', MeView.as_view(), name='me'),
]
