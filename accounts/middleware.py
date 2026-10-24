from django.utils.deprecation import MiddlewareMixin
from .permissions import (
    has_permission, can_override, can_view_team_data,
    get_visible_projects, get_visible_tasks, get_visible_users,
)


class PermissionMiddleware(MiddlewareMixin):  # Attach a permissions dict to every request for templates/views
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
        try:
            role = request.user.profile.role
        except AttributeError:
            return None
        request.permissions = _build_permission_context(request.user, role)
        return None


def _build_permission_context(user, role):  # Build a dictionary of boolean permission flags
    can = {}
    is_admin = role == 'admin'
    is_manager = role == 'manager'
    is_employee = role == 'employee'

    # --- Role-based flags ---
    can['is_admin'] = is_admin
    can['is_manager'] = is_manager
    can['is_employee'] = is_employee
    can['is_manager_or_admin'] = is_admin or is_manager

    # --- Feature-level permissions by role ---
    can['override'] = is_admin
    can['view_team_data'] = is_admin or is_manager
    can['manage_projects'] = is_admin or is_manager
    can['manage_clients'] = is_admin or is_manager
    can['manage_tasks'] = is_admin or is_manager
    can['manage_meetings'] = is_admin or is_manager
    can['manage_employees'] = is_admin
    can['view_reports'] = is_admin or is_manager
    can['export_data'] = is_admin or is_manager

    # --- Fine-grained permission codenames ---
    can['can_view_projects'] = has_permission(user, 'can_view_projects')
    can['can_manage_projects'] = has_permission(user, 'can_manage_projects')
    can['can_view_tasks'] = has_permission(user, 'can_view_tasks')
    can['can_manage_tasks'] = has_permission(user, 'can_manage_tasks')
    can['can_claim_tasks'] = has_permission(user, 'can_claim_tasks')
    can['can_view_time_entries'] = has_permission(user, 'can_view_time_entries')
    can['can_manage_time_entries'] = has_permission(user, 'can_manage_time_entries')
    can['can_correct_time'] = has_permission(user, 'can_correct_time')
    can['can_view_attendance'] = has_permission(user, 'can_view_attendance')
    can['can_view_all_attendance'] = has_permission(user, 'can_view_all_attendance')
    can['can_view_reports'] = has_permission(user, 'can_view_reports')
    can['can_export_data'] = has_permission(user, 'can_export_data')
    can['can_view_clients'] = has_permission(user, 'can_view_clients')
    can['can_manage_clients'] = has_permission(user, 'can_manage_clients')
    can['can_view_meetings'] = has_permission(user, 'can_view_meetings')
    can['can_manage_meetings'] = has_permission(user, 'can_manage_meetings')
    can['can_view_holidays'] = has_permission(user, 'can_view_holidays')
    can['can_manage_holidays'] = has_permission(user, 'can_manage_holidays')
    can['can_manage_users'] = has_permission(user, 'can_manage_users')
    can['can_manage_roles'] = has_permission(user, 'can_manage_roles')

    return can
