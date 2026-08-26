import os
import uuid
import datetime
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point, LineString, Polygon
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from gis_app.models import (
    Road, Building, Address, LandUse, Facility, StreetLight,
    WaterLine, WaterNode, SewerLine, Manhole, SewerJunction,
    ElectricalLine, ElectricalNode, FiberLine, FiberNode,
    SurveySession, FacilityCategory,
)

class Command(BaseCommand):
    help = "Seed database with realistic island GIS mock data in EPSG:32643 (UTM Zone 43N)"

    def handle(self, *args, **options):
        self.stdout.write("Starting database seeding...")

        # 1. Create Groups & Users
        super_admin_group, _ = Group.objects.get_or_create(name="Super Admin")
        sec_admin_group, _ = Group.objects.get_or_create(name="Section Admin")
        staff_group, _ = Group.objects.get_or_create(name="Council Staff")
        registered_group, _ = Group.objects.get_or_create(name="Registered User")

        # Create Admin User
        admin_user, created = User.objects.get_or_create(
            username="admin",
            email="admin@islandcouncil.gov",
            defaults={"is_staff": True, "is_superuser": True}
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
            admin_user.groups.add(super_admin_group)
            self.stdout.write("Created Super Admin user 'admin' (password: admin123)")

        # Grant the upload permission to all data-entry groups
        upload_perm, _ = Permission.objects.get_or_create(
            codename="can_upload_data",
            content_type=ContentType.objects.get_for_model(SurveySession),
            defaults={"name": "Can upload survey drawings and imagery"},
        )
        for group in [registered_group, staff_group, sec_admin_group, super_admin_group]:
            group.permissions.add(upload_perm)
        self.stdout.write("Granted 'can_upload_data' permission to all data-entry groups.")

        # Create Staff User
        staff_user, created = User.objects.get_or_create(
            username="staff",
            email="staff@islandcouncil.gov",
            defaults={"is_staff": True}
        )
        if created:
            staff_user.set_password("staff123")
            staff_user.save()
            staff_user.groups.add(staff_group)
            self.stdout.write("Created Staff user 'staff' (password: staff123)")

        # Clear existing GIS data
        self.stdout.write("Clearing existing GIS objects...")
        Road.objects.all().delete()
        Building.objects.all().delete()
        Address.objects.all().delete()
        LandUse.objects.all().delete()
        Facility.objects.all().delete()
        StreetLight.objects.all().delete()
        WaterLine.objects.all().delete()
        WaterNode.objects.all().delete()
        SewerLine.objects.all().delete()
        Manhole.objects.all().delete()
        SewerJunction.objects.all().delete()
        ElectricalLine.objects.all().delete()
        ElectricalNode.objects.all().delete()
        FiberLine.objects.all().delete()
        FiberNode.objects.all().delete()

        # Seed Metadata parameters
        survey_date = datetime.date(2026, 5, 1)
        src_file = "dxf_seed_survey_v1.dxf"

        # 2. SEED ROADS
        # Main road running North-South
        main_road = Road.objects.create(
            asset_code="ROAD-0001",
            road_name="Majeedhee Magu (Main Road)",
            road_code="MJM",
            surface_type="Asphalt",
            geometry=LineString((332500, 435200), (332550, 436000), (332600, 436800), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.1
        )
        # Ring road running East-West on South beach
        south_road = Road.objects.create(
            asset_code="ROAD-0002",
            road_name="South Beach Road",
            road_code="SBR",
            surface_type="Sand",
            geometry=LineString((332100, 435200), (332500, 435200), (332900, 435250), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.2
        )
        self.stdout.write("Seeded 2 Roads.")

        # 3. SEED BUILDINGS & ADDRESSES
        # Council Office building
        bldg_council = Building.objects.create(
            asset_code="BLDG-0001",
            building_code="BLDG-C1",
            house_name="Island Council Secretariat",
            building_type="Government",
            usage="Administrative Offices",
            floors=3,
            geometry=Polygon(((332560, 436020), (332590, 436020), (332590, 436050), (332560, 436050), (332560, 436020)), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.05
        )
        # Link Address to Council office
        Address.objects.create(
            asset_code="ADDR-0001",
            building=bldg_council,
            road=main_road,
            address_label="G. Secretariat, Majeedhee Magu, Island Council",
            notes="Main entrance facing West."
        )

        # Beach Resort building
        bldg_resort = Building.objects.create(
            asset_code="BLDG-0002",
            building_code="BLDG-R1",
            house_name="Sunset Beach Villa",
            building_type="Commercial",
            usage="Resort Guesthouse",
            floors=2,
            geometry=Polygon(((332850, 435300), (332880, 435300), (332880, 435330), (332850, 435330), (332850, 435300)), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.1
        )
        Address.objects.create(
            asset_code="ADDR-0002",
            building=bldg_resort,
            road=south_road,
            address_label="Villa 101, Sunset Beach Villa, South Beach Road",
            notes="Private beachfront balcony."
        )

        # Residential House 1
        bldg_h1 = Building.objects.create(
            asset_code="BLDG-0003",
            building_code="BLDG-H1",
            house_name="Ocean Breeze",
            building_type="Residential",
            usage="Single Family Home",
            floors=1,
            geometry=Polygon(((332480, 435550), (332500, 435550), (332500, 435570), (332480, 435570), (332480, 435550)), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.1
        )
        Address.objects.create(
            asset_code="ADDR-0003",
            building=bldg_h1,
            road=main_road,
            address_label="M. Ocean Breeze, Majeedhee Magu",
            notes="Residential household."
        )

        # Residential House 2 (Multi-household building)
        bldg_h2 = Building.objects.create(
            asset_code="BLDG-0004",
            building_code="BLDG-H2",
            house_name="Rose Villa",
            building_type="Residential",
            usage="Multi-Family Apartment",
            floors=4,
            geometry=Polygon(((332520, 435750), (332545, 435750), (332545, 435780), (332520, 435780), (332520, 435750)), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.08
        )
        # Multi-household addresses linked to a single building
        Address.objects.create(
            asset_code="ADDR-0004",
            building=bldg_h2,
            road=main_road,
            address_label="G. Rose Villa, Ground Floor",
            notes="Household 1"
        )
        Address.objects.create(
            asset_code="ADDR-0005",
            building=bldg_h2,
            road=main_road,
            address_label="G. Rose Villa, Flat 1A (First Floor)",
            notes="Household 2"
        )
        Address.objects.create(
            asset_code="ADDR-0006",
            building=bldg_h2,
            road=main_road,
            address_label="G. Rose Villa, Flat 2B (Second Floor)",
            notes="Household 3"
        )
        self.stdout.write("Seeded 4 Buildings with 6 linked Addresses (representing households).")

        # 4. SEED LAND USE ZONES
        LandUse.objects.create(
            asset_code="ZONE-0001",
            zone_class="Commercial",
            zone_name="Beach Resort Zone",
            geometry=Polygon(((332700, 435200), (333000, 435200), (333000, 435500), (332700, 435500), (332700, 435200)), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.5
        )
        LandUse.objects.create(
            asset_code="ZONE-0002",
            zone_class="Conservation",
            zone_name="Southern Mangrove Reserve",
            geometry=Polygon(((332000, 435000), (332300, 435000), (332300, 435300), (332000, 435300), (332000, 435000)), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.5
        )
        self.stdout.write("Seeded 2 Land Use Zones.")

        # 5. SEED FACILITY CATEGORIES + FACILITIES
        def _category(name, code, color):
            cat, created = FacilityCategory.objects.get_or_create(
                code=code,
                defaults={"name": name, "color": color},
            )
            return cat

        cat_mosque = _category("Mosque", "MOSQUE", "#22c55e")
        cat_clinic = _category("Clinic", "CLINIC", "#ef4444")
        for name, code in [("School", "SCHOOL"), ("Council Office", "COUNCIL"),
                           ("Port / Harbour", "PORT"), ("Power House", "POWERHOUSE")]:
            _category(name, code, "#3b82f6")
        self.stdout.write("Seeded 6 Facility Categories.")

        # Local Mosque
        Facility.objects.create(
            asset_code="FAC-0001",
            name="Masjid-al-Ikhlas",
            category=cat_mosque,
            geometry=Point(332530, 435880, srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.1
        )
        # Health Center / Clinic
        Facility.objects.create(
            asset_code="FAC-0002",
            name="Island Health Center",
            category=cat_clinic,
            geometry=Point(332580, 436300, srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.08
        )
        self.stdout.write("Seeded 2 Public Facilities.")

        # 6. SEED STREET LIGHTS
        for i in range(1, 5):
            StreetLight.objects.create(
                asset_code=f"SL-{i:04d}",
                light_type="LED",
                geometry=Point(332510, 435200 + (i * 300), srid=32643),
                created_by=admin_user,
                survey_date=survey_date,
                source_file=src_file,
                accuracy=0.1
            )
        self.stdout.write("Seeded 4 Street Lights along Main Road.")

        # 7. SEED UTILITY: WATER NETWORK
        # Main Water pipe running North-South along Main Road
        water_main = WaterLine.objects.create(
            asset_code="WLINE-0001",
            diameter_mm=110,
            pipe_material="HDPE",
            geometry=LineString((332498, 435200), (332548, 436000), (332598, 436800), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.15
        )
        # Water Node (Main Isolation Valve)
        WaterNode.objects.create(
            asset_code="WNODE-0001",
            node_type="Valve",
            geometry=Point(332548, 436000, srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.05
        )
        self.stdout.write("Seeded Water Line and Node.")

        # 8. SEED UTILITY: SEWER NETWORK
        # Sewer gravity line running down Main Road
        sewer_main = SewerLine.objects.create(
            asset_code="SLINE-0001",
            diameter_mm=160,
            pipe_material="uPVC",
            geometry=LineString((332502, 435200), (332552, 436000), (332602, 436800), srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.15
        )
        # Manholes along sewer line
        Manhole.objects.create(
            asset_code="MH-0001",
            depth_m=1.85,
            geometry=Point(332502, 435200, srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.05
        )
        Manhole.objects.create(
            asset_code="MH-0002",
            depth_m=2.10,
            geometry=Point(332552, 436000, srid=32643),
            created_by=admin_user,
            survey_date=survey_date,
            source_file=src_file,
            accuracy=0.05
        )
        self.stdout.write("Seeded Sewer Line and 2 Manholes.")

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))
