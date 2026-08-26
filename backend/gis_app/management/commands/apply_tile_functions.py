from django.core.management.base import BaseCommand
from django.db import connection
import os

class Command(BaseCommand):
    help = 'Apply PostGIS MVT tile functions'

    def handle(self, *args, **options):
        sql_file = os.path.join(os.path.dirname(__file__), '..', '..', 'sql', 'tile_functions.sql')
        
        if not os.path.exists(sql_file):
            self.stderr.write(self.style.ERROR(f'SQL file not found: {sql_file}'))
            return
        
        with open(sql_file, 'r') as f:
            sql = f.read()
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
            self.stdout.write(self.style.SUCCESS('Successfully applied MVT tile functions'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error applying tile functions: {e}'))
