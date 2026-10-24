from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
from .models import UserProfile


class EmployeeCreateForm(forms.ModelForm):
    ROLE_CHOICES = [('employee', 'Employee'), ('manager', 'Manager')]

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Confirm Password'
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES, initial='employee',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Role'
    )
    gender = forms.ChoiceField(
        choices=UserProfile.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Gender',
        required=False,
    )
    manager = forms.ModelChoiceField(
        queryset=UserProfile.objects.filter(role='manager', user__is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Manager'
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):  # Reject duplicate usernames
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean(self):  # Validate that passwords match
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('confirm_password')
        if password and confirm and password != confirm:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned

    def save(self, commit=True):  # Create User and corresponding UserProfile
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            role = self.cleaned_data.get('role', 'employee')
            gender = self.cleaned_data.get('gender', '')
            manager_profile = self.cleaned_data.get('manager')
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    'role': role,
                    'gender': gender,
                    'manager': manager_profile,
                    'manager_assigned_at': timezone.now() if manager_profile else None,
                }
            )
        return user


class EmployeeEditForm(forms.ModelForm):
    ROLE_CHOICES = [('employee', 'Employee'), ('manager', 'Manager')]

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='New Password (leave blank to keep current)',
        required=False,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Confirm New Password',
        required=False,
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Role'
    )
    gender = forms.ChoiceField(
        choices=UserProfile.GENDER_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Gender',
        required=False,
    )
    manager = forms.ModelChoiceField(
        queryset=UserProfile.objects.filter(role='manager', user__is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Manager'
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):  # Pre-fill role, gender, manager from existing profile
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            try:
                self.fields['role'].initial = self.instance.profile.role
                self.fields['gender'].initial = self.instance.profile.gender
                if self.instance.profile.manager:
                    self.fields['manager'].initial = self.instance.profile.manager
            except:
                pass

    def clean_username(self):  # Reject duplicate usernames (exclude current user)
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean(self):  # Validate password match if a new password is provided
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('confirm_password')
        if password and confirm and password != confirm:
            raise forms.ValidationError('Passwords do not match.')
        if password and not confirm:
            raise forms.ValidationError('Please confirm the new password.')
        return cleaned

    def save(self, commit=True):  # Update User and UserProfile, track manager changes
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            role = self.cleaned_data.get('role', 'employee')
            gender = self.cleaned_data.get('gender', '')
            manager_profile = self.cleaned_data.get('manager')
            defaults = {'role': role, 'gender': gender}
            old_manager = user.profile.manager
            if manager_profile != old_manager:  # Manager changed; update assignment timestamp
                defaults['manager'] = manager_profile
                defaults['manager_assigned_at'] = timezone.now()
            else:
                defaults['manager'] = manager_profile
            UserProfile.objects.update_or_create(
                user=user,
                defaults=defaults,
            )
        return user
