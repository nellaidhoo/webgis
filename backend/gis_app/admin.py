from django.contrib.gis.admin import GISModelAdmin
from django.contrib import admin

from .models import (
    SurveySession, UploadedFile, ProcessingJob, ApprovalHistory, AuditLog,
    Road, StagingRoad, Building, StagingBuilding, Address, LandUse, StagingLandUse,
    Facility, StagingFacility, StreetLight, StagingStreetLight,
    WaterLine, StagingWaterLine, WaterNode, StagingWaterNode,
    SewerLine, StagingSewerLine, Manhole, StagingManhole, SewerJunction, StagingSewerJunction,
    ElectricalLine, StagingElectricalLine, ElectricalNode, StagingElectricalNode,
    FiberLine, StagingFiberLine, FiberNode, StagingFiberNode, FacilityCategory,
    UserRegistrationRequest
)


class BaseGISAdmin(GISModelAdmin):
    """Base admin for GIS models using an OpenLayers map widget."""
    list_display = ('id', 'asset_code', 'status', 'survey_date', 'updated_at')
    readonly_fields = ('id', 'created_by', 'updated_at')


# --- FACILITY CATEGORIES ---
@admin.register(FacilityCategory)
class FacilityCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'icon', 'color', 'is_active', 'facility_count']
    list_editable = ['icon', 'color', 'is_active']
    search_fields = ['name', 'code']
    list_filter = ['is_active']
    
    def facility_count(self, obj):
        return obj.facilities.count()
    facility_count.short_description = 'Active Facilities'


# --- STAGING FACILITIES (with bulk category assignment) ---
@admin.register(StagingFacility)
class StagingFacilityAdmin(admin.ModelAdmin):
    list_display = ['asset_code', 'name', 'get_category', 'session', 'updated_at']
    list_filter = ['category', 'session__status']
    search_fields = ['name', 'asset_code']
    actions = ['bulk_assign_category']
    
    def get_category(self, obj):
        return obj.category.name if obj.category else 'Uncategorized'
    get_category.short_description = 'Category'
    
    def bulk_assign_category(self, request, queryset):
        from django.shortcuts import render
        from django.http import HttpResponseRedirect
        
        if 'apply' in request.POST:
            category_id = request.POST.get('category')
            if category_id:
                category = FacilityCategory.objects.get(id=category_id)
                queryset.update(category=category)
                self.message_user(request, f"Updated {queryset.count()} facilities to category: {category.name}")
                return HttpResponseRedirect(request.get_full_path())
        
        categories = FacilityCategory.objects.filter(is_active=True)
        return render(request, 'admin/bulk_assign_category.html', {
            'categories': categories,
            'queryset': queryset,
            'action': 'bulk_assign_category',
        })
    bulk_assign_category.short_description = "Assign category to selected facilities"


# --- FACILITIES (main table) ---
@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ['asset_code', 'name', 'get_category', 'status']
    list_filter = ['category', 'status']
    search_fields = ['name', 'asset_code']
    
    def get_category(self, obj):
        return obj.category.name if obj.category else 'Uncategorized'
    get_category.short_description = 'Category'


# --- SURVEY SESSIONS ---
@admin.register(SurveySession)
class SurveySessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'session_type', 'created_at', 'uploaded_by']
    list_filter = ['status', 'session_type']
    search_fields = ['id', 'notes']
    readonly_fields = ['created_at', 'approved_at']
    actions = ['approve_sessions']
    
    def approve_sessions(self, request, queryset):
        """Approve selected sessions and move ALL data to main tables"""
        from .services import approve_session, SessionNotApprovable

        approved_count = 0
        totals = {}
        skipped = []
        for session in queryset:
            try:
                counts = approve_session(session, request.user)
            except SessionNotApprovable as exc:
                skipped.append(f'{session.id}: {exc}')
                continue
            approved_count += 1
            for layer, n in counts.items():
                totals[layer] = totals.get(layer, 0) + n

        lines = [f'Approved {approved_count} session(s):']
        lines += [f'  {layer}: {n}' for layer, n in sorted(totals.items()) if n]
        if skipped:
            lines.append('Skipped:')
            lines += [f'  {s}' for s in skipped]
        self.message_user(request, ' '.join(lines))

@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'file_name', 'file_size', 'uploaded_at')
    search_fields = ('file_name',)


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'status', 'started_at', 'completed_at')
    list_filter = ('status',)


@admin.register(ApprovalHistory)
class ApprovalHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'action', 'user', 'timestamp')
    list_filter = ('action',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'action', 'user', 'session', 'timestamp')
    list_filter = ('action', 'timestamp')


# --- CORE GEOMETRY MODELS (with GIS support) ---
@admin.register(Road)
class RoadAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'road_name', 'road_code', 'surface_type', 'status')


@admin.register(StagingRoad)
class StagingRoadAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'road_name', 'road_code', 'session')


@admin.register(Building)
class BuildingAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'building_code', 'house_name', 'building_type', 'status')


@admin.register(StagingBuilding)
class StagingBuildingAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'building_code', 'house_name', 'session')


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('asset_code', 'address_label', 'building', 'road')
    search_fields = ('address_label', 'asset_code')


@admin.register(LandUse)
class LandUseAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'zone_class', 'zone_name', 'status')


@admin.register(StagingLandUse)
class StagingLandUseAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'zone_class', 'zone_name', 'session')


# --- UTILITY NETWORK ASSETS ---
@admin.register(StreetLight)
class StreetLightAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'light_type', 'status')


@admin.register(StagingStreetLight)
class StagingStreetLightAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'light_type', 'session')


@admin.register(WaterLine)
class WaterLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'diameter_mm', 'pipe_material', 'status')


@admin.register(StagingWaterLine)
class StagingWaterLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'diameter_mm', 'pipe_material', 'session')


@admin.register(WaterNode)
class WaterNodeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'node_type', 'status')


@admin.register(StagingWaterNode)
class StagingWaterNodeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'node_type', 'session')


@admin.register(SewerLine)
class SewerLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'diameter_mm', 'pipe_material', 'status')


@admin.register(StagingSewerLine)
class StagingSewerLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'diameter_mm', 'pipe_material', 'session')


@admin.register(Manhole)
class ManholeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'depth_m', 'status')


@admin.register(StagingManhole)
class StagingManholeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'depth_m', 'session')


@admin.register(SewerJunction)
class SewerJunctionAdmin(BaseGISAdmin):
    pass


@admin.register(StagingSewerJunction)
class StagingSewerJunctionAdmin(BaseGISAdmin):
    pass


@admin.register(ElectricalLine)
class ElectricalLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'voltage', 'cable_type', 'status')


@admin.register(StagingElectricalLine)
class StagingElectricalLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'voltage', 'cable_type', 'session')


@admin.register(ElectricalNode)
class ElectricalNodeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'node_type', 'capacity_kva', 'status')


@admin.register(StagingElectricalNode)
class StagingElectricalNodeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'node_type', 'capacity_kva', 'session')


@admin.register(FiberLine)
class FiberLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'core_count', 'status')


@admin.register(StagingFiberLine)
class StagingFiberLineAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'core_count', 'session')


@admin.register(FiberNode)
class FiberNodeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'node_type', 'status')


@admin.register(StagingFiberNode)
class StagingFiberNodeAdmin(BaseGISAdmin):
    list_display = ('asset_code', 'node_type', 'session')


# --- USER REGISTRATION REQUESTS ---
@admin.register(UserRegistrationRequest)
class UserRegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'status', 'created_at', 'approved_by', 'approved_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['approve_registrations', 'reject_registrations']

    def approve_registrations(self, request, queryset):
        """Approve selected registration requests and activate accounts."""
        from django.utils import timezone
        from .notifications import notify_registration_approved
        approved_count = 0

        for req in queryset.filter(status=UserRegistrationRequest.Status.PENDING):
            # Activate the user
            user = req.user
            user.is_active = True
            user.save()

            # Add to Registered User group
            registered_group, _ = Group.objects.get_or_create(name='Registered User')
            user.groups.add(registered_group)

            # Update registration request
            req.status = UserRegistrationRequest.Status.APPROVED
            req.approved_by = request.user
            req.approved_at = timezone.now()
            req.save()

            # Send email notification
            notify_registration_approved(user)

            approved_count += 1

        self.message_user(request, f"Approved {approved_count} registration(s). Accounts are now active.")

    approve_registrations.short_description = "Approve selected registrations"

    def reject_registrations(self, request, queryset):
        """Reject selected registration requests and deactivate accounts."""
        from django.utils import timezone
        from .notifications import notify_registration_rejected
        rejected_count = 0

        for req in queryset.filter(status=UserRegistrationRequest.Status.PENDING):
            # Deactivate the user
            user = req.user
            user.is_active = False
            user.save()

            # Update registration request
            req.status = UserRegistrationRequest.Status.REJECTED
            req.approved_by = request.user
            req.approved_at = timezone.now()
            req.save()

            # Send email notification
            notify_registration_rejected(user, req.rejection_reason)

            rejected_count += 1

        self.message_user(request, f"Rejected {rejected_count} registration(s).")

    reject_registrations.short_description = "Reject selected registrations"