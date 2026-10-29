"""log_action(user, action, obj, details, request) helper."""
from frames_project.utils import client_ip

from .middleware import get_current_request
from .models import AuditLog


def log_action(user, action, obj=None, details=None, request=None, model_name="", object_id=""):
    """Record an audit entry. ``request`` defaults to the current request (for the IP)."""
    request = request or get_current_request()
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    if obj is not None:
        model_name = model_name or obj.__class__.__name__
        object_id = object_id or str(obj.pk)
    return AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=str(object_id or ""),
        details=details or {},
        ip_address=client_ip(request),
    )
