from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from gis_app.models import SurveySession
from gis_app.services import approve_session, SessionNotApprovable


class Command(BaseCommand):
    help = 'Approve survey sessions and move ALL staging data to production tables'

    def add_arguments(self, parser):
        parser.add_argument('--session_id', help='Approve a single session by ID')
        parser.add_argument('--latest', action='store_true', help='Approve only the latest session')
        parser.add_argument('--all', action='store_true', help='Approve every STAGED/COMPLETED session (default)')

    def handle(self, *args, **options):
        admin = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not admin:
            raise CommandError("No users exist; create a superuser first.")

        sessions = SurveySession.objects.all().order_by('created_at')
        if options.get('session_id'):
            sessions = sessions.filter(id=options['session_id'])
        elif options.get('latest'):
            latest = SurveySession.objects.order_by('-created_at').first()
            sessions = SurveySession.objects.filter(id=latest.id) if latest else sessions.none()

        if not sessions:
            raise CommandError("No matching sessions found.")

        approved = skipped = 0
        totals = {}
        for session in sessions:
            try:
                counts = approve_session(session, admin, comments='Approved via approve_all command')
            except SessionNotApprovable as exc:
                self.stdout.write(self.style.WARNING(f"⏭️  {session.id}: {exc}"))
                skipped += 1
                continue
            approved += 1
            self.stdout.write(self.style.SUCCESS(f"✅ Approved {session.id}: " +
                ", ".join(f"{layer}={n}" for layer, n in sorted(counts.items()) if n)))
            for layer, n in counts.items():
                totals[layer] = totals.get(layer, 0) + n

        summary = ", ".join(f"{layer}={n}" for layer, n in sorted(totals.items()) if n)
        self.stdout.write(self.style.SUCCESS(
            f"Done. Approved: {approved}, Skipped: {skipped}. Totals: {summary or 'nothing merged'}"
        ))
