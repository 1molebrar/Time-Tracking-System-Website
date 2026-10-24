from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models import Q, Count
from .models import Notification, Attendance, Break, ProjectTask, Meeting, LeaveRequest
from django.contrib.auth.models import User


# --- Internal helpers ---

def _create(user, type, message, priority='medium', category='system', related_url='', expires_minutes=None):
    # Create or reuse an unread notification for the user
    expires_at = timezone.now() + timedelta(minutes=expires_minutes) if expires_minutes else None
    Notification.objects.get_or_create(
        user=user, type=type,
        is_read=False, is_dismissed=False,
        defaults={
            'message': message,
            'priority': priority,
            'category': category,
            'related_url': related_url,
            'expires_at': expires_at,
        }
    )


# --- Attendance event notifications ---

def notify_clock_in(user):
    hour = timezone.now().hour
    if hour < 12:
        greeting = 'morning'
    elif hour < 18:
        greeting = 'afternoon'
    else:
        greeting = 'evening'
    _create(user, 'clock_in', f'Good {greeting}! Your shift has started. Have a productive day!',
            priority='low', category='attendance')


def notify_break_start(user, attendance):
    _create(user, 'break_start', 'Enjoy your break! Don\'t stay away too long.',
            priority='low', category='attendance')


# --- Rule-based checks ---

def check_extended_break(user, attendance):
    """Urgent: break > 60 min => warning"""
    if not attendance:
        return
    active_break = Break.objects.filter(attendance=attendance, break_end__isnull=True).first()
    if not active_break:
        return
    elapsed = (timezone.now() - active_break.break_start).total_seconds()
    if elapsed >= 3600:
        _create(user, 'extended_break',
                'You\'ve been on break for over an hour! Please return to work.',
                priority='urgent', category='attendance',
                expires_minutes=30)


def check_missing_clock_out(user):
    """High: after 18:00 without clock-out (skip for users on approved leave)"""
    now = timezone.now()
    if now.hour < 18:
        return
    today = now.date()
    if LeaveRequest.is_on_leave(user, today):
        return
    if Attendance.objects.filter(user=user, date=today, check_out__isnull=True).exists():
        _create(user, 'clock_out_reminder',
                'The workday is ending. Don\'t forget to clock out!',
                priority='high', category='attendance',
                expires_minutes=60)


def check_mid_shift_reminder(user, attendance):
    """Medium: 4+ hours without clock-out => break reminder"""
    if not attendance or not attendance.check_in or attendance.check_out:
        return
    elapsed = (timezone.now() - attendance.check_in).total_seconds()
    if elapsed >= 4 * 3600:
        _create(user, 'break_reminder',
                'You\'ve been working for a while. Time for a short break!',
                priority='medium', category='attendance',
                expires_minutes=60)


def check_deadline_risks(user):
    """High/urgent: tasks due within 24h / 3 days"""
    today = timezone.now().date()

    urgent = ProjectTask.objects.filter(
        assigned_to=user, status__in=('todo', 'in_progress', 'in_review'),
        deadline__lte=today
    ).count()
    if urgent:
        _create(user, 'deadline_risk',
                f'{urgent} task(s) are overdue or due today!',
                priority='urgent', category='task',
                related_url='/tasks/?filter=urgent',
                expires_minutes=120)

    soon = ProjectTask.objects.filter(
        assigned_to=user, status__in=('todo', 'in_progress'),
        deadline__gt=today, deadline__lte=today + timedelta(days=3)
    ).count()
    if soon:
        _create(user, 'deadline_risk',
                f'{soon} task(s) deadline approaching within 3 days.',
                priority='high', category='task',
                related_url='/my-tasks/',
                expires_minutes=120)


def check_missed_meetings(user):
    """High: meetings that ended without the user attending"""
    today = timezone.now().date()
    now = timezone.now()
    missed = Meeting.objects.filter(
        participants=user, date=today,
        status__in=('scheduled', 'ongoing'),
        end_time__lt=now.time()
    ).exclude(attendees=user).count()
    if missed:
        _create(user, 'missed_meeting',
                f'You missed {missed} meeting(s) today!',
                priority='high', category='meeting',
                related_url='/meetings/',
                expires_minutes=180)


def check_no_clock_in(user):
    """Medium: reminders at 10:00 and 11:00 if no clock-in (skip for users on approved leave)"""
    now = timezone.now()
    today = now.date()
    if now.hour not in (10, 11) or now.minute > 30:
        return
    if Attendance.objects.filter(user=user, date=today).exists():
        return
    if LeaveRequest.is_on_leave(user, today):
        return
    hour_word = 'morning' if now.hour == 10 else 'late'
    _create(user, 'clock_in', f'Good {hour_word}! You haven\'t clocked in yet. Start your shift!',
            priority='medium', category='attendance',
            expires_minutes=60)


# --- Summary ---

def generate_daily_summary(user):
    """Low priority: end-of-day summary"""
    today = timezone.now().date()
    attendance = Attendance.objects.filter(user=user, date=today).first()
    if not attendance or not attendance.check_in:
        return
    hours = attendance.total_hours or 0
    breaks = attendance.breaks.filter(break_end__isnull=False).count()
    tasks_done = ProjectTask.objects.filter(
        assigned_to=user, completed_at__date=today, status='done'
    ).count()
    msg = f'Daily summary: {hours}h worked, {breaks} break(s), {tasks_done} task(s) completed.'
    _create(user, 'daily_summary', msg,
            priority='low', category='system',
            expires_minutes=120)


# --- Orchestrator ---

def run_all_checks(user):
    """Run every rule-based check for a given user."""
    now = timezone.now()
    today = now.date()
    attendance = Attendance.objects.filter(user=user, date=today).first()
    check_extended_break(user, attendance)
    check_mid_shift_reminder(user, attendance)
    check_missing_clock_out(user)
    check_deadline_risks(user)
    check_missed_meetings(user)
    check_no_clock_in(user)
