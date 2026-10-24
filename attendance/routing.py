from django.urls import re_path
from . import consumers

# --- WebSocket URL patterns ---
websocket_urlpatterns = [
    re_path(r'^ws/notifications/$', consumers.UserNotificationConsumer.as_asgi()),       # Personal notification stream
    re_path(r'^ws/task-board/(?P<project_id>\d+)/$', consumers.TaskBoardConsumer.as_asgi()),  # Per-project task board
    re_path(r'^ws/dashboard/$', consumers.AttendanceDashboardConsumer.as_asgi()),         # Admin/manager live dashboard
]
