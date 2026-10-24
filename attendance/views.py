from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, JsonResponse
from datetime import datetime, timedelta, time, date
from django.template.loader import render_to_string
import csv
import calendar

from .models import Attendance, Break, Task, Notification, Client, Project, ProjectTask, TimeEntry, Holiday, Meeting, AuditLog, LeaveRequest
from .audit import audit_log, log_create, log_update, log_delete
from .notifications import (
    notify_clock_in, notify_break_start,
    check_mid_shift_reminder, check_extended_break, check_missing_clock_out
)
from accounts.decorators import admin_required, employee_required, manager_or_admin_required, require_permission
from accounts.permissions import (
    get_visible_projects, get_visible_tasks,
    get_visible_attendances, get_visible_users,
    get_editable_projects, get_editable_tasks,
    get_editable_timeentries, get_editable_attendances,
    get_editable_meetings,
    can_edit_project, can_edit_task, can_edit_timeentry,
    can_edit_attendance, can_edit_meeting, can_edit_object,
    can_override,
)



# --- Helpers ---

def get_redirect_url(request):  # Determine which dashboard URL the user should go to
    try:
        role = request.user.profile.role
        if role == 'admin':
            return 'admin_dashboard'
        if role == 'manager':
            return 'manager_dashboard'
    except:
        pass
    return 'employee_dashboard'

def get_managed_users(user):  # Get users visible/managed by this user
    return get_visible_users(user)



def home_redirect(request):  # Root URL: redirect to role-appropriate dashboard
    if request.user.is_authenticated:
        try:
            role = request.user.profile.role
            if role == 'admin':
                return redirect('admin_dashboard')
            if role == 'manager':
                return redirect('manager_dashboard')
            return redirect('employee_dashboard')
        except:
            return redirect('employee_dashboard')
    return redirect('login')



# --- Employee Views ---

@login_required
@employee_required
def employee_dashboard(request):  # Main dashboard: attendance status, tasks, meetings
    today = timezone.now().date()
    now = timezone.now()
    attendance = Attendance.objects.filter(user=request.user, date=today).first()
    active_break = None
    today_breaks = []
    if attendance:
        today_breaks = Break.objects.filter(attendance=attendance).order_by('break_start')
        active_break = today_breaks.filter(break_end__isnull=True).first()
        check_mid_shift_reminder(request.user, attendance)
        check_extended_break(request.user, attendance)
    check_missing_clock_out(request.user)
    my_tasks = ProjectTask.objects.filter(assigned_to=request.user).exclude(status='done').select_related('project')[:5]
    all_user_tasks = ProjectTask.objects.filter(assigned_to=request.user)
    task_stats = {
        'total': all_user_tasks.count(),
        'todo': all_user_tasks.filter(status='todo').count(),
        'in_progress': all_user_tasks.filter(status='in_progress').count(),
        'done': all_user_tasks.filter(status='done').count(),
    }
    open_available = ProjectTask.objects.filter(assigned_to__isnull=True, status='todo').count()
    today_holiday = Holiday.get_holiday(today)
    upcoming_meetings = Meeting.objects.filter(participants=request.user, date__gte=today).order_by('date', 'start_time')[:5]
    my_leaves = LeaveRequest.objects.filter(employee=request.user).order_by('-created_at')[:5]

    shift_progress = 0
    if attendance and attendance.check_in:
        total_secs = (attendance.check_out - attendance.check_in).total_seconds() if attendance.check_out else (now - attendance.check_in).total_seconds()
        break_mins = Break.objects.filter(attendance=attendance).aggregate(total=Sum('duration_minutes'))['total'] or 0
        work_secs = max(0, total_secs - (break_mins * 60))
        shift_progress = min(100, round((work_secs / (8 * 3600)) * 100, 1))

    context = {
        'attendance': attendance,
        'active_break': active_break,
        'today_breaks': today_breaks,
        'now': now,
        'today': today,
        'my_tasks': my_tasks,
        'task_stats': task_stats,
        'open_tasks_count': open_available,
        'today_holiday': today_holiday,
        'upcoming_meetings': upcoming_meetings,
        'shift_progress': shift_progress,
        'my_leaves': my_leaves,
    }
    return render(request, 'employee/dashboard.html', context)



@login_required
def clock_in(request):  # Clock in: start the workday session
    today = timezone.now().date()
    now = timezone.now()
    redirect_url = get_redirect_url(request)

    if LeaveRequest.is_on_leave(request.user, today):
        messages.error(request, 'You are on approved leave today. Clock-in is not available.')
        return redirect(redirect_url)

    today_holiday = Holiday.get_holiday(today)
    if today_holiday:
        messages.info(request, f'Today is a public holiday: {today_holiday.name}. Clock-in is optional on holidays.')

    existing = Attendance.objects.filter(user=request.user, date=today).first()
    if existing:
        if existing.check_in and not existing.check_out:
            messages.error(request, 'You are already clocked in!')
            return redirect(redirect_url)
        elif existing.check_in and existing.check_out:
            messages.error(request, 'You have already clocked out today.')
            return redirect(redirect_url)

    attendance, created = Attendance.objects.get_or_create(
        user=request.user, date=today, defaults={'check_in': now}
    )
    if created or not attendance.check_in:
        late_threshold = timezone.make_aware(
            datetime.combine(today, time(9, 0, 0)), timezone.get_current_timezone()
        )
        if now > late_threshold:
            attendance.is_late = True
        attendance.check_in = now
        attendance.is_completed = False
        attendance.save()
        notify_clock_in(request.user)
        audit_log(request.user, 'clock_in', f'Clocked in at {now.strftime("%H:%M")}', request=request)
        messages.success(request, 'Clocked in successfully! Session started.')
    else:
        messages.info(request, 'You are already clocked in.')
    return redirect(redirect_url)

@login_required
def clock_out(request):  # Clock out: end session, calculate totals
    today = timezone.now().date()
    now = timezone.now()
    redirect_url = get_redirect_url(request)
    attendance = Attendance.objects.filter(
        user=request.user, date=today, check_in__isnull=False, check_out__isnull=True
    ).first()
    if not attendance:
        messages.error(request, 'No active session to clock out from.')
        return redirect(redirect_url)

    can, msg = attendance.can_clock_out()
    if not can:
        messages.error(request, msg)
        return redirect(redirect_url)

    active_break = Break.objects.filter(attendance=attendance, break_end__isnull=True).first()
    if active_break:
        active_break.break_end = now
        active_break.duration_minutes = int((now - active_break.break_start).total_seconds() / 60)
        active_break.save()
    attendance.finalize()
    audit_log(request.user, 'clock_out', f'Clocked out. Total: {attendance.total_hours}h', request=request)
    messages.success(request, 'Clocked out successfully!')
    return redirect(redirect_url)

@login_required
def break_start(request):  # Start a break, auto-pause running timer
    today = timezone.now().date()
    now = timezone.now()
    redirect_url = get_redirect_url(request)
    attendance = Attendance.objects.filter(
        user=request.user, date=today, check_in__isnull=False, check_out__isnull=True
    ).first()
    if not attendance:
        messages.error(request, 'You must clock in first before taking a break.')
        return redirect(redirect_url)
    active_break = Break.objects.filter(attendance=attendance, break_end__isnull=True).first()
    if active_break:
        messages.error(request, 'You are already on a break!')
        return redirect(redirect_url)

    running_entry = TimeEntry.objects.filter(user=request.user, is_running=True).first()
    paused_entry = None
    if running_entry:
        running_entry.stop()
        paused_entry = running_entry
    Break.objects.create(attendance=attendance, break_start=now, paused_entry=paused_entry)
    notify_break_start(request.user, attendance)
    msg = 'Break started! Timer paused automatically.' if paused_entry else 'Break started! Take your time.'
    messages.success(request, msg)
    return redirect(redirect_url)

@login_required
def break_end(request):  # End break, resume paused timer if any
    today = timezone.now().date()
    now = timezone.now()
    redirect_url = get_redirect_url(request)
    attendance = Attendance.objects.filter(
        user=request.user, date=today, check_in__isnull=False, check_out__isnull=True
    ).first()
    if not attendance:
        messages.error(request, 'No active work session.')
        return redirect(redirect_url)
    active_break = Break.objects.filter(attendance=attendance, break_end__isnull=True).first()
    if not active_break:
        messages.error(request, 'No active break found.')
        return redirect(redirect_url)

    paused_entry = active_break.end()
    if paused_entry:
        TimeEntry.objects.create(
            user=request.user, task=paused_entry.task, attendance=attendance,
            start_time=now, is_running=True
        )
        msg = f'Break ended ({active_break.duration_minutes} min). Timer resumed for "{paused_entry.task.title}".'
    else:
        msg = f'Break ended. Duration: {active_break.duration_minutes} minutes.'
    messages.success(request, msg)
    return redirect(redirect_url)

@login_required
@employee_required
def attendance_history(request):  # Show employee's own attendance records
    attendances = Attendance.objects.filter(user=request.user).order_by('-date', '-check_in')
    return render(request, 'attendance/history.html', {'attendances': attendances})



# --- Admin / Manager Dashboard ---

@login_required
@admin_required
def admin_dashboard(request):  # Admin dashboard: all employees and managers
    return _dashboard_view(request, User.objects.filter(profile__role__in=['employee', 'manager'], is_active=True))

@login_required
@manager_or_admin_required
def manager_dashboard(request):  # Manager dashboard: own team only
    if request.user.profile.role == 'admin':
        return redirect('admin_dashboard')
    team = User.objects.filter(profile__manager=request.user.profile, is_active=True)
    return _dashboard_view(request, team)

def _dashboard_view(request, employees):  # Shared rendering: stats, chart data, context
    today = timezone.now().date()
    now = timezone.now()
    total_employees = employees.count()
    today_attendances = Attendance.objects.filter(date=today, user__in=employees)
    clocked_in = today_attendances.filter(check_in__isnull=False, check_out__isnull=True).count()
    late_count = today_attendances.filter(is_late=True).count()
    on_leave_today = User.objects.filter(
        leave_requests__start_date__lte=today,
        leave_requests__end_date__gte=today,
        leave_requests__status='approved'
    ).distinct().count()
    absent = max(0, total_employees - today_attendances.values('user').distinct().count() - on_leave_today)

    recent_attendances = today_attendances.order_by('user__username')
    my_attendance = Attendance.objects.filter(user=request.user, date=today).first()
    active_break = None
    today_breaks = []
    if my_attendance:
        active_break = Break.objects.filter(attendance=my_attendance, break_end__isnull=True).first()
        today_breaks = Break.objects.filter(attendance=my_attendance).order_by('break_start')
        check_mid_shift_reminder(request.user, my_attendance)
        check_extended_break(request.user, my_attendance)
    check_missing_clock_out(request.user)

    # Build last 7 days chart data
    days_labels, daily_counts, late_counts = [], [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        days_labels.append(d.strftime('%a %d'))
        day_att = Attendance.objects.filter(date=d, user__in=employees)
        daily_counts.append(day_att.count())
        late_counts.append(day_att.filter(is_late=True).count())

    # Build this week's hours data
    week_start = today - timedelta(days=today.weekday())
    week_labels, week_hours = [], []
    for i in range(5):
        d = week_start + timedelta(days=i)
        week_labels.append(d.strftime('%a'))
        total = Attendance.objects.filter(date=d, user__in=employees).aggregate(s=Sum('total_hours'))['s'] or 0
        week_hours.append(round(total, 1))

    shift_progress = 0
    if my_attendance and my_attendance.check_in:
        total_secs = (my_attendance.check_out - my_attendance.check_in).total_seconds() if my_attendance.check_out else (now - my_attendance.check_in).total_seconds()
        break_mins = Break.objects.filter(attendance=my_attendance).aggregate(total=Sum('duration_minutes'))['total'] or 0
        work_secs = max(0, total_secs - (break_mins * 60))
        shift_progress = min(100, round((work_secs / (8 * 3600)) * 100, 1))


    active_projects = Project.objects.filter(status='active').count()
    today_holiday = Holiday.get_holiday(today)
    upcoming_meetings = Meeting.objects.filter(date__gte=today).order_by('date', 'start_time')[:10]

    context = {
        'total_employees': total_employees,
        'clocked_in': clocked_in,
        'late_count': late_count,
        'absent': max(0, absent),
        'today_attendances': recent_attendances,
        'today': today,
        'now': now,
        'my_attendance': my_attendance,
        'active_break': active_break,
        'today_breaks': today_breaks,
        'days_labels': days_labels,
        'late_counts': late_counts,
        'week_labels': week_labels,
        'week_hours': week_hours,
        'shift_progress': shift_progress,
        'active_projects': active_projects,
        'today_holiday': today_holiday,
        'upcoming_meetings': upcoming_meetings,
        'employees_list': employees,
    }
    return render(request, 'admin/dashboard.html', context)



# --- Timer Views ---

@login_required
def timer_start(request, task_id):  # Start timer: begin tracking time on a task
    task = get_object_or_404(ProjectTask, pk=task_id)
    now = timezone.now()

    attendance = TimeEntry.get_active_session(request.user)
    if not attendance:
        messages.error(request, 'You must clock in before starting a timer.')
        return redirect(request.META.get('HTTP_REFERER', 'employee_dashboard'))

    # Stop any other running timers first
    for entry in TimeEntry.objects.filter(user=request.user, is_running=True):
        entry.stop()

    if task.status != 'in_progress':
        task._old_status = task.status
        task.set_status('in_progress', user=request.user)
    TimeEntry.objects.create(
        user=request.user, task=task, attendance=attendance,
        start_time=now, is_running=True
    )
    messages.success(request, f'Timer started for "{task.title}"')
    return redirect(request.META.get('HTTP_REFERER', 'employee_dashboard'))

@login_required
def timer_stop(request, entry_id=None):  # Stop timer: end tracking, save duration
    if entry_id:
        entries = TimeEntry.objects.filter(pk=entry_id, user=request.user, is_running=True)
    else:
        entries = TimeEntry.objects.filter(user=request.user, is_running=True)
    updated = 0
    for entry in entries:
        entry.stop()
        updated += 1
    if updated:
        messages.success(request, 'Timer stopped.')
    else:
        messages.info(request, 'No active timer found.')
    return redirect(request.META.get('HTTP_REFERER', 'employee_dashboard'))

def _get_active_timer(user):  # Helper: get user's running timer entry
    return TimeEntry.objects.filter(user=user, is_running=True).select_related('task__project').first()



# --- Client CRUD ---

@login_required
@manager_or_admin_required
def client_list(request):  # List all clients, active first
    clients = Client.objects.all().order_by('-is_active', 'name')
    return render(request, 'attendance/client_list.html', {'clients': clients})

@login_required
@manager_or_admin_required
@require_permission('can_manage_clients')
def client_add(request):  # Create a new client record
    if request.method == 'POST':
        client = Client.objects.create(
            name=request.POST['name'],
            email=request.POST.get('email', ''),
            company=request.POST.get('company', ''),
            phone=request.POST.get('phone', ''),
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )
        messages.success(request, f'Client "{client.name}" created.')
        return redirect('client_list')
    return render(request, 'attendance/client_form.html', {'client': None})

@login_required
@manager_or_admin_required
@require_permission('can_manage_clients')
def client_edit(request, client_id):  # Update an existing client
    client = get_object_or_404(Client, pk=client_id)
    if request.method == 'POST':
        client.name = request.POST['name']
        client.email = request.POST.get('email', '')
        client.company = request.POST.get('company', '')
        client.phone = request.POST.get('phone', '')
        client.notes = request.POST.get('notes', '')
        client.save()
        messages.success(request, 'Client updated.')
        return redirect('client_list')
    return render(request, 'attendance/client_form.html', {'client': client})

@login_required
@manager_or_admin_required
@require_permission('can_manage_clients')
def client_toggle(request, client_id):  # Toggle client's active/inactive status
    client = get_object_or_404(Client, pk=client_id)
    client.is_active = not client.is_active
    client.save()
    messages.success(request, f'Client {"activated" if client.is_active else "deactivated"}.')
    return redirect('client_list')



# --- Project CRUD ---

@login_required
@manager_or_admin_required
def project_list(request):  # List projects visible to this user
    projects = get_visible_projects(request.user).select_related('client').order_by('-status', '-created_at')
    return render(request, 'attendance/project_list.html', {'projects': projects})

@login_required
@manager_or_admin_required
@require_permission('can_manage_projects')
def project_add(request):  # Create a new project with optional client
    clients = Client.objects.filter(is_active=True)
    if request.method == 'POST':
        project = Project.objects.create(
            name=request.POST['name'],
            description=request.POST.get('description', ''),
            client_id=request.POST.get('client') or None,
            status=request.POST.get('status', 'active'),
            created_by=request.user,
        )
        log_create(request.user, project, request=request)
        messages.success(request, f'Project "{project.name}" created.')
        return redirect('project_list')
    return render(request, 'attendance/project_form.html', {'project': None, 'clients': clients})

# --- Calendar ---

@login_required

@login_required
def calendar_view(request):  # Monthly calendar: attendance, holidays, tasks, meetings
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    holidays = Holiday.objects.filter(date__gte=first_day, date__lte=last_day, is_active=True)
    holiday_dates = {h.date: h for h in holidays}

    attendances = Attendance.objects.filter(
        user=request.user, date__gte=first_day, date__lte=last_day
    )
    attendance_map = {a.date: a for a in attendances}

    tasks = ProjectTask.objects.filter(
        assigned_to=request.user, deadline__gte=first_day, deadline__lte=last_day
    ).select_related('project')

    if request.user.profile.role in ('admin', 'manager'):
        meetings_qs = Meeting.objects.filter(date__gte=first_day, date__lte=last_day)
    else:
        meetings_qs = Meeting.objects.filter(participants=request.user, date__gte=first_day, date__lte=last_day)
    meetings = meetings_qs.select_related('created_by').prefetch_related('participants').order_by('date', 'start_time')
    meeting_map = {}
    for m in meetings:
        meeting_map.setdefault(m.date, []).append(m)

    today_holiday = Holiday.get_holiday(today)

    # Build calendar grid by weeks starting from Monday
    weeks = []
    week = []
    day = first_day
    while day.weekday() != 0:
        day -= timedelta(days=1)
    while day <= last_day:
        week.append(day)
        if day.weekday() == 6:
            weeks.append(week)
            week = []
        day += timedelta(days=1)
    if week:
        weeks.append(week)

    prev_month = month - 1 or 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return render(request, 'attendance/calendar.html', {
        'weeks': weeks,
        'month': month,
        'month_name': calendar.month_name[month],
        'year': year,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'holiday_dates': holiday_dates,
        'attendance_map': attendance_map,
        'tasks': tasks,
        'today_holiday': today_holiday,
        'today': today,
        'meetings': meetings,
        'meeting_map': meeting_map,
    })




# --- Meetings ---

@login_required
def meeting_list(request):  # List meetings: live, upcoming, and past groups
    from datetime import datetime, timedelta
    now = timezone.now()
    today = now.date()

    base_qs = Meeting.objects.filter(is_archived=False, is_deleted=False).select_related('created_by').prefetch_related('participants', 'attendees')
    if request.user.profile.role not in ('admin', 'manager'):
        base_qs = base_qs.filter(participants=request.user)

    # Auto-update meeting status based on time
    for m in base_qs:
        if m.status == 'scheduled' and m.is_ongoing:
            m.status = 'ongoing'
            m.save(update_fields=['status'])
        elif m.status in ('scheduled', 'ongoing') and m.is_past:
            if m.attendees.exists():
                m.status = 'completed'
            else:
                m.status = 'missed'
            m.save(update_fields=['status'])

    # Re-fetch to get updated statuses
    base_qs = Meeting.objects.filter(is_archived=False, is_deleted=False).select_related('created_by').prefetch_related('participants', 'attendees')
    if request.user.profile.role not in ('admin', 'manager'):
        base_qs = base_qs.filter(participants=request.user)

    live_meetings = []
    upcoming_meetings = []
    past_meetings = []

    for m in base_qs:
        if m.status == 'ongoing' or (m.status == 'scheduled' and m.is_today and m.is_ongoing):
            live_meetings.append(m)
        elif m.status == 'scheduled' and not m.is_past:
            upcoming_meetings.append(m)
        elif m.status in ('completed', 'missed', 'cancelled'):
            past_meetings.append(m)

    upcoming_meetings.sort(key=lambda x: (x.date, x.start_time))
    past_meetings.sort(key=lambda x: (x.date, x.start_time), reverse=True)

    return render(request, 'attendance/meeting_list.html', {
        'live_meetings': live_meetings,
        'upcoming_meetings': upcoming_meetings,
        'past_meetings': past_meetings,
        'today': today,
        'now': now,
    })


@login_required
@manager_or_admin_required
@require_permission('can_manage_meetings')
def meeting_create(request):  # Create meeting with participants and notifications
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        date_val = request.POST.get('date', '').strip()
        start_time = request.POST.get('start_time', '').strip()
        end_time = request.POST.get('end_time', '').strip()
        participant_ids = request.POST.getlist('participants')

        if not all([title, date_val, start_time, end_time]):
            messages.error(request, 'Please fill in all required fields.')
            return redirect('meeting_create')

        from datetime import datetime
        try:
            parsed_date = datetime.strptime(date_val, '%Y-%m-%d').date()
            parsed_start = datetime.strptime(start_time, '%H:%M').time()
            parsed_end = datetime.strptime(end_time, '%H:%M').time()
        except ValueError:
            messages.error(request, 'Invalid date or time format.')
            return redirect('meeting_create')

        meeting_type = request.POST.get('meeting_type', 'other')
        meeting = Meeting.objects.create(
            title=title,
            description=description,
            meeting_type=meeting_type,
            date=parsed_date,
            start_time=parsed_start,
            end_time=parsed_end,
            created_by=request.user,
        )
        if participant_ids:
            users = User.objects.filter(id__in=participant_ids)
            meeting.participants.set(users)
            for user in users:
                Notification.objects.create(
                    user=user,
                    message=f'Meeting invited: "{title}" on {meeting.date} at {meeting.start_time:%H:%M} ({meeting.duration_minutes} min)',
                    type='meeting_invite',
                )

        log_create(request.user, meeting, request=request)
        messages.success(request, f'Meeting "{title}" created and {meeting.participants.count()} participants notified.')
        return redirect('meeting_list')

    employees = User.objects.filter(profile__role__in=['employee', 'manager'], is_active=True).order_by('username')
    if request.user.profile.role != 'admin':
        employees = get_visible_users(request.user)
    return render(request, 'attendance/meeting_form.html', {
        'employees': employees,
        'is_edit': False,
        'meeting_types': Meeting.MEETING_TYPES,
    })


@login_required
@manager_or_admin_required
@require_permission('can_manage_meetings')
def meeting_edit(request, meeting_id):  # Edit meeting title, time, participants
    meeting = get_object_or_404(Meeting, pk=meeting_id)
    if not can_edit_meeting(request.user, meeting):
        messages.error(request, 'You do not have permission to edit this meeting.')
        return redirect('meeting_list')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        date_val = request.POST.get('date', '').strip()
        start_time = request.POST.get('start_time', '').strip()
        end_time = request.POST.get('end_time', '').strip()
        participant_ids = request.POST.getlist('participants')

        if not all([title, date_val, start_time, end_time]):
            messages.error(request, 'Please fill in all required fields.')
            return redirect('meeting_edit', meeting_id=meeting.id)

        from datetime import datetime
        try:
            parsed_date = datetime.strptime(date_val, '%Y-%m-%d').date()
            parsed_start = datetime.strptime(start_time, '%H:%M').time()
            parsed_end = datetime.strptime(end_time, '%H:%M').time()
        except ValueError:
            messages.error(request, 'Invalid date or time format.')
            return redirect('meeting_edit', meeting_id=meeting.id)

        meeting.title = title
        meeting.description = description
        meeting.meeting_type = request.POST.get('meeting_type', meeting.meeting_type)
        meeting.date = parsed_date
        meeting.start_time = parsed_start
        meeting.end_time = parsed_end
        meeting.save()

        if participant_ids:
            meeting.participants.set(User.objects.filter(id__in=participant_ids))

        log_update(request.user, meeting, request=request)
        messages.success(request, f'Meeting "{title}" updated.')
        return redirect('meeting_list')

    employees = User.objects.filter(profile__role__in=['employee', 'manager'], is_active=True).order_by('username')
    if request.user.profile.role != 'admin':
        employees = get_visible_users(request.user)
    return render(request, 'attendance/meeting_form.html', {
        'meeting': meeting,
        'employees': employees,
        'is_edit': True,
        'selected_ids': list(meeting.participants.values_list('id', flat=True)),
        'meeting_types': Meeting.MEETING_TYPES,
    })


@login_required
def meeting_detail(request, meeting_id):  # Show full meeting details
    meeting = get_object_or_404(
        Meeting.objects.select_related('created_by').prefetch_related('participants', 'attendees'),
        pk=meeting_id, is_deleted=False,
    )
    if request.user.profile.role not in ('admin', 'manager') and request.user not in meeting.participants.all():
        messages.error(request, 'You do not have access to this meeting.')
        return redirect('employee_dashboard')
    now = timezone.now()
    return render(request, 'attendance/meeting_detail.html', {'meeting': meeting, 'now': now})


@login_required
def meeting_join(request, meeting_id):  # Mark user as attending the meeting
    meeting = get_object_or_404(Meeting, pk=meeting_id)
    if request.user not in meeting.participants.all() and request.user.profile.role not in ('admin', 'manager'):
        messages.error(request, 'You are not invited to this meeting.')
        return redirect('meeting_list')
    if meeting.status == 'cancelled':
        messages.error(request, 'This meeting has been cancelled.')
        return redirect('meeting_list')
    meeting.attendees.add(request.user)
    if meeting.status == 'scheduled':
        meeting.status = 'ongoing'
        meeting.save()
    messages.success(request, f'You joined "{meeting.title}".')
    return redirect('meeting_detail', meeting_id=meeting.id)


@login_required
@manager_or_admin_required
@require_permission('can_manage_meetings')
def meeting_cancel(request, meeting_id):  # Cancel a scheduled meeting
    meeting = get_object_or_404(Meeting, pk=meeting_id)
    if not can_edit_meeting(request.user, meeting):
        messages.error(request, 'You do not have permission to cancel this meeting.')
        return redirect('meeting_list')
    if request.method == 'POST':
        meeting.status = 'cancelled'
        meeting.save()
        audit_log(request.user, 'update', f'Cancelled meeting "{meeting.title}"', target=meeting, request=request)
        messages.success(request, f'Meeting "{meeting.title}" cancelled.')
        return redirect('meeting_list')
    return render(request, 'attendance/meeting_cancel.html', {'meeting': meeting})


@login_required
@manager_or_admin_required
@require_permission('can_manage_meetings')
def meeting_add_notes(request, meeting_id):  # Save meeting notes/summary
    meeting = get_object_or_404(Meeting, pk=meeting_id)
    if not can_edit_meeting(request.user, meeting):
        messages.error(request, 'You do not have permission to modify this meeting.')
        return redirect('meeting_list')
    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        meeting.notes = notes
        meeting.save()
        messages.success(request, 'Meeting notes saved.')
        return redirect('meeting_detail', meeting_id=meeting.id)
    return render(request, 'attendance/meeting_notes.html', {'meeting': meeting})


@login_required
@manager_or_admin_required
@require_permission('can_manage_meetings')
def meeting_toggle_important(request, meeting_id):  # Toggle important flag on meeting
    meeting = get_object_or_404(Meeting, pk=meeting_id)
    if not can_edit_meeting(request.user, meeting):
        messages.error(request, 'You do not have permission to modify this meeting.')
        return redirect('meeting_list')
    meeting.is_important = not meeting.is_important
    meeting.save()
    msg = 'marked as important' if meeting.is_important else 'unmarked as important'
    messages.success(request, f'Meeting "{meeting.title}" {msg}.')
    return redirect('meeting_detail', meeting_id=meeting.id)


@login_required
def meeting_archive(request):  # Show list of archived meetings
    base_qs = Meeting.objects.filter(is_archived=True).select_related('created_by').prefetch_related('participants', 'attendees')
    if request.user.profile.role not in ('admin', 'manager'):
        base_qs = base_qs.filter(participants=request.user)
    return render(request, 'attendance/meeting_archive.html', {'meetings': base_qs})


@login_required
@manager_or_admin_required
@require_permission('can_manage_meetings')
def meeting_delete(request, meeting_id):  # Soft-delete: move meeting to trash
    meeting = get_object_or_404(Meeting, pk=meeting_id)
    if not can_edit_meeting(request.user, meeting):
        messages.error(request, 'You do not have permission to delete this meeting.')
        return redirect('meeting_list')
    title = meeting.title
    meeting.soft_delete(request.user)
    log_delete(request.user, meeting, request=request)
    messages.success(request, f'Meeting "{title}" moved to trash.')
    return redirect('meeting_list')





# --- Trash / Restore ---

@login_required
@manager_or_admin_required
def trash_list(request):  # View all soft-deleted items
    """View all soft-deleted items."""
    deleted_projects = Project.objects.filter(is_deleted=True).order_by('-deleted_at')[:20]
    deleted_tasks = ProjectTask.objects.filter(is_deleted=True).select_related('project').order_by('-deleted_at')[:20]
    deleted_meetings = Meeting.objects.filter(is_deleted=True).order_by('-deleted_at')[:20]
    return render(request, 'attendance/trash_list.html', {
        'deleted_projects': deleted_projects,
        'deleted_tasks': deleted_tasks,
        'deleted_meetings': deleted_meetings,
    })


@login_required
@manager_or_admin_required
def project_restore(request, project_id):  # Restore soft-deleted project
    project = get_object_or_404(Project, pk=project_id, is_deleted=True)
    project.restore()
    log_create(request.user, project, detail=f'Restored project "{project.name}" from trash', request=request)
    messages.success(request, f'Project "{project.name}" restored.')
    return redirect('project_list')


@login_required
@manager_or_admin_required
def task_restore(request, task_id):  # Restore soft-deleted task
    task = get_object_or_404(ProjectTask, pk=task_id, is_deleted=True)
    task.restore()
    log_create(request.user, task, detail=f'Restored task "{task.title}" from trash', request=request)
    messages.success(request, f'Task "{task.title}" restored.')
    return redirect('project_detail', project_id=task.project_id)


@login_required
@manager_or_admin_required
def meeting_restore(request, meeting_id):  # Restore soft-deleted meeting
    meeting = get_object_or_404(Meeting, pk=meeting_id, is_deleted=True)
    meeting.restore()
    log_create(request.user, meeting, detail=f'Restored meeting "{meeting.title}" from trash', request=request)
    messages.success(request, f'Meeting "{meeting.title}" restored.')
    return redirect('meeting_list')


@login_required
@admin_required
def project_permanent_delete(request, project_id):  # Permanently delete project from trash
    project = get_object_or_404(Project.objects.filter(is_deleted=True), pk=project_id)
    name = project.name
    project.hard_delete()
    log_delete(request.user, project, detail=f'Permanently deleted project "{name}"', request=request)
    messages.success(request, f'Project "{name}" permanently deleted.')
    return redirect('trash_list')


@login_required
@admin_required
def task_permanent_delete(request, task_id):  # Permanently delete task from trash
    task = get_object_or_404(ProjectTask.objects.filter(is_deleted=True), pk=task_id)
    title = task.title
    task.hard_delete()
    log_delete(request.user, task, detail=f'Permanently deleted task "{title}"', request=request)
    messages.success(request, f'Task "{title}" permanently deleted.')
    return redirect('trash_list')


@login_required
@admin_required
def meeting_permanent_delete(request, meeting_id):  # Permanently delete meeting from trash
    meeting = get_object_or_404(Meeting.objects.filter(is_deleted=True), pk=meeting_id)
    title = meeting.title
    meeting.hard_delete()
    log_delete(request.user, meeting, detail=f'Permanently deleted meeting "{title}"', request=request)
    messages.success(request, f'Meeting "{title}" permanently deleted.')
    return redirect('trash_list')


@login_required
@admin_required
def empty_trash(request):  # Empty trash: delete all soft-deleted items permanently
    """Permanently delete all soft-deleted items (admin only)."""
    Project.objects.filter(is_deleted=True).delete()
    ProjectTask.objects.filter(is_deleted=True).delete()
    Meeting.objects.filter(is_deleted=True).delete()
    messages.success(request, 'Trash emptied permanently.')
    return redirect('trash_list')


@login_required
@manager_or_admin_required
@require_permission('can_manage_projects')
def project_archive(request, project_id):  # Archive a project (mark as archived)
    project = get_object_or_404(get_editable_projects(request.user), pk=project_id)
    project.archive()
    log_update(request.user, project, detail=f'Archived project "{project.name}"', request=request)
    messages.success(request, f'Project "{project.name}" archived.')
    return redirect('project_list')


@login_required
@manager_or_admin_required
@require_permission('can_manage_projects')
def project_unarchive(request, project_id):  # Restore project from archive
    project = get_object_or_404(Project, pk=project_id, is_archived=True)
    project.unarchive()
    log_update(request.user, project, detail=f'Unarchived project "{project.name}"', request=request)
    messages.success(request, f'Project "{project.name}" restored from archive.')
    return redirect('project_list')


@login_required
@manager_or_admin_required
@require_permission('can_manage_meetings')
def meeting_archive_toggle(request, meeting_id):  # Toggle meeting archive status
    meeting = get_object_or_404(Meeting, pk=meeting_id)
    if meeting.is_archived:
        meeting.unarchive()
        msg = 'unarchived'
    else:
        meeting.archive()
        msg = 'archived'
    log_update(request.user, meeting, detail=f'{msg.capitalize()} meeting "{meeting.title}"', request=request)
    messages.success(request, f'Meeting "{meeting.title}" {msg}.')
    return redirect('meeting_list')

from .analytics import (
    get_productivity_score, get_daily_hours, get_idle_time,
    get_focus_break_ratio, get_weekly_stats, get_team_performance,
    get_focus_break_team,
)


# --- Analytics JSON Endpoints ---

@login_required
def analytics_productivity(request):  # JSON: productivity score + daily hours
    days = int(request.GET.get('days', 30))
    user_id = request.GET.get('user_id')
    user = get_object_or_404(User, pk=user_id) if user_id else request.user
    if user != request.user and request.user.profile.role not in ('admin', 'manager'):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    return JsonResponse({
        'score': get_productivity_score(user, days),
        'daily_hours': get_daily_hours(user),
        'weekly': get_weekly_stats(user),
    })


@login_required
def analytics_idle_time(request):  # JSON: idle time periods between timers
    days = int(request.GET.get('days', 7))
    user_id = request.GET.get('user_id')
    user = get_object_or_404(User, pk=user_id) if user_id else request.user
    if user != request.user and request.user.profile.role not in ('admin', 'manager'):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    return JsonResponse(get_idle_time(user, days))


@login_required
def analytics_focus_break(request):  # JSON: focus vs break time ratio
    days = int(request.GET.get('days', 7))
    user_id = request.GET.get('user_id')
    user = get_object_or_404(User, pk=user_id) if user_id else request.user
    if user != request.user and request.user.profile.role not in ('admin', 'manager'):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    return JsonResponse(get_focus_break_ratio(user, days))


@login_required
@manager_or_admin_required
def analytics_team_performance(request):  # JSON: team performance comparison
    days = int(request.GET.get('days', 30))
    user_id = request.GET.get('user_id')
    target_user = get_object_or_404(User, pk=user_id) if user_id else request.user
    if target_user.profile.role not in ('admin', 'manager'):
        return JsonResponse({'error': 'User is not a manager/admin'}, status=400)
    return JsonResponse({
        'team': get_team_performance(target_user, days),
        'focus_break_chart': get_focus_break_team(target_user, days),
    })




# --- Notifications ---

from .notifications import run_all_checks


@login_required
def notifications_poll(request):  # JSON: return unread notifications, run rule checks
    """JSON endpoint — returns unread notifications + runs rule checks."""
    run_all_checks(request.user)

    Notification.objects.filter(
        user=request.user, is_dismissed=False, expires_at__isnull=False, expires_at__lte=timezone.now()
    ).update(is_dismissed=True)

    Notification.objects.filter(user=request.user, is_dismissed=True, created_at__lt=timezone.now() - timedelta(days=7)).delete()
    qs = Notification.objects.filter(user=request.user, is_dismissed=False).order_by('is_read', 'priority', '-created_at')[:20]
    data = []
    unread_count = 0
    for n in qs:
        item = {
            'id': n.id,
            'message': n.message,
            'type': n.type,
            'priority': n.priority,
            'category': n.category,
            'is_read': n.is_read,
            'icon': n.icon_class,
            'color': n.color_class,
            'bg': n.bg_class,
            'url': n.related_url,
            'created_at': n.created_at.isoformat(),
        }
        data.append(item)
        if not n.is_read:
            unread_count += 1
    return JsonResponse({'notifications': data, 'unread_count': unread_count})


@login_required
def notifications_mark_read(request, notification_id=None):  # Mark one or all notifications as read
    if notification_id:
        Notification.objects.filter(pk=notification_id, user=request.user).update(is_read=True)
    else:
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    messages.success(request, 'Notifications marked as read.')
    return redirect(request.META.get('HTTP_REFERER', 'employee_dashboard'))


@login_required
def notifications_dismiss(request, notification_id):  # Dismiss a notification permanently
    Notification.objects.filter(pk=notification_id, user=request.user).update(is_dismissed=True)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect(request.META.get('HTTP_REFERER', 'employee_dashboard'))




# --- Audit Log ---

@login_required
@manager_or_admin_required
def audit_history(request):  # View audit log with filter/search/pagination
    qs = AuditLog.objects.select_related('actor', 'target_type').all()

    action = request.GET.get('action', '')
    user_id = request.GET.get('user_id', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    target_model = request.GET.get('target_model', '')
    if action:
        qs = qs.filter(action=action)
    if user_id:
        qs = qs.filter(actor_id=user_id)
    if date_from:
        qs = qs.filter(created_at__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__lte=date_to + 'T23:59:59')
    if target_model:
        qs = qs.filter(target_type__model=target_model)
    page = int(request.GET.get('page', 1))
    per_page = 50
    total = qs.count()
    logs = qs[(page - 1) * per_page:page * per_page]
    users = User.objects.filter(is_active=True, profile__role__in=['admin', 'manager'])
    return render(request, 'attendance/audit_history.html', {
        'logs': logs,
        'users': users,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'action_choices': AuditLog.ACTION_CHOICES,
        'model_choices': [
            ('project', 'Project'), ('projecttask', 'Task'),
            ('meeting', 'Meeting'), ('attendance', 'Attendance'),
            ('timeentry', 'Time Entry'), ('user', 'User'),
        ],
        'filters': {'action': action, 'user_id': user_id, 'date_from': date_from, 'date_to': date_to, 'target_model': target_model},
    })





# --- Leave Requests ---

@login_required
def leave_list(request):  # Employee: view own leave requests
    """Employee: view own leave requests."""
    leaves = LeaveRequest.objects.filter(employee=request.user)
    return render(request, 'attendance/leave_list.html', {'leaves': leaves})


@login_required
def leave_create(request):  # Employee: submit new leave request
    """Employee: create a new leave request."""
    leave_types = LeaveRequest.get_leave_types_for_gender(request.user.profile.gender)
    if request.method == 'POST':
        leave_type = request.POST.get('leave_type', '')
        start_date_str = request.POST.get('start_date', '')
        end_date_str = request.POST.get('end_date', '')
        reason = request.POST.get('reason', '')
        attachment = request.FILES.get('attachment')

        if leave_type not in dict(leave_types):
            messages.error(request, 'Please select a valid leave type.')
            return render(request, 'attendance/leave_form.html', {'leave_types': leave_types})

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            messages.error(request, 'Please enter valid dates.')
            return render(request, 'attendance/leave_form.html', {'leave_types': leave_types})

        if end_date < start_date:
            messages.error(request, 'End date cannot be before start date.')
            return render(request, 'attendance/leave_form.html', {'leave_types': leave_types})

        total_days = (end_date - start_date).days + 1

        leave = LeaveRequest.objects.create(
            employee=request.user,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            total_days=total_days,
            reason=reason,
            attachment=attachment,
        )

        manager_profile = request.user.profile.manager
        if manager_profile:
            Notification.objects.create(
                user=manager_profile.user,
                type='leave_requested',
                category='leave',
                message=f'{request.user.get_full_name() or request.user.username} requested {leave.get_leave_type_display()} ({start_date} to {end_date})',
                priority='medium',
                related_url=f'/leaves/manage/',
            )
        messages.success(request, 'Leave request submitted. Waiting for approval.')
        return redirect('leave_list')

    return render(request, 'attendance/leave_form.html', {'leave_types': leave_types})


@login_required
def leave_cancel(request, leave_id):  # Employee: cancel own pending leave
    """Employee: cancel own pending leave request."""
    leave = get_object_or_404(LeaveRequest, pk=leave_id, employee=request.user)
    if leave.status != 'pending':
        messages.error(request, 'Only pending requests can be cancelled.')
        return redirect('leave_list')
    leave.status = 'cancelled'
    leave.save()
    messages.success(request, 'Leave request cancelled.')
    return redirect('leave_list')


@login_required
@manager_or_admin_required
def leave_manage(request):  # Manager/Admin: view team leave requests
    """Manager/Admin: view leave requests for their team."""
    if request.user.profile.role == 'admin':
        leaves = LeaveRequest.objects.all().select_related('employee', 'reviewed_by')
    else:
        team = request.user.profile.team_members.values_list('user_id', flat=True)
        leaves = LeaveRequest.objects.filter(employee_id__in=list(team) + [request.user.id]).select_related('employee', 'reviewed_by')
    return render(request, 'attendance/leave_manage.html', {'leaves': leaves})


@login_required
@manager_or_admin_required
def leave_detail(request, leave_id):  # Manager/Admin: view leave request detail
    """Manager/Admin: view leave request detail."""
    leave = get_object_or_404(LeaveRequest.objects.select_related('employee', 'reviewed_by'), pk=leave_id)
    if request.user.profile.role != 'admin':
        team = list(request.user.profile.team_members.values_list('user_id', flat=True)) + [request.user.id]
        if leave.employee_id not in team:
            messages.error(request, 'You cannot view this leave request.')
            return redirect('leave_manage')
    return render(request, 'attendance/leave_detail.html', {'leave': leave})


@login_required
@manager_or_admin_required
def leave_approve(request, leave_id):  # Approve a pending leave request
    leaves = LeaveRequest.objects.filter(pk=leave_id, status='pending')
    if request.method == 'POST':
        leave = get_object_or_404(leaves)
        if request.user.profile.role != 'admin':
            team = list(request.user.profile.team_members.values_list('user_id', flat=True)) + [request.user.id]
            if leave.employee_id not in team:
                messages.error(request, 'You cannot approve this request.')
                return redirect('leave_manage')
        leave.status = 'approved'
        leave.reviewed_by = request.user
        leave.reviewed_at = timezone.now()
        leave.manager_note = request.POST.get('manager_note', '')
        leave.save()
        Notification.objects.create(
            user=leave.employee,
            type='leave_approved',
            category='leave',
            message=f'Your {leave.get_leave_type_display()} request ({leave.start_date} to {leave.end_date}) has been approved.',
            priority='low',
            related_url='/leaves/',
        )
        messages.success(request, f'{leave.employee.get_full_name() or leave.employee.username}\'s leave approved.')
        return redirect('leave_manage')
    return redirect('leave_manage')


@login_required
@manager_or_admin_required
def leave_reject(request, leave_id):  # Reject a pending leave request
    leaves = LeaveRequest.objects.filter(pk=leave_id, status='pending')
    if request.method == 'POST':
        leave = get_object_or_404(leaves)
        if request.user.profile.role != 'admin':
            team = list(request.user.profile.team_members.values_list('user_id', flat=True)) + [request.user.id]
            if leave.employee_id not in team:
                messages.error(request, 'You cannot reject this request.')
                return redirect('leave_manage')
        leave.status = 'rejected'
        leave.reviewed_by = request.user
        leave.reviewed_at = timezone.now()
        leave.manager_note = request.POST.get('manager_note', '')
        leave.save()
        Notification.objects.create(
            user=leave.employee,
            type='leave_rejected',
            category='leave',
            message='Your {} request ({} to {}) has been rejected.{}'.format(
                leave.get_leave_type_display(), leave.start_date, leave.end_date,
                ' Reason: ' + leave.manager_note if leave.manager_note else ''
            ),
            priority='medium',
            related_url='/leaves/',
        )
        messages.success(request, f'{leave.employee.get_full_name() or leave.employee.username}\'s leave rejected.')
        return redirect('leave_manage')
    return redirect('leave_manage')



# --- Reports ---

@login_required
@manager_or_admin_required
@require_permission('can_view_reports')
def reports(request):
    today = timezone.now().date()
    report_view = request.GET.get('view', 'attendance')
    report_type = request.GET.get('type', 'weekly')
    date_str = request.GET.get('date', today.isoformat())
    try:
        ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        ref_date = today

    if report_type == 'daily':
        start_date = end_date = ref_date
    elif report_type == 'monthly':
        start_date = ref_date.replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
    else:
        start_date = ref_date - timedelta(days=ref_date.weekday())
        end_date = start_date + timedelta(days=6)

    attendances = get_visible_attendances(request.user).filter(
        date__gte=start_date, date__lte=end_date
    ).select_related('user')

    summary = {}
    project_data = []
    user_data = []

    if report_view == 'attendance':
        total_records = attendances.count()
        total_hours_sum = attendances.aggregate(s=Sum('total_hours'))['s'] or 0
        total_overtime = attendances.aggregate(s=Sum('overtime_minutes'))['s'] or 0
        total_late = attendances.filter(is_late=True).count()
        summary = {
            'total_records': total_records,
            'total_hours_sum': round(total_hours_sum, 1),
            'total_overtime': total_overtime,
            'total_late': total_late,
        }

    elif report_view == 'projects':
        projects = get_visible_projects(request.user)
        for p in projects:
            mins = TimeEntry.objects.filter(
                task__project=p, start_time__date__gte=start_date, start_time__date__lte=end_date
            ).aggregate(s=Sum('duration_minutes'))['s'] or 0
            if mins > 0:
                project_data.append({'project': p, 'hours': mins // 60, 'minutes': mins})
        project_data.sort(key=lambda x: x['minutes'], reverse=True)
        summary = {'total_hours': sum(pd['hours'] for pd in project_data), 'project_count': len(project_data)}

    elif report_view == 'users':
        users = get_visible_users(request.user)
        for u in users:
            mins = TimeEntry.objects.filter(
                user=u, start_time__date__gte=start_date, start_time__date__lte=end_date
            ).aggregate(s=Sum('duration_minutes'))['s'] or 0
            if mins > 0:
                user_data.append({'user': u, 'hours': mins // 60, 'minutes': mins})
        user_data.sort(key=lambda x: x['minutes'], reverse=True)
        summary = {'total_hours': sum(ud['hours'] for ud in user_data)}

    context = {
        'attendances': attendances,
        'project_data': project_data,
        'user_data': user_data,
        'summary': summary,
        'report_view': report_view,
        'report_type': report_type,
        'start_date': start_date,
        'end_date': end_date,
        'today': today,
    }
    return render(request, 'attendance/reports.html', context)


@login_required
@manager_or_admin_required
@require_permission('can_export_data')
def export_csv(request):
    today = timezone.now().date()
    report_view = request.GET.get('view', 'attendance')
    report_type = request.GET.get('type', 'weekly')
    date_str = request.GET.get('date', today.isoformat())
    try:
        ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        ref_date = today

    if report_type == 'daily':
        start_date = end_date = ref_date
    elif report_type == 'monthly':
        start_date = ref_date.replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
    else:
        start_date = ref_date - timedelta(days=ref_date.weekday())
        end_date = start_date + timedelta(days=6)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="report_{start_date}_{end_date}.csv"'
    writer = csv.writer(response)

    if report_view == 'projects':
        writer.writerow(['Project', 'Status', 'Hours', 'Minutes'])
        projects = get_visible_projects(request.user)
        for p in projects:
            mins = TimeEntry.objects.filter(
                task__project=p, start_time__date__gte=start_date, start_time__date__lte=end_date
            ).aggregate(s=Sum('duration_minutes'))['s'] or 0
            if mins > 0:
                writer.writerow([p.name, p.get_status_display(), mins // 60, mins % 60])

    elif report_view == 'users':
        writer.writerow(['User', 'Hours', 'Minutes'])
        users = get_visible_users(request.user)
        for u in users:
            mins = TimeEntry.objects.filter(
                user=u, start_time__date__gte=start_date, start_time__date__lte=end_date
            ).aggregate(s=Sum('duration_minutes'))['s'] or 0
            if mins > 0:
                writer.writerow([u.get_full_name() or u.username, mins // 60, mins % 60])

    else:
        writer.writerow(['Employee', 'Date', 'Check In', 'Check Out', 'Hours', 'Late', 'Overtime'])
        attendances = get_visible_attendances(request.user).filter(
            date__gte=start_date, date__lte=end_date
        ).select_related('user')
        for a in attendances:
            writer.writerow([
                a.user.get_full_name() or a.user.username,
                a.date,
                a.check_in.strftime('%H:%M') if a.check_in else '--',
                a.check_out.strftime('%H:%M') if a.check_out else '--',
                a.total_hours,
                'Yes' if a.is_late else 'No',
                a.overtime_minutes,
            ])

    return response


@login_required
@manager_or_admin_required
@require_permission('can_export_data')
def export_pdf(request):
    today = timezone.now().date()
    report_type = request.GET.get('type', 'weekly')
    date_str = request.GET.get('date', today.isoformat())
    try:
        ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        ref_date = today

    if report_type == 'daily':
        start_date = end_date = ref_date
    elif report_type == 'monthly':
        start_date = ref_date.replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
    else:
        start_date = ref_date - timedelta(days=ref_date.weekday())
        end_date = start_date + timedelta(days=6)

    attendances = get_visible_attendances(request.user).filter(
        date__gte=start_date, date__lte=end_date
    ).select_related('user')

    total_records = attendances.count()
    total_hours_sum = attendances.aggregate(s=Sum('total_hours'))['s'] or 0
    total_overtime = attendances.aggregate(s=Sum('overtime_minutes'))['s'] or 0
    total_late = attendances.filter(is_late=True).count()

    html = render_to_string('attendance/pdf_report.html', {
        'attendances': attendances,
        'summary': {
            'total_records': total_records,
            'total_hours_sum': round(total_hours_sum, 1),
            'total_overtime': total_overtime,
            'total_late': total_late,
        },
        'report_type': report_type,
        'start_date': start_date,
        'end_date': end_date,
        'today': today,
    })
    return HttpResponse(html)



# --- Notifications: Mark All Read ---

@login_required
def mark_notifications_read(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        messages.success(request, 'Notifications marked as read.')
        return redirect(request.META.get('HTTP_REFERER', 'employee_dashboard'))
    return redirect('employee_dashboard')



# --- Global Search ---

@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    results = {'users': [], 'projects': [], 'tasks': [], 'clients': []}
    if q:
        results['users'] = get_visible_users(request.user).filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )[:10]
        results['projects'] = get_visible_projects(request.user).filter(name__icontains=q)[:10]
        results['tasks'] = ProjectTask.objects.filter(
            Q(title__icontains=q) | Q(description__icontains=q), is_deleted=False
        ).select_related('project')[:10]
        results['clients'] = Client.objects.filter(name__icontains=q)[:10]
    return render(request, 'attendance/search_results.html', {'results': results, 'q': q})



# --- Project Edit / Delete / Detail ---

@login_required
@manager_or_admin_required
@require_permission('can_manage_projects')
def project_edit(request, project_id):
    project = get_object_or_404(get_editable_projects(request.user), pk=project_id)
    clients = Client.objects.filter(is_active=True)
    if request.method == 'POST':
        project.name = request.POST['name']
        project.description = request.POST.get('description', '')
        project.client_id = request.POST.get('client') or None
        project.status = request.POST.get('status', 'active')
        project.save()
        log_update(request.user, project, request=request)
        messages.success(request, f'Project "{project.name}" updated.')
        return redirect('project_detail', project_id=project.id)
    return render(request, 'attendance/project_form.html', {'project': project, 'clients': clients})


@login_required
@manager_or_admin_required
@require_permission('can_manage_projects')
def project_delete(request, project_id):
    project = get_object_or_404(get_editable_projects(request.user), pk=project_id)
    if request.method == 'POST':
        name = project.name
        project.soft_delete(request.user)
        log_delete(request.user, project, request=request)
        messages.success(request, f'Project "{name}" moved to trash.')
        return redirect('project_list')
    return redirect('project_detail', project_id=project.id)


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(
        get_visible_projects(request.user).select_related('client'), pk=project_id
    )
    tasks = ProjectTask.objects.filter(project=project, is_deleted=False).select_related('assigned_to')
    active_timer = _get_active_timer(request.user)
    total_mins = TimeEntry.objects.filter(task__project=project).aggregate(s=Sum('duration_minutes'))['s'] or 0
    total_hours = total_mins // 60
    total_minutes = total_mins % 60
    return render(request, 'attendance/project_detail.html', {
        'project': project,
        'tasks': tasks,
        'status_choices': ProjectTask.STATUS_CHOICES,
        'active_timer': active_timer,
        'total_hours': total_hours,
        'total_minutes': total_minutes,
    })



# --- Task CRUD ---

@login_required
@manager_or_admin_required
@require_permission('can_manage_tasks')
def task_add(request, project_id):
    project = get_object_or_404(get_visible_projects(request.user), pk=project_id)
    employees = get_visible_users(request.user)
    if request.method == 'POST':
        task = ProjectTask.objects.create(
            project=project,
            title=request.POST['title'],
            description=request.POST.get('description', ''),
            priority=request.POST.get('priority', 'medium'),
            status=request.POST.get('status', 'todo'),
            estimated_hours=float(request.POST.get('estimated_hours', 0) or 0),
            deadline=request.POST.get('deadline') or None,
            assigned_to_id=request.POST.get('assigned_to') or None,
            created_by=request.user,
        )
        log_create(request.user, task, request=request)
        messages.success(request, f'Task "{task.title}" created.')
        return redirect('project_detail', project_id=project.id)
    return render(request, 'attendance/task_form.html', {
        'task': None, 'project': project, 'employees': employees,
    })


@login_required
@manager_or_admin_required
@require_permission('can_manage_tasks')
def task_edit(request, task_id):
    task = get_object_or_404(get_editable_tasks(request.user), pk=task_id)
    project = task.project
    employees = get_visible_users(request.user)
    if request.method == 'POST':
        task.title = request.POST['title']
        task.description = request.POST.get('description', '')
        task.priority = request.POST.get('priority', 'medium')
        task.status = request.POST.get('status', 'todo')
        task.estimated_hours = float(request.POST.get('estimated_hours', 0) or 0)
        deadline = request.POST.get('deadline')
        task.deadline = datetime.strptime(deadline, '%Y-%m-%d').date() if deadline else None
        task.assigned_to_id = request.POST.get('assigned_to') or None
        task.save()
        log_update(request.user, task, request=request)
        messages.success(request, f'Task "{task.title}" updated.')
        return redirect('project_detail', project_id=task.project_id)
    return render(request, 'attendance/task_form.html', {
        'task': task, 'project': project, 'employees': employees,
    })


@login_required
@manager_or_admin_required
@require_permission('can_manage_tasks')
def task_delete(request, task_id):
    task = get_object_or_404(get_editable_tasks(request.user), pk=task_id)
    if request.method == 'POST':
        title = task.title
        task.soft_delete(request.user)
        log_delete(request.user, task, request=request)
        messages.success(request, f'Task "{title}" moved to trash.')
        return redirect('project_detail', project_id=task.project_id)
    return redirect('project_detail', project_id=task.project_id)


@login_required
def task_update_status(request, task_id):
    task = get_object_or_404(ProjectTask, pk=task_id, is_deleted=False)
    if request.method == 'POST':
        new_status = request.POST.get('status', '')
    else:
        new_status = request.GET.get('status', '')
    if new_status and new_status in dict(ProjectTask.STATUS_CHOICES):
        try:
            task.set_status(new_status, user=request.user)
            audit_log(request.user, 'status_change',
                      f'Changed task "{task.title}" status to {task.get_status_display()}',
                      target=task, request=request)
            messages.success(request, f'Task status updated to {task.get_status_display()}.')
        except ValueError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, 'Invalid status.')
    return redirect(request.META.get('HTTP_REFERER', 'project_detail'))


@login_required
def task_update_status_ajax(request, task_id):
    if request.method == 'POST':
        task = get_object_or_404(ProjectTask, pk=task_id, is_deleted=False)
        new_status = request.POST.get('new_status', '') or request.POST.get('status', '')
        if new_status and new_status in dict(ProjectTask.STATUS_CHOICES):
            try:
                task.set_status(new_status, user=request.user)
                return JsonResponse({'status': 'ok', 'new_status': new_status})
            except ValueError as e:
                return JsonResponse({'status': 'error', 'message': str(e)})
        return JsonResponse({'status': 'error', 'message': 'Invalid status.'})
    return JsonResponse({'status': 'error', 'message': 'POST required.'})


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(
        ProjectTask.objects.select_related('project', 'assigned_to', 'created_by', 'completed_by'),
        pk=task_id, is_deleted=False,
    )
    can_claim = task.assigned_to is None and request.user.has_perm('attendance.can_claim_tasks')
    active_timer = _get_active_timer(request.user)
    time_entries = TimeEntry.objects.filter(task=task).select_related('user').order_by('-start_time')[:20]
    return render(request, 'attendance/task_detail.html', {
        'task': task,
        'status_choices': ProjectTask.STATUS_CHOICES,
        'active_timer': active_timer,
        'can_claim': can_claim,
        'time_entries': time_entries,
        'user': request.user,
    })


@login_required
def claim_task(request, task_id):
    task = get_object_or_404(
        ProjectTask, pk=task_id, is_deleted=False, assigned_to__isnull=True
    )
    task.assigned_to = request.user
    task.save()
    log_update(request.user, task, detail=f'Claimed task "{task.title}"', request=request)
    messages.success(request, f'You claimed task "{task.title}".')
    return redirect('task_detail', task_id=task.id)


@login_required
def task_complete(request, task_id):
    task = get_object_or_404(
        ProjectTask.objects.select_related('project'), pk=task_id, is_deleted=False
    )
    if task.assigned_to != request.user and request.user.profile.role not in ('admin', 'manager'):
        messages.error(request, 'You cannot complete this task.')
        return redirect('task_detail', task_id=task.id)
    if request.method == 'POST':
        note = request.POST.get('completion_note', '')
        try:
            task.complete(request.user, note)
            log_update(request.user, task, detail=f'Completed task "{task.title}"', request=request)
            messages.success(request, f'Task "{task.title}" completed.')
            return redirect('task_detail', task_id=task.id)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('task_complete', task_id=task.id)
    return render(request, 'attendance/task_complete.html', {'task': task})



# --- Task Board ---

@login_required
def task_board(request):
    project_filter = request.GET.get('project', '')
    assigned_filter = request.GET.get('assigned', '')
    tasks = get_visible_tasks(request.user).select_related(
        'project', 'assigned_to', 'completed_by'
    )
    if project_filter:
        tasks = tasks.filter(project_id=project_filter)
    if assigned_filter == 'mine':
        tasks = tasks.filter(assigned_to=request.user)
    elif assigned_filter == 'unassigned':
        tasks = tasks.filter(assigned_to__isnull=True)
    elif assigned_filter:
        tasks = tasks.filter(assigned_to_id=assigned_filter)
    columns = []
    for key, label in ProjectTask.STATUS_CHOICES:
        columns.append({'key': key, 'label': label, 'tasks': [t for t in tasks if t.status == key]})
    projects = get_visible_projects(request.user)
    users = get_visible_users(request.user)
    return render(request, 'attendance/task_board.html', {
        'columns': columns,
        'projects': projects,
        'users': users,
        'selected_project': project_filter,
        'selected_assigned': assigned_filter,
    })



# --- My Tasks / Open Tasks ---

@login_required
def my_tasks(request):
    assigned_tasks = ProjectTask.objects.filter(
        assigned_to=request.user, is_deleted=False
    ).select_related('project')
    open_tasks_qs = ProjectTask.objects.filter(
        assigned_to__isnull=True, status='todo', is_deleted=False
    ).select_related('project')[:5]
    active_timer = _get_active_timer(request.user)
    return render(request, 'attendance/my_tasks.html', {
        'assigned_tasks': assigned_tasks,
        'open_tasks': open_tasks_qs,
        'active_timer': active_timer,
    })


@login_required
def open_tasks(request):
    tasks = ProjectTask.objects.filter(
        assigned_to__isnull=True, status='todo', is_deleted=False
    ).select_related('project')
    return render(request, 'attendance/open_tasks.html', {'tasks': tasks})



# --- Timesheet ---

@login_required
def timesheet(request):
    today = timezone.now().date()
    view_type = request.GET.get('view', 'weekly')
    date_str = request.GET.get('date', today.isoformat())
    try:
        ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        ref_date = today

    if view_type == 'daily':
        start_date = end_date = ref_date
        prev_date = ref_date - timedelta(days=1)
        next_date = ref_date + timedelta(days=1)
    elif view_type == 'monthly':
        start_date = ref_date.replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)
        prev_date = (start_date - timedelta(days=1)).replace(day=1)
        next_date = (end_date + timedelta(days=1)).replace(day=1)
    else:
        start_date = ref_date - timedelta(days=ref_date.weekday())
        end_date = start_date + timedelta(days=6)
        prev_date = start_date - timedelta(days=7)
        next_date = start_date + timedelta(days=7)

    entries = TimeEntry.objects.filter(
        user=request.user,
        start_time__date__gte=start_date,
        start_time__date__lte=end_date,
    ).select_related('task__project', 'task').order_by('-start_time')

    total_mins = entries.aggregate(s=Sum('duration_minutes'))['s'] or 0
    total_hours = round(total_mins / 60, 1)

    date_grid = None
    if view_type == 'weekly':
        date_grid = []
        for i in range(7):
            d = start_date + timedelta(days=i)
            day_mins = entries.filter(start_time__date=d).aggregate(s=Sum('duration_minutes'))['s'] or 0
            date_grid.append({'date': d, 'label': d.strftime('%a %d'), 'total': day_mins})

    project_totals = {}
    for e in entries:
        pname = e.task.project.name
        project_totals[pname] = project_totals.get(pname, 0) + (e.duration_minutes or 0)
    total_minutes = sum(project_totals.values()) or 1

    return render(request, 'attendance/timesheet.html', {
        'view_type': view_type,
        'start_date': start_date,
        'end_date': end_date,
        'prev_date': prev_date,
        'next_date': next_date,
        'today': today,
        'total_hours': total_hours,
        'entries': entries,
        'date_grid': date_grid,
        'project_totals': project_totals,
        'total_minutes': total_minutes,
    })
