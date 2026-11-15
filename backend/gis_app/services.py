"""
Shared business logic for approving survey sessions and merging staging
data into production tables. Used by the API viewset, Django admin actions
and management commands so the rules exist in exactly one place.
"""
import uuid

from django.db import transaction
from django.utils import timezone

from .validators import validator

from .models import (
    SurveySession, SurveyValidationReport, ApprovalHistory, AuditLog,
    Road, StagingRoad,
    Building, StagingBuilding,
    LandUse, StagingLandUse,
    Facility, StagingFacility,
    StreetLight, StagingStreetLight,
    WaterLine, StagingWaterLine,
    WaterNode, StagingWaterNode,
    SewerLine, StagingSewerLine,
    Manhole, StagingManhole,
    SewerJunction, StagingSewerJunction,
    ElectricalLine, StagingElectricalLine,
    ElectricalNode, StagingElectricalNode,
    FiberLine, StagingFiberLine,
    FiberNode, StagingFiberNode,
)


class SessionNotApprovable(ValueError):
    """Raised when a session cannot be approved in its current state."""


def _new_asset_code(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def _merge_layer(staging_model, production_model, session, user, prefix, field_map):
    moved = 0
    for staging in staging_model.objects.filter(session=session):
        defaults = {
            'geometry': staging.geometry,
            'created_by': staging.created_by or user,
            'survey_date': staging.survey_date,
            'source_file': staging.source_file,
            'source_session': session,
            'accuracy': staging.accuracy,
            'status': 'ACTIVE',
        }
        for src, dst in field_map.items():
            defaults[dst] = getattr(staging, src)
        production_model.objects.update_or_create(
            asset_code=staging.asset_code or _new_asset_code(prefix),
            defaults=defaults,
        )
        moved += 1
    staging_model.objects.filter(session=session).delete()
    return moved


LAYER_SPECS = [
    # (staging_model, production_model, asset-code prefix, {staging_field: production_field})
    ('StagingRoad', 'Road', 'ROAD', {'road_name': 'road_name', 'road_code': 'road_code', 'surface_type': 'surface_type', 'width_ft': 'width_ft'}),
    ('StagingBuilding', 'Building', 'BLDG', {'building_code': 'building_code', 'house_name': 'house_name', 'building_type': 'building_type', 'usage': 'usage', 'floors': 'floors'}),
    ('StagingLandUse', 'LandUse', 'ZONE', {'zone_class': 'zone_class', 'zone_name': 'zone_name'}),
    ('StagingFacility', 'Facility', 'FAC', {'name': 'name', 'category': 'category', 'category_old': 'category_old'}),
    ('StagingStreetLight', 'StreetLight', 'SL', {'light_type': 'light_type'}),
    ('StagingWaterLine', 'WaterLine', 'WLINE', {'diameter_mm': 'diameter_mm', 'pipe_material': 'pipe_material'}),
    ('StagingWaterNode', 'WaterNode', 'WNODE', {'node_type': 'node_type'}),
    ('StagingSewerLine', 'SewerLine', 'SLINE', {'diameter_mm': 'diameter_mm', 'pipe_material': 'pipe_material'}),
    ('StagingManhole', 'Manhole', 'MH', {'depth_m': 'depth_m'}),
    ('StagingSewerJunction', 'SewerJunction', 'SJ', {}),
    ('StagingElectricalLine', 'ElectricalLine', 'ELINE', {'voltage': 'voltage', 'cable_type': 'cable_type'}),
    ('StagingElectricalNode', 'ElectricalNode', 'ENODE', {'node_type': 'node_type', 'capacity_kva': 'capacity_kva'}),
    ('StagingFiberLine', 'FiberLine', 'FLINE', {'provider': 'provider', 'core_count': 'core_count'}),
    ('StagingFiberNode', 'FiberNode', 'FNODE', {'node_type': 'node_type'}),
]

LAYER_LABELS = {
    'Road': 'roads',
    'Building': 'buildings',
    'LandUse': 'land_uses',
    'Facility': 'facilities',
    'StreetLight': 'street_lights',
    'WaterLine': 'water_lines',
    'WaterNode': 'water_nodes',
    'SewerLine': 'sewer_lines',
    'Manhole': 'manholes',
    'SewerJunction': 'sewer_junctions',
    'ElectricalLine': 'electrical_lines',
    'ElectricalNode': 'electrical_nodes',
    'FiberLine': 'fiber_lines',
    'FiberNode': 'fiber_nodes',
}


@transaction.atomic
def merge_session_to_production(session, user):
    """
    Transactional upsert of every staging feature belonging to `session`
    into the production tables, then purge the staging rows.
    Returns a dict of counts keyed by layer label.
    """
    counts = {}
    for staging_name, production_name, prefix, field_map in LAYER_SPECS:
        staging_model = globals()[staging_name]
        production_model = globals()[production_name]
        counts[LAYER_LABELS[production_name]] = _merge_layer(
            staging_model, production_model, session, user, prefix, field_map
        )
    return counts


def approve_session(session, user, comments=''):
    """
    Validate, merge and mark a survey session APPROVED, recording history
    and audit entries. Returns the merge counts dict.
    """
    if session.session_type != 'SURVEY':
        raise SessionNotApprovable("Imagery sessions are approved automatically after tiling and cannot be merged.")
    if session.status not in ('STAGED', 'COMPLETED'):
        raise SessionNotApprovable(f"Cannot approve session in state '{session.status}'")

    with transaction.atomic():
        counts = merge_session_to_production(session, user)

        session.status = 'APPROVED'
        session.approved_at = timezone.now()
        session.approved_by = user
        session.save()

        ApprovalHistory.objects.create(
            session=session,
            action='APPROVE',
            user=user,
            comments=comments,
        )
        AuditLog.objects.create(
            session=session,
            user=user,
            action='MERGE_SESSION',
            details={
                'notes': session.notes,
                'approved_by': getattr(user, 'username', ''),
                'comments': comments,
                'counts': counts,
            },
        )
    return counts


def clear_staging(session):
    """Delete every staging feature linked to `session`."""
    for staging_name, _, _, _ in LAYER_SPECS:
        globals()[staging_name].objects.filter(session=session).delete()


# Map each staging layer's asset-code validation key (matches AssetCodeValidator.PATTERNS).
STAGING_ASSET_TYPES = {
    'StagingRoad': 'road',
    'StagingBuilding': 'building',
    'StagingFacility': 'facility',
    'StagingStreetLight': 'street_light',
    'StagingWaterLine': 'water_line',
    'StagingSewerLine': 'sewer_line',
    'StagingElectricalLine': 'electrical_line',
    'StagingFiberLine': 'fiber_line',
}


def generate_validation_report(session, user=None):
    """
    Run data-quality validation over every staging feature of `session`,
    then upsert a dedicated SurveyValidationReport.

    Distinct from ProcessingJob: this reports the *outcome* of validating the
    staged GIS records (geometry + asset-code rules), not the async import
    pipeline state.
    """
    total_features = 0
    error_count = 0
    error_details = []

    for staging_name, _, _, _ in LAYER_SPECS:
        staging_model = globals()[staging_name]
        asset_type = STAGING_ASSET_TYPES.get(staging_name)
        for feature in staging_model.objects.filter(session=session):
            total_features += 1
            for message in validator.validate_feature(feature, asset_type):
                error_count += 1
                error_details.append({
                    'layer': LAYER_LABELS[staging_name.replace('Staging', '')],
                    'id': str(feature.id),
                    'asset_code': feature.asset_code,
                    'error': message,
                })

    status = SurveyValidationReport.Status.PASSED if error_count == 0 else SurveyValidationReport.Status.FAILED
    summary = (
        "All staged features passed validation."
        if error_count == 0
        else f"{error_count} validation issue(s) found across {total_features} staged feature(s)."
    )

    report, _ = SurveyValidationReport.objects.update_or_create(
        session=session,
        defaults={
            'status': status,
            'summary': summary,
            'total_features': total_features,
            'error_count': error_count,
            'warning_count': 0,
            'error_details': error_details,
            'validated_by': user,
            'validated_at': timezone.now(),
        },
    )
    return report
