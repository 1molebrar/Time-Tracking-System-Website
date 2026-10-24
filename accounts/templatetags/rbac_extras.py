from django import template
from django.template.defaulttags import register

register = template.Library()  # Custom template tags for RBAC checks in templates


@register.filter
def has_perm(user, codename):  # Check if user has a specific permission codename
    return user.is_authenticated and (user.has_perm(f'attendance.{codename}') or user.has_perm(f'accounts.{codename}'))


@register.filter
def get_item(d, key):  # Get an item from a dictionary by key
    return d.get(key)


@register.simple_tag(takes_context=True)
def if_role(context, *roles):  # Check if the current user's role matches any of the given roles
    request = context.get('request')
    if request and request.user.is_authenticated:
        try:
            return request.user.profile.role in roles
        except AttributeError:
            pass
    return False


@register.simple_tag(takes_context=True)
def role_include(context, template_name):  # Load a role-specific template (e.g. admin_nav.html)
    request = context.get('request')
    if request and request.user.is_authenticated:
        try:
            role = request.user.profile.role
            return template.loader.render_to_string(
                f'{role}_{template_name}',
                context.flatten(),
                request=request,
            )
        except Exception:
            pass
    return ''
