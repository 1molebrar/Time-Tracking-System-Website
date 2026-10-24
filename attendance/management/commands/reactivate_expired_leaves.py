from django.core.management.base import BaseCommand
from django.utils import timezone
from attendance.models import LeaveRequest


class Command(BaseCommand):
    # Management command: reactivate users whose approved leave has ended
    help = 'Reactivate employees whose approved leave period has ended'

    def handle(self, *args, **options):
        today = timezone.now().date()
        # Find all expired approved leaves
        expired = LeaveRequest.objects.filter(
            status='approved', end_date__lt=today
        ).select_related('employee__profile')
        count = 0
        for leave in expired:
            user = leave.employee
            # Skip if user has another active leave still running
            has_other_active = LeaveRequest.objects.filter(
                employee=user, status='approved', end_date__gte=today
            ).exists()
            if not has_other_active:
                user.is_active = True
                user.save(update_fields=['is_active'])
                profile = user.profile
                profile.deactivation_reason = None
                profile.save(update_fields=['deactivation_reason'])
                count += 1
                self.stdout.write(f'  Reactivated {user.username}')
        self.stdout.write(self.style.SUCCESS(f'Reactivated {count} user(s)'))
