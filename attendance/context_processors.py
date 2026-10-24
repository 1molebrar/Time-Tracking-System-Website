from .models import Notification, TimeEntry, ProjectTask, Holiday
from django.db.models import Q
from django.utils import timezone


# --- Template context processors ---

def notifications(request):  # Provide unread notifications for the current user
    if request.user.is_authenticated:
        unread = Notification.objects.filter(user=request.user, is_read=False)
        return {
            'unread_notifications': unread[:10],
            'unread_count': unread.count(),
        }
    return {'unread_notifications': [], 'unread_count': 0}


def active_timer(request):  # Provide the currently running timer for the user
    if request.user.is_authenticated:
        timer = TimeEntry.objects.filter(
            user=request.user, is_running=True
        ).select_related('task__project').first()
        return {'active_timer': timer}
    return {'active_timer': None}


def global_search_form(request):  # Persist the current search query across page loads
    return {'search_query': request.GET.get('q', '')}


def open_tasks_count(request):  # Count unassigned tasks for the badge in the nav
    if request.user.is_authenticated:
        count = ProjectTask.objects.filter(assigned_to__isnull=True, status='todo').count()
        return {'open_tasks_count': count}
    return {'open_tasks_count': 0}


def today_holiday(request):  # Check if today is a holiday
    if request.user.is_authenticated:
        holiday = Holiday.get_holiday(timezone.now().date())
        return {'today_holiday_global': holiday}
    return {'today_holiday_global': None}
