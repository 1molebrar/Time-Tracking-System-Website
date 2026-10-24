"""
ASGI config for timetracker project.

Supports both HTTP (Django) and WebSocket (Channels) protocols.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'timetracker.settings')

# Get the ASGI application for standard HTTP requests
django_asgi = get_asgi_application()

import attendance.routing

# Protocol router: handles both HTTP and WebSocket connections
application = ProtocolTypeRouter({
    'http': django_asgi,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            attendance.routing.websocket_urlpatterns
        )
    ),
})
