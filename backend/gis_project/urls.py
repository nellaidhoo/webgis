from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # JWT authentication endpoints (versioned + legacy)
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='v1_token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='v1_token_refresh'),
    path('api/v1/auth/token/verify/', TokenVerifyView.as_view(), name='v1_token_verify'),
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    # Public GIS portal - STRICTLY read-only, registered once (not under legacy/api include)
    path('api/public/', include('gis_app.urls_public')),
    # Versioned API (primary)
    path('api/v1/', include('gis_app.urls')),
    # Legacy API (backward compat, same handlers)
    path('api/', include('gis_app.urls')),
]
