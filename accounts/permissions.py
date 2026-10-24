from django.core.exceptions import PermissionDenied
from django.db.models import Q


def has_permission(user, codename):  # Check if user has a specific permission codename
    if not user.is_authenticated or not user.is_active:
        return False
    return user.has_perm(f'attendance.{codename}') or user.has_perm(f'accounts.{codename}')


# --- Visibility queries: what users can see ---


def get_visible_projects(user):  # Projects visible to user based on their role
    from attendance.models import Project
    if user.profile.role == 'admin':
        return Project.objects.filter(is_deleted=False)
    elif user.profile.role == 'manager':
        team_ids = list(user.profile.team_members.values_list('user_id', flat=True)) + [user.id]
        return Project.objects.filter(
            Q(is_deleted=False),
            Q(created_by=user) |
            Q(memberships__user_id__in=team_ids, memberships__is_active=True)
        ).distinct()
    return Project.objects.filter(is_deleted=False, status='active')


def get_visible_tasks(user):  # Tasks visible to user based on their role
    from attendance.models import ProjectTask
    if user.profile.role == 'admin':
        return ProjectTask.objects.filter(is_deleted=False)
    elif user.profile.role == 'manager':
        team_ids = user.profile.team_members.values_list('user_id', flat=True)
        return ProjectTask.objects.filter(
            Q(is_deleted=False),
            Q(manager=user) | Q(assigned_to_id__in=list(team_ids))
        ).distinct()
    return ProjectTask.objects.filter(is_deleted=False, assigned_to=user)


def get_visible_attendances(user):  # Attendance records visible to user
    from attendance.models import Attendance
    if user.profile.role == 'admin':
        return Attendance.objects.all()
    elif user.profile.role == 'manager':
        team_ids = list(user.profile.team_members.values_list('user_id', flat=True)) + [user.id]
        return Attendance.objects.filter(
            Q(manager=user) | Q(user_id__in=team_ids)
        ).distinct()
    return Attendance.objects.filter(user=user)


def get_visible_users(user):  # Other users visible to this user
    from django.contrib.auth.models import User
    if user.profile.role == 'admin':
        return User.objects.filter(is_active=True)
    elif user.profile.role == 'manager':
        team_ids = user.profile.team_members.values_list('user_id', flat=True)
        return User.objects.filter(id__in=list(team_ids) + [user.id], is_active=True)
    return User.objects.filter(id=user.id)


def get_visible_meetings(user):  # Meetings visible to user
    from attendance.models import Meeting
    if user.profile.role == 'admin':
        return Meeting.objects.filter(is_deleted=False)
    elif user.profile.role == 'manager':
        team_ids = list(user.profile.team_members.values_list('user_id', flat=True)) + [user.id]
        return Meeting.objects.filter(
            Q(is_deleted=False),
            Q(created_by=user) | Q(participants__id__in=team_ids)
        ).distinct()
    return Meeting.objects.filter(is_deleted=False, participants=user).distinct()


# --- Editability queries: what users can modify ---


def get_editable_projects(user):  # Projects the user can create / edit / delete
    from attendance.models import Project
    if user.profile.role == 'admin':
        return Project.objects.filter(is_deleted=False)
    elif user.profile.role == 'manager':
        return Project.objects.filter(is_deleted=False, created_by=user)
    return Project.objects.none()


def get_editable_tasks(user):  # Tasks the user can edit or change status on
    from attendance.models import ProjectTask
    if user.profile.role == 'admin':
        return ProjectTask.objects.filter(is_deleted=False)
    elif user.profile.role == 'manager':
        team_ids = user.profile.team_members.values_list('user_id', flat=True)
        return ProjectTask.objects.filter(
            Q(is_deleted=False),
            Q(manager=user) | Q(assigned_to_id__in=list(team_ids))
        ).distinct()
    return ProjectTask.objects.filter(is_deleted=False, assigned_to=user)


def get_editable_timeentries(user):  # Time entries the user can modify / correct / approve / delete
    from attendance.models import TimeEntry
    if user.profile.role == 'admin':
        return TimeEntry.objects.filter(is_deleted=False)
    elif user.profile.role == 'manager':
        team_ids = list(user.profile.team_members.values_list('user_id', flat=True)) + [user.id]
        return TimeEntry.objects.filter(is_deleted=False, user_id__in=team_ids)
    return TimeEntry.objects.filter(is_deleted=False, user=user)


def get_editable_attendances(user):  # Attendances the user can correct / finalize / override
    from attendance.models import Attendance
    if user.profile.role == 'admin':
        return Attendance.objects.all()
    elif user.profile.role == 'manager':
        team_ids = list(user.profile.team_members.values_list('user_id', flat=True)) + [user.id]
        return Attendance.objects.filter(user_id__in=team_ids)
    return Attendance.objects.filter(user=user)


def get_editable_meetings(user):  # Meetings the user can edit / cancel / delete
    from attendance.models import Meeting
    if user.profile.role == 'admin':
        return Meeting.objects.filter(is_deleted=False)
    elif user.profile.role == 'manager':
        return Meeting.objects.filter(is_deleted=False, created_by=user)
    return Meeting.objects.none()


# --- Object-level permission checks ---


def can_edit_project(user, project):
    if user.profile.role == 'admin':
        return True
    if user.profile.role == 'manager':
        return get_editable_projects(user).filter(pk=project.pk).exists()
    return False


def can_edit_task(user, task):
    if user.profile.role == 'admin':
        return True
    if user.profile.role == 'manager':
        return get_editable_tasks(user).filter(pk=task.pk).exists()
    return task.assigned_to == user


def can_edit_timeentry(user, entry):
    if user.profile.role == 'admin':
        return True
    if user.profile.role == 'manager':
        return get_editable_timeentries(user).filter(pk=entry.pk).exists()
    return entry.user == user


def can_edit_attendance(user, attendance):
    if user.profile.role == 'admin':
        return True
    if user.profile.role == 'manager':
        return get_editable_attendances(user).filter(pk=attendance.pk).exists()
    return attendance.user == user


def can_edit_meeting(user, meeting):
    if user.profile.role == 'admin':
        return True
    if user.profile.role == 'manager':
        return meeting.created_by == user or meeting.created_by is None
    return meeting.created_by == user


def can_edit_object(user, obj):  # Dispatch to the correct permission check based on object type
    type_map = {
        'Project': can_edit_project,
        'ProjectTask': can_edit_task,
        'TimeEntry': can_edit_timeentry,
        'Attendance': can_edit_attendance,
        'Meeting': can_edit_meeting,
    }
    checker = type_map.get(obj.__class__.__name__)
    if checker:
        return checker(user, obj)
    return user.profile.role == 'admin'


def can_override(user):  # Only admins can perform override / force operations
    return user.profile.role == 'admin'


def can_view_team_data(user):  # Managers and admins can view team-level data
    return user.profile.role in ('admin', 'manager')
