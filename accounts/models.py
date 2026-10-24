from django.db import models
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    # --- Role choices ---
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('employee', 'Employee'),
    ]
    # Maps role keys to display names for permission groups
    PERMISSION_ROLES = {
        'admin': 'Admin',
        'manager': 'Manager',
        'employee': 'Employee',
    }
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]
    # Reason why a user was deactivated
    DEACTIVATION_REASON_CHOICES = [
        ('sick_leave', 'Sick Leave'),
        ('annual_leave', 'Annual Leave'),
        ('maternity_leave', 'Maternity Leave'),
        ('paternity_leave', 'Paternity Leave'),
        ('marriage_leave', 'Marriage Leave'),
        ('unpaid_leave', 'Unpaid Leave'),
        ('resignation_pending', 'Resignation Pending'),
    ]
    # Filters deactivation reasons based on gender
    GENDER_FILTERED_REASONS = {
        'male': [r for r in DEACTIVATION_REASON_CHOICES if r[0] != 'maternity_leave'],
        'female': [r for r in DEACTIVATION_REASON_CHOICES if r[0] != 'paternity_leave'],
    }
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')  # Link to Django auth user
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='employee')  # admin / manager / employee
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='team_members')  # Reports to this manager
    manager_assigned_at = models.DateTimeField(null=True, blank=True, help_text='When the current manager was assigned')
    phone = models.CharField(max_length=50, blank=True)
    department = models.CharField(max_length=100, blank=True)
    deactivation_reason = models.CharField(max_length=30, choices=DEACTIVATION_REASON_CHOICES, null=True, blank=True)

    def get_deactivation_reasons(self):  # Returns gender-filtered deactivation reasons
        return self.GENDER_FILTERED_REASONS.get(self.gender, self.DEACTIVATION_REASON_CHOICES)

    class Meta:
        permissions = [
            ('can_manage_users', 'Can manage all users'),
            ('can_manage_roles', 'Can change user roles'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


# --- Signal handlers ---

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):  # Auto-create profile when a new User is saved
    if created and not kwargs.get('raw', False):
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):  # Auto-save profile when User is saved
    if not kwargs.get('raw', False):
        instance.profile.save()
