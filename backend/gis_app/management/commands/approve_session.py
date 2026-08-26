from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from gis_app.models import SurveySession
from gis_app.services import approve_session, SessionNotApprovable


class Command(BaseCommand):
    help = 'Approve a survey session and move ALL staging data to production tables'

    def add_arguments(self, parser):
        parser.add_argument('session_id', nargs='?', help='Session ID to approve (optional)')
        parser.add_argument('--latest', action='store_true', help='Approve the latest session')

    def handle(self, *args, **options):
        if options.get('session_id'):
            session = SurveySession.objects.filter(id=options['session_id']).first()
            if not session:
                raise CommandError(f"Session {options['session_id']} not found")
        else:
            session = SurveySession.objects.order_by('-created_at').first()
            if not session:
                raise CommandError("No sessions exist.")

        admin = User.objects.filter(is_superuser=True).first() or User.objects.first()

        self.stdout.write(f"📋 Session: {session.id}")
        self.stdout.write(f"   Status: {session.status}")

        try:
            counts = approve_session(session, admin, comments='Approved via approve_session command')
        except SessionNotApprovable as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f"✅ Session {session.id} approved: " +
            ", ".join(f"{layer}={n}" for layer, n in sorted(counts.items()) if n)
        ))
