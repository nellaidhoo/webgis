"""
Public GIS Portal routes - strictly read-only (/api/public/*).

Every view uses the `PublicOnly` permission which rejects any non-safe method,
so no endpoint here can mutate GIS records.
"""
from django.urls import path

from .views_public import (
    PublicLayerListView,
    PublicFeatureListView,
    PublicSearchView,
    PublicImageryView,
)

urlpatterns = [
    path('layers/', PublicLayerListView.as_view(), name='public-layers'),
    path('search/', PublicSearchView.as_view(), name='public-search'),
    path('imagery/', PublicImageryView.as_view(), name='public-imagery'),
    path('<str:layer>/', PublicFeatureListView.as_view(), name='public-layer-features'),
]
