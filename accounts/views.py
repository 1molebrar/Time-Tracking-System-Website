from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .decorators import admin_required, manager_or_admin_required, can_override_required, require_permission
from .forms import EmployeeCreateForm, EmployeeEditForm
from .models import UserProfile
from attendance.audit import audit_log, log_create, log_update, log_delete


def _redirect_by_role(user):  # Redirect user to their role-specific dashboard
    try:
        role = user.profile.role
        if role == 'admin':
            return redirect('admin_dashboard')
        if role == 'manager':
            return redirect('manager_dashboard')
        return redirect('employee_dashboard')
    except:
        return redirect('employee_dashboard')


# --- Authentication views ---

@never_cache
def login_view(request):
    if request.user.is_authenticated:  # Already logged in; redirect to dashboard
        return _redirect_by_role(request.user)

    if request.method == 'POST':  # Process login form submission
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return _redirect_by_role(user)
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'registration/login.html')


def logout_view(request):  # Log out and redirect to login page
    logout(request)
    return redirect('login')


# --- Employee management views ---

@login_required
@admin_required
def employee_list(request):  # List active and inactive employees and managers
    employees = User.objects.filter(profile__role__in=['employee', 'manager'], is_active=True).order_by('username')
    inactive = User.objects.filter(profile__role__in=['employee', 'manager'], is_active=False).order_by('username')
    managers = User.objects.filter(profile__role='manager', is_active=True)
    return render(request, 'admin/employee_list.html', {
        'active_employees': employees,
        'inactive_employees': inactive,
        'managers': managers,
    })


@login_required
@admin_required
def employee_add(request):  # Show form and create a new employee
    if request.method == 'POST':
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Employee created successfully.')
            return redirect('employee_list')
    else:
        form = EmployeeCreateForm()
    return render(request, 'admin/employee_form.html', {'form': form, 'title': 'Add Employee'})


@login_required
@admin_required
@require_permission('can_manage_users')
@require_permission('can_manage_roles')
def employee_edit(request, user_id):  # Show form and update an existing employee
    user = get_object_or_404(User, pk=user_id, profile__role__in=['employee', 'manager'])
    if request.method == 'POST':
        form = EmployeeEditForm(request.POST, instance=user)
        if form.is_valid():
            old_role = user.profile.role
            old_manager = user.profile.manager.user.username if user.profile.manager else None
            form.save()
            new_manager = user.profile.manager.user.username if user.profile.manager else None
            if old_manager != new_manager or old_role != user.profile.role:  # Log role/manager changes
                audit_log(request.user, 'override',
                    f'Employee "{user.username}" edited: role={old_role}->{user.profile.role}, manager={old_manager}->{new_manager}',
                    target=user,
                    metadata={
                        'changes': {'role': {'old': old_role, 'new': user.profile.role}, 'manager': {'old': old_manager, 'new': new_manager}},
                        'employee_id': user.id,
                    },
                    request=request)
            messages.success(request, 'Employee updated successfully.')
            return redirect('employee_list')
    else:
        form = EmployeeEditForm(instance=user)
    return render(request, 'admin/employee_form.html', {'form': form, 'title': 'Edit Employee'})


@login_required
@admin_required
def employee_deactivate(request, user_id):  # Deactivate an employee or manager with a reason
    user = get_object_or_404(User, pk=user_id, is_active=True)
    if user.profile.role not in ('employee', 'manager'):
        messages.error(request, 'Cannot deactivate this user.')
        return redirect('employee_list')
    if user.profile.role == 'manager':
        # Step 1: unassign this manager from all team members
        UserProfile.objects.filter(manager=user.profile).update(manager=None)
        reasons = user.profile.get_deactivation_reasons()
        if request.method == 'POST':
            reason = request.POST.get('deactivation_reason', '')
            if reason not in dict(reasons):
                messages.error(request, 'Please select a deactivation reason.')
                return render(request, 'admin/employee_confirm_deactivate.html', {
                    'employee': user,
                    'deactivation_reasons': reasons,
                })
        user.is_active = False
        user.profile.deactivation_reason = reason
        user.profile.save()
        user.save()
        audit_log(request.user, 'deactivation',
            f'Deactivated "{user.username}" reason: {reason}',
            target=user, request=request)
        messages.success(request, f'User "{user.username}" deactivated.')
        return redirect('employee_list')
    return render(request, 'admin/employee_confirm_deactivate.html', {
        'employee': user,
        'deactivation_reasons': user.profile.get_deactivation_reasons(),
    })


@login_required
@admin_required
def employee_activate(request, user_id):  # Reactivate a deactivated employee
    user = get_object_or_404(User, pk=user_id, is_active=False)
    user.is_active = True
    user.profile.deactivation_reason = None
    user.profile.save()
    user.save()
    messages.success(request, f'User "{user.username}" reactivated successfully.')
    return redirect('employee_list')
