# Generated - Seed the LayerRegistry with the confirmed visibility defaults.
from django.db import migrations

# (key, display_name, description, geometry_type, visibility, is_public, is_exportable, min_zoom, max_zoom, export_layer_key)
LAYERS = [
    ('roads', 'Roads', 'Approved road network', 'LineString', 'PUBLIC', True, True, 0, 22, 'roads'),
    ('buildings', 'Buildings', 'Approved building footprints', 'Polygon', 'PUBLIC', True, True, 10, 22, 'buildings'),
    ('facilities', 'Public Facilities', 'Approved public facilities', 'Point', 'PUBLIC', True, True, 0, 22, 'facilities'),
    ('land_use', 'Land Use', 'Approved land-use zones', 'Polygon', 'PUBLIC', True, True, 0, 22, 'land_use'),
    ('street_lights', 'Street Lights', 'Street lighting inventory', 'Point', 'AUTHENTICATED', False, False, 12, 22, 'street_lights'),
    ('water_lines', 'Water Network', 'Water distribution lines', 'LineString', 'COUNCIL', False, False, 10, 22, 'water_lines'),
    ('water_nodes', 'Water Nodes', 'Water network nodes', 'Point', 'COUNCIL', False, False, 12, 22, None),
    ('sewer_lines', 'Sewer Network', 'Sewer lines', 'LineString', 'COUNCIL', False, False, 10, 22, 'sewer_lines'),
    ('manholes', 'Manholes', 'Sewer manholes', 'Point', 'COUNCIL', False, False, 12, 22, None),
    ('sewer_junctions', 'Sewer Junctions', 'Sewer junctions', 'Point', 'COUNCIL', False, False, 12, 22, None),
    ('electrical_lines', 'Electrical Network', 'Electrical distribution lines', 'LineString', 'COUNCIL', False, False, 10, 22, 'electrical_lines'),
    ('electrical_nodes', 'Electrical Nodes', 'Electrical network nodes', 'Point', 'COUNCIL', False, False, 12, 22, None),
    ('fiber_lines', 'Fiber Network', 'Fiber-optic lines', 'LineString', 'COUNCIL', False, False, 10, 22, 'fiber_lines'),
    ('fiber_nodes', 'Fiber Nodes', 'Fiber network nodes', 'Point', 'COUNCIL', False, False, 12, 22, None),
]


def seed_layers(apps, schema_editor):
    LayerRegistry = apps.get_model('gis_app', 'LayerRegistry')
    for row in LAYERS:
        key, display_name, description, geom_type, visibility, is_public, is_exportable, min_zoom, max_zoom, export_key = row
        LayerRegistry.objects.update_or_create(
            key=key,
            defaults={
                'display_name': display_name,
                'description': description,
                'geometry_type': geom_type,
                'visibility': visibility,
                'is_public': is_public,
                'is_enabled': True,
                'is_exportable': is_exportable,
                'min_zoom': min_zoom,
                'max_zoom': max_zoom,
                'style_config': {},
                'export_layer_key': export_key,
            },
        )


def unseed_layers(apps, schema_editor):
    LayerRegistry = apps.get_model('gis_app', 'LayerRegistry')
    LayerRegistry.objects.filter(key__in=[r[0] for r in LAYERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('gis_app', '0007_layerregistry_building_source_session_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_layers, unseed_layers),
    ]
