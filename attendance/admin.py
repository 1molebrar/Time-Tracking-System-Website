from django.contrib import admin
from .models import (
    Attendance, Break, Task, Notification,
    Client, Project, ProjectTask, TimeEntry, Holiday, Meeting,
)


# --- Inline admin classes ---

class BreakInline(admin.TabularInline):  # Show breaks inline on attendance form
    model = Break
    extra = 0
    readonly_fields = ['break_start', 'break_end', 'duration_minutes']


class TaskInline(admin.TabularInline):  # Show daily tasks inline on attendance form
    model = Task
    extra = 0


class TaskInlineProject(admin.TabularInline):  # Show project tasks inline on project form
    model = ProjectTask
    extra = 0
    fields = ['title', 'priority', 'status', 'assigned_to', 'estimated_hours', 'deadline']


# --- Model admin registrations ---

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'date', 'check_in', 'check_out', 'total_hours', 'is_late', 'overtime_minutes']
    list_filter = ['is_late', 'date', 'user']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    date_hierarchy = 'date'
    readonly_fields = ['total_hours', 'is_late', 'overtime_minutes']
    inlines = [BreakInline, TaskInline]


@admin.register(Break)
class BreakAdmin(admin.ModelAdmin):
    list_display = ['attendance', 'break_start', 'break_end', 'duration_minutes']
    list_filter = ['attendance__date']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'attendance', 'start_time', 'end_time']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'is_read', 'created_at']
    list_filter = ['type', 'is_read']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'email', 'is_active', 'created_at']
    search_fields = ['name', 'company']
    list_filter = ['is_active']


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'client', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['name']
    inlines = [TaskInlineProject]


@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'priority', 'status', 'assigned_to', 'estimated_hours', 'deadline']
    list_filter = ['status', 'priority', 'project']
    search_fields = ['title']
    date_hierarchy = 'deadline'


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ['user', 'task', 'start_time', 'end_time', 'duration_minutes', 'is_running']
    list_filter = ['is_running', 'start_time']
    search_fields = ['user__username', 'task__title']


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ['date', 'name', 'year', 'is_active']
    list_filter = ['year', 'is_active']
    search_fields = ['name']
    date_hierarchy = 'date'
    list_editable = ['is_active']


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'start_time', 'end_time', 'created_by', 'duration_minutes']
    list_filter = ['date']
    search_fields = ['title', 'description']
    date_hierarchy = 'date'
    filter_horizontal = ['participants']
