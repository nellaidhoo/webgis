from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('gis_app', '0004_facilitycategory_facility_category_old_and_more'),
    ]

    operations = [
        # Required by the combined search view (TrigramSimilarity)
        CreateExtension(name='pg_trgm'),
    ]
