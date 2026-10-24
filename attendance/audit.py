from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from .models import AuditLog


def audit_log(actor, action, action_detail='', target=None, metadata=None, request=None):
    """Create an audit log entry."""
    ct = None
    obj_id = None
    target_repr = ''
    # Resolve content type and ID for the target object
    if target is not None:
        ct = ContentType.objects.get_for_model(target)
        obj_id = target.pk
        target_repr = str(target)[:255]
    ip = None
    # Extract client IP from request if available
    if request:
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = (xff.split(',')[0] if xff else request.META.get('REMOTE_ADDR')) or None
    AuditLog.objects.create(
        actor=actor,
        action=action,
        action_detail=str(action_detail)[:500],
        target_type=ct,
        target_id=obj_id,
        target_repr=target_repr,
        metadata=metadata or {},
        ip_address=ip,
    )


def log_create(actor, obj, detail='', request=None):  # Log a create action
    audit_log(actor, 'create', detail or f'Created {type(obj).__name__}: {obj}', obj, request=request)


def log_update(actor, obj, detail='', changes=None, request=None):  # Log an update action with optional changes dict
    audit_log(actor, 'update', detail or f'Updated {type(obj).__name__}: {obj}', obj, {'changes': changes} if changes else {}, request=request)


def log_delete(actor, obj, detail='', request=None):  # Log a delete action
    audit_log(actor, 'delete', detail or f'Deleted {type(obj).__name__}: {obj}', obj, request=request)
