from django.db import models
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone




# --- Mixins ---

class SoftDeleteMixin(models.Model):
    """Adds soft-delete fields + methods."""
    is_deleted = models.BooleanField(default=False)  # Soft-delete flag
    deleted_at = models.DateTimeField(null=True, blank=True)  # When it was deleted
    deleted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='%(class)s_deleted'
    )  # Who deleted it
    restored_at = models.DateTimeField(null=True, blank=True)  # When it was restored

    class Meta:
        abstract = True

    def soft_delete(self, user=None):  # Mark as deleted
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    def restore(self):  # Undo soft-delete
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.restored_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'restored_at'])


class ArchiveMixin(models.Model):
    """Adds archive fields + methods."""
    is_archived = models.BooleanField(default=False)  # Whether record is archived
    archived_at = models.DateTimeField(null=True, blank=True)  # When it was archived

    class Meta:
        abstract = True

    def archive(self):  # Mark record as archived
        self.is_archived = True
        self.archived_at = timezone.now()
        self.save(update_fields=['is_archived', 'archived_at'])

    def unarchive(self):  # Remove archive status
        self.is_archived = False
        self.archived_at = None
        self.save(update_fields=['is_archived', 'archived_at'])


# --- Clients ---

class Client(SoftDeleteMixin, models.Model):
    """Companies or individuals the business works with."""
    name = models.CharField(max_length=200)  # Client name
    email = models.EmailField(blank=True)  # Contact email
    company = models.CharField(max_length=200, blank=True)  # Company name
    phone = models.CharField(max_length=50, blank=True)  # Contact phone
    notes = models.TextField(blank=True)  # Internal notes
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)  # Who added this client
    created_at = models.DateTimeField(auto_now_add=True)  # When added
    is_active = models.BooleanField(default=True)  # Whether client is active

    class Meta:
        ordering = ['name']
        permissions = [
            ('can_view_clients', 'Can view clients'),
            ('can_manage_clients', 'Can create/edit/delete clients'),
        ]

    def __str__(self):
        return self.name


# --- Projects ---

class Project(SoftDeleteMixin, ArchiveMixin, models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    name = models.CharField(max_length=200)  # Project name
    description = models.TextField(blank=True)  # Project description
    client = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='projects'
    )  # Associated client
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')  # Current status
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)  # Who created it
    created_at = models.DateTimeField(auto_now_add=True)  # When created
    updated_at = models.DateTimeField(auto_now=True)  # Last updated

    def archive(self):  # Archive project and update status
        """Override to also update status."""
        self.is_archived = True
        self.archived_at = timezone.now()
        self.status = 'archived'
        self.save(update_fields=['is_archived', 'archived_at', 'status'])

    def unarchive(self):  # Restore from archive
        self.is_archived = False
        self.archived_at = None
        self.status = 'active'
        self.save(update_fields=['is_archived', 'archived_at', 'status'])

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('can_view_projects', 'Can view projects'),
            ('can_manage_projects', 'Can create/edit/delete projects'),
        ]

    def __str__(self):
        return self.name


# --- Project Tasks ---

class ProjectTask(SoftDeleteMixin, ArchiveMixin, models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('in_review', 'In Review'),
        ('done', 'Done'),
        ('blocked', 'Blocked'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')  # Parent project
    title = models.CharField(max_length=200)  # Task title
    description = models.TextField(blank=True)  # Task description
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')  # Priority level
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='todo')  # Current status
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='project_tasks'
    )  # Who is working on this task
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)  # Who created it
    created_at = models.DateTimeField(auto_now_add=True)  # When created
    updated_at = models.DateTimeField(auto_now=True)  # Last updated
    estimated_hours = models.FloatField(default=0)  # Expected effort in hours
    deadline = models.DateField(null=True, blank=True)  # Due date
    completion_note = models.TextField(blank=True, help_text='Employee notes about what was done')  # Employee's completion notes
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_tasks')  # Who marked it done
    completed_at = models.DateTimeField(null=True, blank=True)  # When it was completed
    manager = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supervised_tasks',
        help_text='Snapshot: who was the employee\'s manager when this task was created'
    )  # Manager snapshot at task creation

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('can_view_tasks', 'Can view tasks'),
            ('can_manage_tasks', 'Can create/edit/delete tasks'),
            ('can_claim_tasks', 'Can claim open tasks'),
        ]

    def __str__(self):
        return f"[{self.project.name}] {self.title}"

    def save(self, *args, **kwargs):  # Auto-set manager and auto-join project membership
        # Step 1: detect if this is a new record
        is_new = not self.pk
        if is_new and self.assigned_to and not self.manager_id:
            from accounts.models import UserProfile
            profile = UserProfile.objects.filter(user=self.assigned_to).select_related('manager__user').first()
            if profile and profile.manager:
                self.manager = profile.manager.user
        super().save(*args, **kwargs)
        if is_new and self.assigned_to:
            ProjectMembership.objects.get_or_create(
                user=self.assigned_to,
                project=self.project,
                defaults={'assigned_by': self.created_by, 'role': 'member'}
            )

    @property
    def is_open(self):  # Whether task is unassigned
        return self.assigned_to is None

    @property
    def is_overdue(self):  # Whether deadline has passed
        if self.deadline and self.status not in ('done',):
            from django.utils import timezone
            return self.deadline < timezone.now().date()
        return False

    @property
    def total_logged_minutes(self):  # Total time logged in minutes
        return self.time_entries.aggregate(
            total=models.Sum('duration_minutes')
        )['total'] or 0

    @property
    def total_logged_hours(self):  # Total time logged in hours
        return round(self.total_logged_minutes / 60, 1)

    @property
    def progress_percent(self):  # Completion percentage based on status or hours
        if self.status == 'done':
            return 100
        if self.status in ('blocked',):
            return 0
        if self.estimated_hours > 0:
            return min(100, round((self.total_logged_hours / self.estimated_hours) * 100))
        return 0

    VALID_TRANSITIONS = {
        'todo': ['in_progress', 'blocked'],
        'in_progress': ['done', 'blocked', 'in_review'],
        'in_review': ['done', 'in_progress'],
        'done': ['in_progress'],
        'blocked': ['todo', 'in_progress'],
    }

    def can_transition_to(self, new_status):  # Check if status change is valid
        if self.status == new_status:
            return False, f'Task is already {self.get_status_display().lower()}.'
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            return False, f'Cannot move from {self.get_status_display()} to {dict(self.STATUS_CHOICES).get(new_status, new_status)}.'

        if self.status == 'done' and new_status == 'in_progress':
            return True, 'Admin override — reopening completed task.'
        return True, None

    def set_status(self, new_status, user=None):  # Change task status with validation
        can, msg = self.can_transition_to(new_status)
        if not can:
            raise ValueError(msg)
        old_status = self.status
        self._old_status = old_status
        self.status = new_status
        if new_status == 'done':
            if user:
                self.completed_by = user
            self.completed_at = timezone.now()
            for entry in self.time_entries.filter(is_running=True):
                entry.stop()
        elif new_status == 'in_progress' and old_status in ('done', 'blocked'):
            self.completed_by = None
            self.completed_at = None
        self.save()

    @property
    def actual_minutes(self):  # Convenience alias for total_logged_minutes
        return self.total_logged_minutes

    @property
    def actual_hours(self):  # Convenience alias for total_logged_hours
        return self.total_logged_hours

    @property
    def variance_minutes(self):  # Difference between estimated and actual time
        return self.actual_minutes - int(self.estimated_hours * 60)

    def can_complete(self):  # Check if task is eligible for completion
        if self.status == 'done':
            return False, 'Task is already completed.'
        if self.actual_minutes <= 0:
            return False, 'Please log at least one work session before completing this task.'
        return True, None

    def complete(self, user, note=''):  # Mark task as done with completion note
        can, msg = self.can_complete()
        if not can:
            raise ValueError(msg)
        self.completion_note = note or ''
        self.set_status('done', user=user)


# --- Project Memberships ---

class ProjectMembership(models.Model):
    """Links users to projects with a role."""
    ROLE_CHOICES = [
        ('project_manager', 'Project Manager'),
        ('member', 'Member'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_memberships')  # Member user
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')  # Project
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')  # Role in project
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_memberships')  # Who assigned them
    assigned_at = models.DateTimeField(default=timezone.now)  # When assigned
    is_active = models.BooleanField(default=True)  # Whether membership is active

    class Meta:
        verbose_name_plural = 'Project memberships'
        unique_together = ['user', 'project']

    def __str__(self):
        return f"{self.user.username} - {self.project.name} ({self.role})"


# --- Time Entries ---

class TimeEntry(SoftDeleteMixin, models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='time_entries')  # Who logged this time
    task = models.ForeignKey(ProjectTask, on_delete=models.CASCADE, related_name='time_entries')  # Task worked on
    attendance = models.ForeignKey(
        'Attendance', on_delete=models.CASCADE, related_name='time_entries',
        null=True, blank=True, help_text='The work session this entry belongs to'
    )  # Work session this belongs to
    start_time = models.DateTimeField()  # When work started
    end_time = models.DateTimeField(null=True, blank=True)  # When work ended
    duration_minutes = models.IntegerField(default=0)  # Total duration in minutes
    description = models.TextField(blank=True)  # What was done
    is_running = models.BooleanField(default=False)  # Whether timer is active
    is_billable = models.BooleanField(default=True)  # Whether this is billable
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_entries')  # Who approved this
    approved_at = models.DateTimeField(null=True, blank=True)  # When approved
    manager = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supervised_time_entries',
        help_text='Snapshot: who was the employee\'s manager when this entry was created'
    )  # Manager snapshot at creation

    class Meta:
        ordering = ['-start_time']
        verbose_name_plural = 'Time entries'
        permissions = [
            ('can_view_time_entries', 'Can view time entries'),
            ('can_manage_time_entries', 'Can create/edit/delete time entries'),
            ('can_correct_time', 'Can manually correct time entries'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.task.title} ({self.duration_minutes}m)"

    def save(self, *args, **kwargs):  # Auto-set manager snapshot
        is_new = not self.pk
        if is_new and self.user and not self.manager_id:
            from accounts.models import UserProfile
            profile = UserProfile.objects.filter(user=self.user).select_related('manager__user').first()
            if profile and profile.manager:
                self.manager = profile.manager.user
        super().save(*args, **kwargs)

    def stop(self):  # Stop a running timer and calculate duration
        from django.utils import timezone
        self.end_time = timezone.now()
        self.duration_minutes = int((self.end_time - self.start_time).total_seconds() / 60)
        self.is_running = False
        self.save()

    @property
    def effective_hours(self):  # Duration converted to hours
        return round(self.duration_minutes / 60, 2)

    @property
    def is_approved(self):  # Whether entry has been approved
        return self.approved_by is not None

    def approve(self, user):  # Approve this time entry
        from django.utils import timezone
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

    @classmethod
    def get_active_session(cls, user):  # Get today's active attendance for a user
        today = timezone.now().date()
        attendance = Attendance.objects.filter(
            user=user, date=today, check_in__isnull=False, check_out__isnull=True
        ).first()
        return attendance


# --- Attendance ---

class Attendance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendances')  # Employee
    date = models.DateField()  # Attendance date
    check_in = models.DateTimeField(null=True, blank=True)  # Clock-in time
    check_out = models.DateTimeField(null=True, blank=True)  # Clock-out time
    total_hours = models.FloatField(default=0)  # Total hours worked
    is_late = models.BooleanField(default=False)  # Whether employee arrived late
    overtime_minutes = models.IntegerField(default=0)  # Overtime in minutes
    is_completed = models.BooleanField(default=False, help_text='True once check_out is set and session is finalized')  # Whether session is finalized
    manager = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supervised_attendances',
        help_text='Snapshot: who was the employee\'s manager on this date'
    )  # Manager snapshot for this date

    class Meta:
        unique_together = ['user', 'date']
        ordering = ['-date', '-check_in']
        permissions = [
            ('can_view_attendance', 'Can view attendance records'),
            ('can_view_all_attendance', 'Can view all attendance records'),
            ('can_manage_attendance', 'Can manage attendance records'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.date}"

    def save(self, *args, **kwargs):  # Auto-set date, completion flag, and manager
        is_new = not self.pk
        if not self.date:
            self.date = timezone.now().date()
        if self.check_out and not self.is_completed:
            self.is_completed = True
        if is_new and self.user and not self.manager_id and self.date:
            from accounts.models import UserProfile
            profile = UserProfile.objects.filter(user=self.user).select_related('manager__user').first()
            if profile and profile.manager:
                self.manager = profile.manager.user
        super().save(*args, **kwargs)

    @property
    def is_active(self):  # Whether user is currently clocked in
        return self.check_in is not None and self.check_out is None

    @property
    def running_time_entries(self):  # Active timers during this session
        return self.time_entries.filter(is_running=True)

    @property
    def has_running_timers(self):  # Whether any timer is still running
        return self.running_time_entries.exists()

    @property
    def total_break_minutes(self):  # Total break time taken during session
        from django.db.models import Sum
        return self.breaks.aggregate(total=Sum('duration_minutes'))['total'] or 0

    @property
    def net_work_minutes(self):  # Work time minus breaks in minutes
        if not self.check_in:
            return 0
        end = self.check_out or timezone.now()
        gross = int((end - self.check_in).total_seconds() / 60)
        return max(0, gross - self.total_break_minutes)

    @property
    def net_work_hours(self):  # Net hours worked (after breaks)
        return round(self.net_work_minutes / 60, 2)

    def can_clock_out(self):  # Validate clock-out conditions
        if self.has_running_timers:
            return False, 'Stop all running timers before clocking out.'
        if self.check_out:
            return False, 'Already clocked out.'
        return True, None

    def finalize(self):  # Complete the work session and calculate totals
        from django.db.models import Sum
        can, msg = self.can_clock_out()
        if not can:
            raise ValueError(msg)
        now = timezone.now()
        self.check_out = now
        gross_seconds = (now - self.check_in).total_seconds()
        break_minutes = self.breaks.aggregate(total=Sum('duration_minutes'))['total'] or 0
        work_seconds = max(0, gross_seconds - (break_minutes * 60))
        self.total_hours = round(work_seconds / 3600, 2)
        if work_seconds > 8 * 3600:
            self.overtime_minutes = int((work_seconds - 8 * 3600) / 60)
        self.is_completed = True
        self.save()


# --- Breaks ---

class Break(models.Model):
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name='breaks')  # Attendance session
    break_start = models.DateTimeField()  # When break started
    break_end = models.DateTimeField(null=True, blank=True)  # When break ended
    duration_minutes = models.IntegerField(default=0)  # Break duration
    paused_entry = models.ForeignKey(
        'TimeEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paused_by_breaks',
        help_text='The running timer that was auto-stopped when this break started'
    )  # Timer that was auto-paused

    def __str__(self):
        return f"Break ({self.attendance.user.username}) - {self.attendance.date}"

    def end(self):  # Complete the break and return paused timer
        from django.utils import timezone
        self.break_end = timezone.now()
        self.duration_minutes = int((self.break_end - self.break_start).total_seconds() / 60)
        self.save()
        return self.paused_entry


# --- Legacy Task ---

class Task(models.Model):
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name='tasks')  # Attendance session
    title = models.CharField(max_length=200)  # Task title
    description = models.TextField(blank=True)  # Task description
    start_time = models.DateTimeField()  # When task started
    end_time = models.DateTimeField(null=True, blank=True)  # When task ended

    def __str__(self):
        return self.title


# --- Audit Log ---

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('clock_in', 'Clock In'),
        ('clock_out', 'Clock Out'),
        ('status_change', 'Status Change'),
        ('assignment', 'Assignment'),
        ('correction', 'Correction'),
        ('override', 'Override'),
        ('deactivation', 'Deactivation'),
        ('login', 'Login'),
        ('leave_approved', 'Leave Approved'),
        ('leave_rejected', 'Leave Rejected'),
    ]
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')  # Who performed the action
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)  # Type of action
    action_detail = models.CharField(max_length=500, blank=True, help_text='Human-readable description')  # Human-readable description
    target_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)  # Model type of target
    target_id = models.PositiveIntegerField(null=True, blank=True)  # ID of target record
    target = GenericForeignKey('target_type', 'target_id')  # Generic reference to target
    target_repr = models.CharField(max_length=255, blank=True, help_text='String representation of target at log time')  # Snapshot of target
    metadata = models.JSONField(default=dict, blank=True, help_text='Extra context (old/new values, IP, etc.)')  # Extra context
    ip_address = models.GenericIPAddressField(blank=True, null=True)  # IP address of actor
    created_at = models.DateTimeField(auto_now_add=True)  # When log was created

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Audit log'
        verbose_name_plural = 'Audit logs'

    def __str__(self):
        return f"[{self.created_at.date()}] {self.actor} {self.action} {self.target_repr}"


# --- Notifications ---

class Notification(models.Model):
    TYPE_CHOICES = [
        ('clock_in', 'Clock In'),
        ('break_reminder', 'Break Reminder'),
        ('break_start', 'Break Start'),
        ('extended_break', 'Extended Break'),
        ('clock_out_reminder', 'Clock Out Reminder'),
        ('task_assigned', 'Task Assigned'),
        ('task_claimed', 'Task Claimed'),
        ('meeting_invite', 'Meeting Invite'),
        ('meeting_reminder', 'Meeting Reminder'),
        ('missed_meeting', 'Missed Meeting'),
        ('deadline_risk', 'Deadline Risk'),
        ('daily_summary', 'Daily Summary'),
        ('leave_requested', 'Leave Requested'),
        ('leave_approved', 'Leave Approved'),
        ('leave_rejected', 'Leave Rejected'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    CATEGORY_CHOICES = [
        ('attendance', 'Attendance'),
        ('task', 'Task'),
        ('meeting', 'Meeting'),
        ('leave', 'Leave'),
        ('system', 'System'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')  # Recipient
    message = models.TextField()  # Notification body text
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)  # Notification type
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')  # Urgency level
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default='system')  # Category
    is_read = models.BooleanField(default=False)  # Whether user has seen it
    is_dismissed = models.BooleanField(default=False)  # Whether user dismissed it
    expires_at = models.DateTimeField(null=True, blank=True, help_text='Auto-dismiss after this time')  # Auto-expiry
    related_url = models.CharField(max_length=500, blank=True, help_text='Deep link to the related resource')  # Deep link
    created_at = models.DateTimeField(auto_now_add=True)  # When created

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('can_view_reports', 'Can view reports'),
            ('can_export_data', 'Can export data (CSV/PDF)'),
            ('can_soft_delete', 'Can soft-delete and restore users'),
        ]

    @property
    def priority_order(self):  # Numeric sort order for priority
        order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
        return order.get(self.priority, 4)

    @property
    def is_expired(self):  # Whether notification has passed expiry
        from django.utils import timezone
        return self.expires_at and timezone.now() > self.expires_at

    @property
    def icon_class(self):  # Bootstrap icon class based on type
        icons = {
            'clock_in': 'bi-sunrise', 'break_reminder': 'bi-cup-hot',
            'break_start': 'bi-cup-hot', 'extended_break': 'bi-eye',
            'clock_out_reminder': 'bi-moon', 'task_assigned': 'bi-list-task',
            'task_claimed': 'bi-hand-index', 'meeting_invite': 'bi-people',
            'meeting_reminder': 'bi-bell', 'missed_meeting': 'bi-x-circle',
            'deadline_risk': 'bi-exclamation-triangle', 'daily_summary': 'bi-graph-up',
            'leave_requested': 'bi-file-earmark-text', 'leave_approved': 'bi-check-circle',
            'leave_rejected': 'bi-x-circle',
        }
        return icons.get(self.type, 'bi-info-circle')

    @property
    def color_class(self):  # Text color based on priority
        colors = {'urgent': '#EF4444', 'high': '#F59E0B', 'medium': '#818CF8', 'low': '#64748B'}
        return colors.get(self.priority, '#64748B')

    @property
    def bg_class(self):  # Background color based on priority
        colors = {'urgent': 'rgba(239,68,68,0.12)', 'high': 'rgba(245,158,11,0.12)', 'medium': 'rgba(129,140,248,0.12)', 'low': 'rgba(100,116,139,0.08)'}
        return colors.get(self.priority, 'rgba(100,116,139,0.08)')

    def __str__(self):
        return f"[{self.priority}] {self.type}: {self.message[:40]}"


# --- Holidays ---

class Holiday(models.Model):
    HOLIDAY_TYPES = [
        ('static', 'Static (Fixed Date)'),
        ('religious', 'Religious (Variable)'),
    ]
    date = models.DateField()  # Holiday date
    name = models.CharField(max_length=200, verbose_name='Holiday name')  # Holiday name
    description = models.TextField(blank=True)  # Optional description
    type = models.CharField(max_length=20, choices=HOLIDAY_TYPES, default='static')  # Static or religious
    year = models.IntegerField()  # Year this holiday applies to
    is_active = models.BooleanField(default=True)  # Whether holiday is in effect
    created_at = models.DateTimeField(auto_now_add=True)  # When added

    class Meta:
        ordering = ['date']
        unique_together = ['date', 'year']
        verbose_name = 'Public Holiday'
        verbose_name_plural = 'Public Holidays'
        permissions = [
            ('can_view_holidays', 'Can view holidays'),
            ('can_manage_holidays', 'Can create/edit/delete holidays'),
        ]

    def __str__(self):
        return f"{self.name} ({self.date})"

    @classmethod
    def is_holiday(cls, date):  # Check if a date is a holiday
        return cls.objects.filter(date=date, year=date.year, is_active=True).exists()

    @classmethod
    def get_holiday(cls, date):  # Get holiday record for a date
        try:
            return cls.objects.get(date=date, year=date.year, is_active=True)
        except cls.DoesNotExist:
            return None


# --- Meetings ---

class Meeting(SoftDeleteMixin, models.Model):
    MEETING_TYPES = [
        ('standup', 'Daily Standup'),
        ('sprint_planning', 'Sprint Planning'),
        ('sprint_review', 'Sprint Review'),
        ('retro', 'Retrospective'),
        ('one_on_one', '1:1 Meeting'),
        ('team', 'Team Meeting'),
        ('client', 'Client Meeting'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('missed', 'Missed'),
        ('cancelled', 'Cancelled'),
    ]
    title = models.CharField(max_length=200)  # Meeting title
    description = models.TextField(blank=True)  # Meeting description
    meeting_type = models.CharField(max_length=30, choices=MEETING_TYPES, default='other')  # Type of meeting
    date = models.DateField()  # Meeting date
    start_time = models.TimeField()  # Start time
    end_time = models.TimeField()  # End time
    duration_minutes = models.IntegerField(default=0, help_text='Auto-calculated on save')  # Duration in minutes
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')  # Current status
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_meetings')  # Who created it
    participants = models.ManyToManyField(User, related_name='meetings')  # Invited participants
    attendees = models.ManyToManyField(User, related_name='attended_meetings', blank=True)  # Who actually attended
    is_important = models.BooleanField(default=False)  # Priority flag
    is_archived = models.BooleanField(default=False)  # Whether archived
    notes = models.TextField(blank=True, help_text='Meeting notes / summary')  # Meeting notes
    created_at = models.DateTimeField(auto_now_add=True)  # When created
    updated_at = models.DateTimeField(auto_now=True)  # Last updated

    class Meta:
        ordering = ['-date', '-start_time']
        permissions = [
            ('can_view_meetings', 'Can view meetings'),
            ('can_manage_meetings', 'Can create/edit/delete meetings'),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):  # Auto-calculate duration from times
        if self.start_time and self.end_time:
            from datetime import datetime
            ref = datetime.combine(self.date or timezone.now().date(), self.start_time)
            ref_end = datetime.combine(self.date or timezone.now().date(), self.end_time)
            diff = ref_end - ref
            self.duration_minutes = int(diff.total_seconds() / 60)
        super().save(*args, **kwargs)

    @property
    def is_today(self):  # Whether meeting is today
        return self.date == timezone.now().date()

    @property
    def is_past(self):  # Whether meeting end time has passed
        from datetime import datetime
        ref = datetime.combine(self.date, self.end_time)
        now = timezone.now()
        if timezone.is_aware(ref):
            return ref < now
        return timezone.make_aware(ref) < now

    @property
    def is_ongoing(self):  # Whether meeting is currently in progress
        from datetime import datetime
        start = timezone.make_aware(datetime.combine(self.date, self.start_time), timezone.get_current_timezone())
        end = timezone.make_aware(datetime.combine(self.date, self.end_time), timezone.get_current_timezone())
        now = timezone.now()
        return start <= now <= end

    @property
    def minutes_since_start(self):  # Minutes elapsed since meeting started
        from datetime import datetime
        start = timezone.make_aware(datetime.combine(self.date, self.start_time), timezone.get_current_timezone())
        now = timezone.now()
        if now > start:
            return int((now - start).total_seconds() / 60)
        return 0

    @property
    def minutes_until_start(self):  # Minutes until meeting begins
        from datetime import datetime
        start = timezone.make_aware(datetime.combine(self.date, self.start_time), timezone.get_current_timezone())
        now = timezone.now()
        if start > now:
            return int((start - now).total_seconds() / 60)
        return 0

    @property
    def attendee_count(self):  # Number of actual attendees
        return self.attendees.count()

    @property
    def participant_count(self):  # Number of invited participants
        return self.participants.count()

    @property
    def status_display(self):  # Human-readable status
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def meeting_type_icon(self):  # Bootstrap icon for meeting type
        icons = {
            'standup': 'bi-sunrise',
            'sprint_planning': 'bi-clipboard-data',
            'sprint_review': 'bi-eye',
            'retro': 'bi-arrow-repeat',
            'one_on_one': 'bi-person-badge',
            'team': 'bi-people',
            'client': 'bi-building',
            'other': 'bi-chat-dots',
        }
        return icons.get(self.meeting_type, 'bi-chat-dots')


# --- Leave Requests ---

class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('annual', 'Annual Leave'),
        ('sick', 'Sick Leave'),
        ('maternity', 'Maternity Leave'),
        ('paternity', 'Paternity Leave'),
        ('marriage', 'Marriage Leave'),
        ('unpaid', 'Unpaid Leave'),
    ]
    GENDER_FILTERED_LEAVE_TYPES = {
        'male': [t for t in LEAVE_TYPES if t[0] != 'maternity'],
        'female': [t for t in LEAVE_TYPES if t[0] != 'paternity'],
    }
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leave_requests')  # Who is taking leave
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)  # Type of leave
    start_date = models.DateField()  # Leave start date
    end_date = models.DateField()  # Leave end date
    total_days = models.PositiveIntegerField()  # Total days requested
    reason = models.TextField(blank=True)  # Reason for leave
    attachment = models.FileField(upload_to='leave_attachments/', blank=True, null=True)  # Supporting document
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')  # Approval status
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_leaves')  # Who reviewed it
    reviewed_at = models.DateTimeField(null=True, blank=True)  # When reviewed
    manager_note = models.TextField(blank=True)  # Manager's note on decision
    created_at = models.DateTimeField(auto_now_add=True)  # When submitted
    updated_at = models.DateTimeField(auto_now=True)  # Last updated

    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('can_manage_leaves', 'Can manage all leave requests'),
        ]

    # Maps leave types to profile deactivation reasons
    _leave_to_deactivation = {
        'sick': 'sick_leave',
        'annual': 'annual_leave',
        'maternity': 'maternity_leave',
        'paternity': 'paternity_leave',
        'marriage': 'marriage_leave',
        'unpaid': 'unpaid_leave',
        'bereavement': None,
    }

    def save(self, *args, **kwargs):  # Deactivate/reactivate user on leave approval/rejection
        # Step 1: capture old status for change detection
        is_new = self.pk is None
        if not is_new:
            old = LeaveRequest.objects.get(pk=self.pk)
            old_status = old.status
        else:
            old_status = None
        super().save(*args, **kwargs)
        if old_status == self.status:
            return
        profile = self.employee.profile
        if self.status == 'approved':
            self.employee.is_active = False
            self.employee.save(update_fields=['is_active'])
            reason = self._leave_to_deactivation.get(self.leave_type)
            if reason:
                profile.deactivation_reason = reason
                profile.save(update_fields=['deactivation_reason'])
        elif old_status == 'approved' and self.status in ('rejected', 'cancelled'):
            has_other_active = LeaveRequest.objects.filter(
                employee=self.employee, status='approved'
            ).exclude(pk=self.pk).exists()
            if not has_other_active:
                self.employee.is_active = True
                self.employee.save(update_fields=['is_active'])
                profile.deactivation_reason = None
                profile.save(update_fields=['deactivation_reason'])

    def __str__(self):
        return f"{self.employee.username} - {self.get_leave_type_display()} ({self.start_date} to {self.end_date})"

    @property
    def status_badge(self):  # CSS background color for status badge
        colors = {
            'pending': 'rgba(245,158,11,0.15);color:#FBBF24',
            'approved': 'rgba(52,211,153,0.15);color:#86EFAC',
            'rejected': 'rgba(239,68,68,0.15);color:#FCA5A5',
            'cancelled': 'rgba(148,163,184,0.15);color:#CBD5E1',
        }
        bg = colors.get(self.status, 'rgba(148,163,184,0.15);color:#CBD5E1')
        return f'background:{bg};border:1px solid rgba(148,163,184,0.1);font-size:0.65rem;'

    @classmethod
    def get_leave_types_for_gender(cls, gender):  # Return leave types available for given gender
        return cls.GENDER_FILTERED_LEAVE_TYPES.get(gender, cls.LEAVE_TYPES)

    @classmethod
    def is_on_leave(cls, user, date):  # Check if user has approved leave for given date
        return cls.objects.filter(
            employee=user, status='approved',
            start_date__lte=date, end_date__gte=date
        ).exists()
