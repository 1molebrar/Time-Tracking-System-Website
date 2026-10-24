from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta


class Command(BaseCommand):
    # Management command: transition meeting statuses and archive old ones
    help = 'Auto-update meeting statuses and archive old meetings'

    def handle(self, *args, **options):
        from attendance.models import Meeting

        now = timezone.now()
        today = now.date()
        updated = 0
        archived = 0

        # Process all non-archived meetings
        for meeting in Meeting.objects.filter(is_archived=False):
            start = timezone.make_aware(
                datetime.combine(meeting.date, meeting.start_time),
                timezone.get_current_timezone()
            )
            end = timezone.make_aware(
                datetime.combine(meeting.date, meeting.end_time),
                timezone.get_current_timezone()
            )

            # Transition scheduled -> ongoing when the start time arrives
            if meeting.status == 'scheduled' and start <= now <= end:
                meeting.status = 'ongoing'
                meeting.save()
                updated += 1
            # Transition ongoing -> completed/missed when end time passes
            elif meeting.status == 'ongoing' and now > end:
                if meeting.attendees.exists():
                    meeting.status = 'completed'
                else:
                    meeting.status = 'missed'
                meeting.save()
                updated += 1
            # Transition scheduled -> completed/missed if it never became ongoing
            elif meeting.status == 'scheduled' and now > end:
                if meeting.attendees.exists():
                    meeting.status = 'completed'
                else:
                    meeting.status = 'missed'
                meeting.save()
                updated += 1
            # Archive completed meetings after 24 hours
            elif meeting.status == 'completed' and now > end + timedelta(hours=24):
                meeting.is_archived = True
                meeting.save()
                archived += 1

        self.stdout.write(self.style.SUCCESS(
            f'Updated {updated} meeting statuses, archived {archived} meetings'
        ))
