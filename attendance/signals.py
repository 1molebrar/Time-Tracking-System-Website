from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User


def _send(channel_layer, group, event):
    """Synchronous helper to send to a channel layer group."""
    async_to_sync(channel_layer.group_send)(group, event)


def notify_user(user_id, event):
    """Send an event to a specific user's notification stream."""
    channel_layer = get_channel_layer()
    _send(channel_layer, f'user_{user_id}', event)


def notify_dashboard(event):
    """Broadcast to admin/manager live dashboard."""
    channel_layer = get_channel_layer()
    _send(channel_layer, 'admin_dashboard', event)


def notify_task_board(project_id, event):
    """Broadcast to all viewers of a project's task board."""
    channel_layer = get_channel_layer()
    _send(channel_layer, f'task_board_{project_id}', event)




@receiver(post_save)
def on_notification_created(sender, instance, created, **kwargs):  # Broadcast new notification to user via WebSocket
    from .models import Notification
    if sender is Notification and created:
        notify_user(instance.user_id, {
            'type': 'notification_new',
            'id': instance.id,
            'message': instance.message,
            'priority': instance.priority,
            'category': instance.category,
            'related_url': instance.related_url or '',
            'created_at': instance.created_at.isoformat() if instance.created_at else '',
            'icon': instance.icon_class,
            'color': instance.color_class,
            'bg': instance.bg_class,
        })




@receiver(post_save)
def on_task_saved(sender, instance, created, **kwargs):  # Notify board and user on task create/update
    from .models import ProjectTask
    if sender is not ProjectTask:
        return
    project_id = instance.project_id

    if created:
        event = {
            'type': 'task_created',
            'task_id': instance.id,
            'task_title': instance.title,
            'assigned_to': instance.assigned_to.username if instance.assigned_to else '',
            'priority': instance.priority,
        }
        notify_task_board(project_id, event)

        notify_dashboard({'type': 'dashboard_refresh', 'section': 'tasks'})
    else:
        event = {
            'type': 'task_status_change',
            'task_id': instance.id,
            'task_title': instance.title,
            'project_id': project_id,
        }

        if hasattr(instance, '_old_status') and instance._old_status != instance.status:
            event['old_status'] = instance._old_status
            event['new_status'] = instance.status
        notify_task_board(project_id, event)

    if instance.assigned_to:
        user_event = {
            'type': 'task_status_change',
            'task_id': instance.id,
            'task_title': instance.title,
            'new_status': instance.status,
            'project_id': project_id,
        }
        if not created:
            user_event['old_status'] = getattr(instance, '_old_status', instance.status)
        notify_user(instance.assigned_to_id, user_event)


@receiver(post_delete)
def on_task_deleted(sender, instance, **kwargs):  # Notify board when task is deleted
    from .models import ProjectTask
    if sender is ProjectTask:
        notify_task_board(instance.project_id, {
            'type': 'task_deleted',
            'task_id': instance.id,
        })




@receiver(post_save)
def on_attendance_saved(sender, instance, created, **kwargs):  # Notify user and dashboard on clock-in/out
    from .models import Attendance
    if sender is not Attendance:
        return
    action = 'clock_in' if created and instance.check_out is None else 'clock_out'
    if created or (not created and instance.check_out is not None):
        user = instance.user
        event = {
            'type': 'clock_event',
            'action': action,
            'user_id': user.id,
            'username': user.username,
            'timestamp': instance.check_in.isoformat() if instance.check_in else '',
            'user_clocked_in': instance.check_out is None,
        }
        notify_user(user.id, event)
        notify_dashboard(event)




@receiver(post_save)
def on_meeting_saved(sender, instance, created, **kwargs):  # Notify participants on meeting create/update/cancel
    from .models import Meeting
    if sender is not Meeting:
        return
    action = 'created' if created else 'updated'
    if not created and instance.status == 'cancelled':
        action = 'cancelled'
    event = {
        'type': 'meeting_event',
        'action': action,
        'meeting_id': instance.id,
        'title': instance.title,
        'status': instance.status,
    }

    for user in instance.participants.all():
        notify_user(user.id, event)

    if instance.created_by:
        notify_user(instance.created_by.id, event)




@receiver(post_save)
def on_timeentry_saved(sender, instance, created, **kwargs):  # Notify user when timer starts/stops
    from .models import TimeEntry
    if sender is not TimeEntry:
        return
    if instance.is_running:
        event = {
            'type': 'timer_event',
            'action': 'timer_start',
            'task_id': instance.task_id,
            'task_title': instance.task.title if instance.task_id else '',
            'started_at': instance.start_time.isoformat() if instance.start_time else '',
            'duration_minutes': instance.duration_minutes or 0,
        }
        notify_user(instance.user_id, event)
