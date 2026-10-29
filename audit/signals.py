"""Audit login, logout, and failed login attempts."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import AuditLog
from .utils import log_action


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    log_action(user, AuditLog.Action.LOGIN, obj=user, request=request, details={"role": user.role})


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    if user is not None:
        log_action(user, AuditLog.Action.LOGOUT, obj=user, request=request)


@receiver(user_login_failed)
def audit_login_failed(sender, credentials, request=None, **kwargs):
    log_action(
        None,
        AuditLog.Action.LOGIN_FAILED,
        request=request,
        model_name="User",
        details={"username": credentials.get("username", "")},
    )
