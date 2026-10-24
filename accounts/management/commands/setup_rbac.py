from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from accounts.models import UserProfile
from attendance.models import Client, Project, ProjectTask, Attendance, TimeEntry, Notification, Holiday, Meeting


# Permission codenames assigned to each role group
GROUP_PERMISSIONS = {
    'Admin': [
        'can_manage_users',
        'can_manage_roles',
        'can_view_reports',
        'can_export_data',
        'can_soft_delete',
        'can_view_clients',
        'can_manage_clients',
        'can_view_projects',
        'can_manage_projects',
        'can_view_tasks',
        'can_manage_tasks',
        'can_claim_tasks',
        'can_view_time_entries',
        'can_manage_time_entries',
        'can_correct_time',
        'can_view_attendance',
        'can_view_all_attendance',
        'can_manage_attendance',
        'can_view_holidays',
        'can_manage_holidays',
        'can_view_meetings',
        'can_manage_meetings',
    ],
    'Manager': [
        'can_view_reports',
        'can_export_data',
        'can_view_clients',
        'can_manage_clients',
        'can_view_projects',
        'can_manage_projects',
        'can_view_tasks',
        'can_manage_tasks',
        'can_claim_tasks',
        'can_view_time_entries',
        'can_correct_time',
        'can_view_attendance',
        'can_view_all_attendance',
        'can_view_holidays',
        'can_view_meetings',
        'can_manage_meetings',
    ],
    'Employee': [
        'can_view_clients',
        'can_view_projects',
        'can_view_tasks',
        'can_claim_tasks',
        'can_view_time_entries',
        'can_view_attendance',
        'can_view_holidays',
        'can_view_meetings',
    ],
}

# Models for which custom permissions will be created
MODELS_WITH_PERMISSIONS = {
    'Client': Client,
    'Project': Project,
    'ProjectTask': ProjectTask,
    'TimeEntry': TimeEntry,
    'Attendance': Attendance,
    'Notification': Notification,
    'Holiday': Holiday,
    'Meeting': Meeting,
    'UserProfile': UserProfile,
}


class Command(BaseCommand):
    help = 'Sets up RBAC groups and permissions'

    def handle(self, *args, **options):  # Create/update groups and sync all users to their role group
        for group_name, codenames in GROUP_PERMISSIONS.items():
            # Step 1: create or get the group
            group, created = Group.objects.get_or_create(name=group_name)
            perms = Permission.objects.filter(codename__in=codenames)
            group.permissions.set(perms)
            status = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{status} group "{group_name}" with {perms.count()} permissions'))

        # Step 2: sync each user to their appropriate group based on profile role
        for up in UserProfile.objects.select_related('user').all():
            role_map = {'admin': 'Admin', 'manager': 'Manager', 'employee': 'Employee'}
            group_name = role_map.get(up.role)
            if group_name:
                group = Group.objects.get(name=group_name)
                up.user.groups.set([group])
                self.stdout.write(f'  Synced {up.user.username} -> {group_name}')

        self.stdout.write(self.style.SUCCESS('RBAC setup complete.'))
