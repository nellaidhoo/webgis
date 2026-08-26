from django.core.management.base import BaseCommand
from django.contrib.gis.geos import GEOSGeometry
from concurrent.futures import ThreadPoolExecutor
import json

from gis_app.models import Road, Building, Facility
from gis_app.validators import validator


class Command(BaseCommand):
    help = 'Validate geometry and asset data across all layers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--layer',
            choices=['all', 'roads', 'buildings', 'facilities'],
            default='all',
            help='Layer to validate'
        )
        parser.add_argument(
            '--report',
            action='store_true',
            help='Generate validation report'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix issues (dry run)'
        )

    def handle(self, *args, **options):
        layer = options['layer']
        report = options['report']
        fix = options['fix']
        
        all_errors = []
        
        if layer in ['all', 'roads']:
            self.stdout.write("Validating roads...")
            road_errors = self.validate_layer(Road, 'road')
            all_errors.extend(road_errors)
        
        if layer in ['all', 'buildings']:
            self.stdout.write("Validating buildings...")
            building_errors = self.validate_layer(Building, 'building')
            all_errors.extend(building_errors)
        
        if layer in ['all', 'facilities']:
            self.stdout.write("Validating facilities...")
            facility_errors = self.validate_layer(Facility, 'facility')
            all_errors.extend(facility_errors)
        
        if report:
            self.generate_report(all_errors)
        
        if fix:
            self.apply_fixes(all_errors)
        
        if all_errors:
            self.stdout.write(self.style.WARNING(f"Found {len(all_errors)} validation errors"))
        else:
            self.stdout.write(self.style.SUCCESS("All data valid"))

    def validate_layer(self, model, layer_type):
        """Validate all objects in a layer."""
        errors = []
        
        for obj in model.objects.all():
            if layer_type == 'road':
                obj_errors = validator.validate_road(obj)
            elif layer_type == 'building':
                obj_errors = validator.validate_building(obj)
            elif layer_type == 'facility':
                obj_errors = validator.validate_facility(obj)
            else:
                continue
            
            for error in obj_errors:
                errors.append({
                    'layer': layer_type,
                    'id': str(obj.id),
                    'asset_code': obj.asset_code,
                    'error': error
                })
        
        return errors

    def generate_report(self, errors):
        """Generate validation report."""
        report = {
            'total_errors': len(errors),
            'by_layer': {},
            'by_error_type': {}
        }
        
        for error in errors:
            # Count by layer
            layer = error['layer']
            report['by_layer'][layer] = report['by_layer'].get(layer, 0) + 1
            
            # Count by error type (first 50 chars)
            error_type = error['error'][:50]
            report['by_error_type'][error_type] = report['by_error_type'].get(error_type, 0) + 1
        
        self.stdout.write("\n=== Validation Report ===")
        self.stdout.write(f"Total errors: {report['total_errors']}")
        self.stdout.write("\nBy layer:")
        for layer, count in report['by_layer'].items():
            self.stdout.write(f"  {layer}: {count}")
        self.stdout.write("\nBy error type:")
        for error_type, count in report['by_error_type'].items():
            self.stdout.write(f"  {error_type}: {count}")

    def apply_fixes(self, errors):
        """Attempt to fix validation errors (dry run)."""
        self.stdout.write("\n=== Fix Suggestions ===")
        for error in errors[:10]:  # Show first 10
            self.stdout.write(f"Layer: {error['layer']}, ID: {error['id']}")
            self.stdout.write(f"  Error: {error['error']}")
            self.stdout.write(f"  Suggestion: Manual review required")
            self.stdout.write("")
