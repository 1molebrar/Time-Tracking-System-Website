from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):  # Show profile fields inline on the User admin page
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(BaseUserAdmin):  # Custom User admin with profile inline and role filter
    inlines = [UserProfileInline]
    list_display = ['username', 'email', 'get_role', 'is_staff']
    list_filter = ['profile__role']

    def get_role(self, obj):  # Display the user's role in the admin list view
        try:
            return obj.profile.get_role_display()
        except:
            return 'N/A'
    get_role.short_description = 'Role'
    get_role.admin_order_field = 'profile__role'


# Replace the default User admin with our custom one
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
