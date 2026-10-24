from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import Attendance, TimeEntry, Break, ProjectTask


def get_productivity_score(user, days=30):  # Score = tasks done per hour worked (capped 100)
    """Productivity = (completed_tasks / total_hours_worked) * 10, capped at 100."""
    since = timezone.now().date() - timedelta(days=days)
    worked = Attendance.objects.filter(
        user=user, date__gte=since, check_in__isnull=False
    ).aggregate(total=Sum('total_hours'))['total'] or 0
    completed = ProjectTask.objects.filter(
        assigned_to=user, completed_at__date__gte=since, status='done'
    ).count()
    if not worked:
        return 0
    return min(round((completed / worked) * 10, 1), 100)


def get_daily_hours(user, days=7):  # Chart data: hours per day for last N days
    """Daily gross hours (check_in to check_out) for the last N days."""
    now = timezone.now()
    since = now.date() - timedelta(days=days - 1)
    qs = Attendance.objects.filter(user=user, date__gte=since).order_by('date')
    labels = []
    values = []
    data_map = {}
    for a in qs:
        if a.check_in:
            end = a.check_out or now
            gross_hours = round((end - a.check_in).total_seconds() / 3600, 2)
            data_map[a.date.isoformat()] = gross_hours
    for i in range(days):
        d = (now.date() - timedelta(days=days - 1 - i)).isoformat()
        labels.append(d[-5:])
        values.append(data_map.get(d, 0))
    return {'labels': labels, 'values': values}


def get_idle_time(user, days=7):  # Find gaps >5 min between timer entries
    """Gaps > 5 min between TimeEntry end→next start."""
    since = timezone.now() - timedelta(days=days)
    entries = TimeEntry.objects.filter(
        user=user, start_time__gte=since
    ).order_by('start_time')
    idle_periods = []
    prev_end = None
    for entry in entries:
        if entry.end_time:
            if prev_end and entry.start_time > prev_end:
                gap = int((entry.start_time - prev_end).total_seconds() / 60)
                if gap > 5:
                    idle_periods.append({'start': prev_end, 'end': entry.start_time, 'minutes': gap})
            prev_end = entry.end_time
    total = sum(p['minutes'] for p in idle_periods)
    return {'periods': idle_periods, 'total_idle_minutes': total, 'total_idle_hours': round(total / 60, 1)}


def get_focus_break_ratio(user, days=7):  # Compare focused work time vs break time
    """Focus hours vs break hours ratio."""
    since = timezone.now().date() - timedelta(days=days)
    work = Attendance.objects.filter(user=user, date__gte=since).aggregate(
        total_hours=Sum('total_hours')
    )['total_hours'] or 0
    break_minutes = Break.objects.filter(
        attendance__user=user, attendance__date__gte=since, break_end__isnull=False
    ).aggregate(total=Sum('duration_minutes'))['total'] or 0
    break_hrs = round(break_minutes / 60, 1)
    focus_hrs = max(0, round(work - break_hrs, 1))
    ratio = round(focus_hrs / break_hrs, 1) if break_hrs else focus_hrs
    return {'focus_hours': focus_hrs, 'break_hours': break_hrs, 'ratio': ratio, 'work_hours': work}


def get_weekly_stats(user):  # Aggregated stats for current week
    """Current week aggregated stats."""
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())
    qs = Attendance.objects.filter(user=user, date__gte=week_start)
    aggregated = qs.aggregate(
        total_hours=Sum('total_hours'),
        days_worked=Count('id', filter=Q(check_in__isnull=False)),
    )
    return {
        'week_hours': round(aggregated['total_hours'] or 0, 1),
        'days_worked': aggregated['days_worked'] or 0,
        'avg_daily': round((aggregated['total_hours'] or 0) / max(aggregated['days_worked'] or 1, 1), 1),
    }


def get_team_performance(manager, days=30):  # Compare productivity/hours across team
    """Performance comparison across all team members."""
    since = timezone.now().date() - timedelta(days=days)
    team = manager.profile.team_members.select_related('user')
    data = []
    for profile in team:
        u = profile.user
        if not u.is_active:
            continue
        work = Attendance.objects.filter(user=u, date__gte=since).aggregate(
            total_hours=Sum('total_hours'), overtime=Sum('overtime_minutes'), days=Count('id')
        )
        tasks = ProjectTask.objects.filter(assigned_to=u)
        completed = tasks.filter(status='done', completed_at__date__gte=since).count()
        total_task_count = tasks.count()
        break_m = Break.objects.filter(
            attendance__user=u, attendance__date__gte=since, break_end__isnull=False
        ).aggregate(total=Sum('duration_minutes'))['total'] or 0
        hours = work['total_hours'] or 0
        days_w = work['days'] or 0
        data.append({
            'user_id': u.id,
            'name': u.get_full_name() or u.username,
            'total_hours': hours,
            'overtime_minutes': work['overtime'] or 0,
            'days_worked': days_w,
            'completed_tasks': completed,
            'total_tasks': total_task_count,
            'break_minutes': break_m,
            'productivity_score': get_productivity_score(u, days),
            'avg_hours_per_day': round(hours / max(days_w, 1), 1),
            'completion_rate': round(completed / max(total_task_count, 1) * 100, 1) if total_task_count else 0,
        })
    return sorted(data, key=lambda x: x['productivity_score'], reverse=True)


def get_focus_break_team(manager, days=30):  # Chart data: focus vs break per team member
    """Focus vs break data for chart — all team members."""
    team = get_team_performance(manager, days)
    return {
        'labels': [m['name'] for m in team],
        'focus': [round(m['total_hours'] - (m['break_minutes'] / 60), 1) for m in team],
        'break': [round(m['break_minutes'] / 60, 1) for m in team],
    }
