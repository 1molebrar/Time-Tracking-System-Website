from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    # App configuration for the attendance module
    name = 'attendance'

    def ready(self):  # Import signals when Django starts
        import attendance.signals
