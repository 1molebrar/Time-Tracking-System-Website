from django.contrib import admin
from django.urls import path, include

# URL routing: maps incoming URLs to the appropriate app views
urlpatterns = [
    path('', include('accounts.urls')),
    path('', include('attendance.urls')),
    path('admin/', admin.site.urls),
]
