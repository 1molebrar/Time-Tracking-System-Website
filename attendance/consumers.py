import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()


# --- WebSocket Consumers ---

class BaseConsumer(AsyncWebsocketConsumer):
    """Base class with send_json helper and user property."""

    @property
    def user(self):  # Get the authenticated user from the connection scope
        return self.scope.get('user')

    async def send_json(self, content):  # Send JSON data over the WebSocket
        await self.send(text_data=json.dumps(content))

    async def receive(self, text_data=None, bytes_data=None):  # Ignore client-sent messages (server-push only)
        pass


class UserNotificationConsumer(BaseConsumer):
    """
    Per-user notification stream.
    Group name: user_{user_id}
    Subscribes to personal events: new notifications, timer state, clock state.
    """

    async def connect(self):
        # Reject anonymous connections, then join the user's personal group
        if self.user.is_anonymous:
            await self.close()
            return
        self.group_name = f'user_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.push_initial_state()

    async def disconnect(self, close_code):  # Leave the personal group on disconnect
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def push_initial_state(self):  # Send current state (unread count, timer, clock) on connect
        data = await self._get_initial_state()
        await self.send_json({'type': 'init', **data})

    @database_sync_to_async
    def _get_initial_state(self):  # Query DB for user's current attendance, timer, and notifications
        from .models import Notification, TimeEntry, Attendance
        from django.utils import timezone
        now = timezone.now()
        active_attendance = Attendance.objects.filter(user=self.user, clock_out__isnull=True).first()
        running_timer = TimeEntry.objects.filter(user=self.user, is_running=True).select_related('task').first()
        unread = Notification.objects.filter(user=self.user, is_read=False, is_dismissed=False)
        return {
            'unread_count': unread.count(),
            'notifications': [
                {
                    'id': n.id,
                    'message': n.message,
                    'type': n.type,
                    'priority': n.priority,
                    'category': n.category,
                    'created_at': n.created_at.isoformat(),
                    'related_url': n.related_url,
                    'icon': n.icon_class,
                    'color': n.color_class,
                    'bg': n.bg_class,
                    'url': n.related_url,
                }
                for n in unread.order_by('-created_at')[:10]
            ],
            'clocked_in': active_attendance is not None,
            'active_timer': {
                'task_id': running_timer.task.id,
                'task_title': running_timer.task.title,
                'started_at': running_timer.start_time.isoformat(),
                'duration_minutes': running_timer.duration_minutes,
            } if running_timer else None,
        }

    # --- Event handlers (called by channel layer when messages are broadcast) ---

    async def notification_new(self, event):  # Push a new notification to the user
        await self.send_json({
            'type': 'notification_new',
            'id': event['id'],
            'message': event['message'],
            'priority': event['priority'],
            'category': event['category'],
            'related_url': event.get('related_url', ''),
            'created_at': event.get('created_at', ''),
            'icon': event.get('icon', 'bi-info-circle'),
            'color': event.get('color', '#818CF8'),
            'bg': event.get('bg', 'rgba(99,102,241,0.05)'),
            'url': event.get('related_url', ''),
        })

    async def notification_read(self, event):  # Mark a notification as read on the client
        await self.send_json({
            'type': 'notification_read',
            'notification_id': event['notification_id'],
        })

    async def clock_event(self, event):  # Clock in / clock out event
        await self.send_json({
            'type': 'clock_event',
            'action': event['action'],
            'user_id': event.get('user_id'),
            'username': event.get('username', ''),
            'timestamp': event.get('timestamp', ''),
            'user_clocked_in': event.get('user_clocked_in', False),
        })

    async def timer_event(self, event):  # Timer start / stop event
        await self.send_json({
            'type': 'timer_event',
            'action': event['action'],
            'task_id': event.get('task_id'),
            'task_title': event.get('task_title', ''),
            'started_at': event.get('started_at'),
            'duration_minutes': event.get('duration_minutes'),
        })

    async def task_status_change(self, event):  # Task status changed event
        await self.send_json({
            'type': 'task_status_change',
            'task_id': event['task_id'],
            'task_title': event.get('task_title', ''),
            'old_status': event.get('old_status', ''),
            'new_status': event.get('new_status', ''),
            'project_id': event.get('project_id'),
            'changed_by': event.get('changed_by', ''),
        })

    async def meeting_event(self, event):  # Meeting created / updated / cancelled event
        await self.send_json({
            'type': 'meeting_event',
            'action': event['action'],
            'meeting_id': event.get('meeting_id'),
            'title': event.get('title', ''),
            'status': event.get('status', ''),
        })


class TaskBoardConsumer(BaseConsumer):
    """
    Shared task board for a specific project.
    Group name: task_board_{project_id}
    """

    async def connect(self):
        # Reject anonymous or missing project_id, then join the project board group
        if self.user.is_anonymous:
            await self.close()
            return
        self.project_id = self.scope['url_route']['kwargs'].get('project_id')
        if not self.project_id:
            await self.close()
            return
        self.group_name = f'task_board_{self.project_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):  # Leave the project board group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def task_status_change(self, event):  # Broadcast task status change to board
        await self.send_json({
            'type': 'task_status_change',
            'task_id': event['task_id'],
            'task_title': event.get('task_title', ''),
            'old_status': event.get('old_status', ''),
            'new_status': event.get('new_status', ''),
            'changed_by': event.get('changed_by', ''),
        })

    async def task_created(self, event):  # Broadcast new task to board
        await self.send_json({
            'type': 'task_created',
            'task_id': event['task_id'],
            'task_title': event.get('task_title', ''),
            'assigned_to': event.get('assigned_to', ''),
            'priority': event.get('priority', 'medium'),
        })

    async def task_deleted(self, event):  # Broadcast task deletion to board
        await self.send_json({
            'type': 'task_deleted',
            'task_id': event['task_id'],
        })


class AttendanceDashboardConsumer(BaseConsumer):
    """
    Admin/manager live dashboard.
    Group name: admin_dashboard
    """

    async def connect(self):
        # Only allow admin/manager roles
        if self.user.is_anonymous or self.user.profile.role not in ('admin', 'manager'):
            await self.close()
            return
        self.group_name = 'admin_dashboard'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):  # Leave the admin dashboard group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def clock_event(self, event):  # Push clock events to admin dashboard
        await self.send_json({
            'type': 'clock_event',
            'action': event['action'],
            'user_id': event.get('user_id'),
            'username': event.get('username', ''),
            'timestamp': event.get('timestamp', ''),
        })

    async def dashboard_refresh(self, event):  # Signal dashboard to reload analytics data
        await self.send_json({
            'type': 'dashboard_refresh',
            'section': event.get('section', 'all'),
        })
