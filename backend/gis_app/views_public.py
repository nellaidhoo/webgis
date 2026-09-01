"""
Public GIS Portal API surface.

STRICTLY READ-ONLY. No endpoint here creates, updates, deletes, approves,
imports, or otherwise modifies GIS records. The `PublicOnly` permission in
security.py guarantees read-only semantics even if a method slips through.

Only layers that are enabled and tagged PUBLIC (or AUTHENTICATED for anonymous
with a token) are exposed. Internal metadata (created_by, accuracy,
source_file, source_session) is never serialized - see Public* serializers.
"""
import json

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import F, CharField
from django.db.models.functions import Coalesce
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from rest_framework import views
from rest_framework.response import Response
from rest_framework import status

from .models import Road, Building, Facility, LandUse, LayerRegistry
from .serializers import (
    PublicRoadSerializer, PublicBuildingSerializer,
    PublicFacilitySerializer, PublicLandUseSerializer,
)
from .security import PublicOnly, user_has_layer_visibility

PUBLIC_LAYER_SERIALIZERS = {
    'roads': (Road, PublicRoadSerializer),
    'buildings': (Building, PublicBuildingSerializer),
    'facilities': (Facility, PublicFacilitySerializer),
    'land_use': (LandUse, PublicLandUseSerializer),
}


def _public_layers():
    """Enabled registry layers that an anonymous/read-only caller may see."""
    public = []
    for entry in LayerRegistry.objects.filter(is_enabled=True).order_by('display_name'):
        if user_has_layer_visibility(None, entry.key):
            public.append({
                'key': entry.key,
                'display_name': entry.display_name,
                'description': entry.description,
                'geometry_type': entry.geometry_type,
                'min_zoom': entry.min_zoom,
                'max_zoom': entry.max_zoom,
                'style_config': entry.style_config,
            })
    return public


class PublicLayerListView(views.APIView):
    """GET /api/public/layers/ - list layers visible to the public (read-only metadata)."""
    permission_classes = [PublicOnly]

    def get(self, request):
        return Response({'layers': _public_layers()})


class PublicFeatureListView(views.APIView):
    """GET /api/public/<layer>/ - list public-layer features (read-only).

    Supports ?limit= and ?bbox=min_lon,min_lat,max_lon,max_lat filters.
    """
    permission_classes = [PublicOnly]

    def get(self, request, layer):
        if layer not in PUBLIC_LAYER_SERIALIZERS:
            return Response(
                {"error": f"Invalid public layer. Valid: {list(PUBLIC_LAYER_SERIALIZERS.keys())}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user_has_layer_visibility(request.user, layer):
            return Response(
                {"error": "You do not have permission to access this layer."},
                status=status.HTTP_403_FORBIDDEN,
            )

        model, serializer_class = PUBLIC_LAYER_SERIALIZERS[layer]
        qs = model.objects.filter(status='ACTIVE')

        bbox_str = request.query_params.get('bbox')
        if bbox_str:
            try:
                coords = [float(c) for c in bbox_str.split(',')]
                if len(coords) == 4:
                    min_lon, min_lat, max_lon, max_lat = coords
                    from django.contrib.gis.geos import Polygon
                    bbox_poly = Polygon.from_bbox(
                        (min_lon, min_lat, max_lon, max_lat), srid=4326
                    )
                    bbox_poly.transform(32643)
                    qs = qs.filter(geometry__intersects=bbox_poly)
                else:
                    raise ValueError
            except (ValueError, Exception):
                return Response(
                    {"error": "bbox must be 4 values: min_lon,min_lat,max_lon,max_lat"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        limit = request.query_params.get('limit')
        if limit:
            try:
                qs = qs[: int(limit)]
            except (ValueError, TypeError):
                return Response({"error": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            qs = qs[:1000]

        return Response(serializer_class(qs, many=True).data)


class PublicSearchView(views.APIView):
    """GET /api/public/search/?q=&lat=&lng=&radius= - public text + proximity search (read-only).

    Only searches PUBLIC layers visible to anonymous callers.
    """
    permission_classes = [PublicOnly]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        radius = request.query_params.get('radius', 500)

        results = {'text_matches': [], 'proximity_matches': []}

        if query:
            if user_has_layer_visibility(request.user, 'buildings'):
                buildings = Building.objects.annotate(
                    similarity=TrigramSimilarity('house_name', query)
                    + TrigramSimilarity('building_code', query)
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
                        'geometry': json.loads(b.geometry.transform(4326, clone=True).geojson),
                    })

            if user_has_layer_visibility(request.user, 'roads'):
                roads = Road.objects.annotate(
                    similarity=TrigramSimilarity('road_name', query)
                    + TrigramSimilarity('road_code', query)
                ).filter(similarity__gt=0.1, status='ACTIVE').order_by('-similarity')[:10]
                for r in roads:
                    results['text_matches'].append({
                        'type': 'road',
                        'id': r.id,
                        'asset_code': r.asset_code,
                        'road_name': r.road_name,
                        'road_code': r.road_code,
                        'similarity': float(r.similarity),
                        'geometry': json.loads(r.geometry.transform(4326, clone=True).geojson),
                    })

            if user_has_layer_visibility(request.user, 'facilities'):
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
                        'geometry': json.loads(f.geometry.transform(4326, clone=True).geojson),
                    })

            results['text_matches'].sort(key=lambda x: x['similarity'], reverse=True)

        if lat and lng:
            try:
                user_point = Point(float(lng), float(lat), srid=4326)
                user_point_32643 = user_point.transform(32643, clone=True)
                radius_m = float(radius)

                if user_has_layer_visibility(request.user, 'facilities'):
                    facilities_near = Facility.objects.filter(
                        geometry__dwithin=(user_point_32643, radius_m),
                        status='ACTIVE',
                    ).annotate(distance=Distance('geometry', user_point_32643)).order_by('distance')[:15]
                    for f in facilities_near:
                        results['proximity_matches'].append({
                            'type': 'facility',
                            'id': f.id,
                            'name': f.name,
                            'category': f.category.name if f.category else f.category_old,
                            'distance_meters': round(f.distance.m, 2),
                            'geometry': json.loads(f.geometry.transform(4326, clone=True).geojson),
                        })

                if user_has_layer_visibility(request.user, 'buildings'):
                    buildings_near = Building.objects.filter(
                        geometry__dwithin=(user_point_32643, radius_m),
                        status='ACTIVE',
                    ).annotate(distance=Distance('geometry', user_point_32643)).order_by('distance')[:5]
                    for b in buildings_near:
                        results['proximity_matches'].append({
                            'type': 'building',
                            'id': b.id,
                            'building_code': b.building_code,
                            'house_name': b.house_name,
                            'distance_meters': round(b.distance.m, 2),
                            'geometry': json.loads(b.geometry.transform(4326, clone=True).geojson),
                        })

                results['proximity_matches'].sort(key=lambda x: x['distance_meters'])
            except ValueError:
                return Response(
                    {"error": "Invalid lat, lng, or radius formats."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(results)


class PublicImageryView(views.APIView):
    """GET /api/public/imagery/ - return latest approved/most recent basemap imagery (read-only).

    Drone imagery is ingested as COG/XYZ serving tiles derived from the
    original stitched GeoTIFF; this returns the latest public imagery session
    metadata only and never creates or modifies records.
    """
    permission_classes = [PublicOnly]

    def get(self, request):
        from .models import SurveySession
        session = SurveySession.objects.filter(
            session_type='IMAGERY',
            status__in=['COMPLETED', 'APPROVED'],
        ).order_by('-created_at').first()
        if not session:
            return Response({"imagery": []})
        return Response({
            "imagery": [
                {
                    "id": str(session.id),
                    "name": f"Drone Orthomosaic {str(session.id)[:8]}",
                    "session_type": "IMAGERY",
                    "status": session.status,
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                }
            ]
        })
