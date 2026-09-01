"""
Security helpers for the GIS hardening phase.

Centralizes backend-enforced layer visibility (derived from the LayerRegistry),
the DRF permission classes that consume it, and a generic audit-log writer.

All access paths (REST viewsets, /api/public/*, search, vector tiles, exports)
must consult these helpers so restricted infrastructure is never exposed to
anonymous or low-clearance users regardless of any frontend layer hiding.
"""
from django.apps import apps

from rest_framework import permissions

from .models import AuditLog, LayerRegistry


# ---------------------------------------------------------------------------
# Layer registry helpers
# ---------------------------------------------------------------------------

def get_layer_registry(layer_key):
    """Return the LayerRegistry row for a layer key, or None if not registered.

    Registered-but-inexistent keys imply the default restriction: treat an
    unregistered key as fully restricted (defensive default) rather than open.
    """
    if not layer_key:
        return None
    LayerRegistry = apps.get_model('gis_app', 'LayerRegistry')
    try:
        return LayerRegistry.objects.get(key=layer_key)
    except LayerRegistry.DoesNotExist:
        return None


def user_has_layer_visibility(user, layer_key):
    """Return True if `user` may read the given layer per its visibility.

    visibility values:
      PUBLIC        -> anyone (including anonymous)
      AUTHENTICATED -> any authenticated user
      COUNCIL       -> staff (Council Staff / Section Admin / Super Admin)
      RESTRICTED    -> Section Admin / Super Admin only

    A layer that is not present in the registry (or not enabled) is treated as
    fully restricted (defensive: deny by default).
    """
    registry = get_layer_registry(layer_key)
    if registry is None or not registry.is_enabled:
        return False

    vis = registry.visibility
    if vis == LayerRegistry.Visibility.PUBLIC:
        return True
    if vis == LayerRegistry.Visibility.AUTHENTICATED:
        return user is not None and user.is_authenticated
    if vis == LayerRegistry.Visibility.COUNCIL:
        return user is not None and user.is_authenticated and is_staff(user)
    if vis == LayerRegistry.Visibility.RESTRICTED:
        return user is not None and user.is_authenticated and is_section_admin(user)
    return False


def can_export_layer(user, layer_key):
    """Exporting also requires the layer to be explicitly marked is_exportable."""
    registry = get_layer_registry(layer_key)
    if registry is None or not registry.is_exportable:
        return False
    return user_has_layer_visibility(user, layer_key)


# ---------------------------------------------------------------------------
# Role helpers (mirror of views.user_roles without importing views to avoid
# circular imports)
# ---------------------------------------------------------------------------

def is_admin(user):
    return user.is_superuser or user.groups.filter(name='Super Admin').exists()


def is_section_admin(user):
    return is_admin(user) or user.groups.filter(name='Section Admin').exists()


def is_staff(user):
    return is_section_admin(user) or user.groups.filter(name='Council Staff').exists()


# ---------------------------------------------------------------------------
# DRF permission classes
# ---------------------------------------------------------------------------

class LayerVisibilityPermission(permissions.BasePermission):
    """
    Enforce a layer's registry visibility for read access.

    Usage:
        class WaterLineViewSet(...):
            layer_key = 'water_lines'
            permission_classes = [LayerVisibilityPermission, IsSectionAdminOrReadOnly]
    """

    #: subclasses must define the LayerRegistry key
    layer_key = None

    def has_permission(self, request, view):
        key = getattr(view, 'layer_key', None) or self.layer_key
        if not key:
            # no layer classification -> fall back to authenticated-or-readonly
            return True
        if request.method in permissions.SAFE_METHODS:
            return user_has_layer_visibility(request.user, key)
        # Mutations are handled by a second, stricter permission class.
        return True


class LayerWritePermission(permissions.BasePermission):
    """
    Restrict write operations (create/update/partial_update/delete) on GIS
    layers to Section Admin / Super Admin (configurable per layer in future).
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user is not None and request.user.is_authenticated and is_section_admin(request.user)


class PublicOnly(permissions.BasePermission):
    """
    For the /api/public/* surface: read-only by construction. Deny every
    non-safe method so a public endpoint can never mutate GIS records.
    """

    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


# ---------------------------------------------------------------------------
# Generic audit logging
# ---------------------------------------------------------------------------

def write_audit(user, action, details=None, session=None, obj=None):
    """
    Append an AuditLog entry. `obj` (if given) is used to enrich details with
    a stable object reference suitable for tracing.
    """
    payload = dict(details or {})
    if obj is not None:
        model_name = getattr(obj, '_meta', None)
        if model_name is not None:
            payload.setdefault('object_type', model_name.model_name)
            pk = getattr(obj, 'pk', None) or getattr(obj, 'id', None)
            payload.setdefault('object_id', str(pk) if pk else None)
            payload.setdefault('asset_code', getattr(obj, 'asset_code', None))
    return AuditLog.objects.create(
        session=session,
        user=user,
        action=action,
        details=payload,
    )
