from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from functools import wraps


def _active_check(user):  # Check if user account is active
    return user.is_active


# --- Role-based access decorators ---


def admin_required(view_func):  # Only admins can access this view
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            if not request.user.is_authenticated or not _active_check(request.user):
                return redirect('login')
            if request.user.is_superuser or request.user.profile.role == 'admin':
                return view_func(request, *args, **kwargs)
        except (ObjectDoesNotExist, AttributeError):
            pass
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login')
    return wrapper


def manager_or_admin_required(view_func):  # Admins or managers can access this view
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            if not request.user.is_authenticated or not _active_check(request.user):
                return redirect('login')
            role = request.user.profile.role
            if role in ('admin', 'manager'):
                return view_func(request, *args, **kwargs)
        except (ObjectDoesNotExist, AttributeError):
            pass
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login')
    return wrapper


def employee_required(view_func):  # Only employees can access this view
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            if not request.user.is_authenticated or not _active_check(request.user):
                return redirect('login')
            if request.user.profile.role == 'employee':
                return view_func(request, *args, **kwargs)
        except (ObjectDoesNotExist, AttributeError):
            pass
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('login')
    return wrapper


def require_permission(codename):  # Require a specific Django permission codename
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated or not _active_check(request.user):
                return redirect('login')
            if not request.user.has_perm(f'attendance.{codename}') and not request.user.has_perm(f'accounts.{codename}'):
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('login')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def require_object_perm(perm_check_fn, lookup_field='pk', lookup_kwarg=None):  # Require object-level permission using a check function
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated or not _active_check(request.user):
                return redirect('login')
            obj = kwargs.get(lookup_kwarg or lookup_field)




            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def can_override_required(view_func):  # Only admins can perform override operations
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not _active_check(request.user):
            return redirect('login')
        if request.user.profile.role != 'admin':
            messages.error(request, 'Only administrators can perform override operations.')
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


def same_user_or_admin_required(user_kwarg='user_id'):  # Users can access own data; admin can access all
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated or not _active_check(request.user):
                return redirect('login')
            target_user_id = int(kwargs.get(user_kwarg, 0))
            if request.user.profile.role != 'admin' and request.user.id != target_user_id:
                messages.error(request, 'You can only access your own data.')
                return redirect('login')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
