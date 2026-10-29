"""Audit log of user actions."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        LOGIN_FAILED = "LOGIN_FAILED", "Failed login"
        PASSWORD_CHANGE = "PASSWORD_CHANGE", "Password change"
        UPLOAD = "UPLOAD", "Document upload"
        DOWNLOAD = "DOWNLOAD", "Document download"
        PREVIEW = "PREVIEW", "Document preview"
        VALIDATE = "VALIDATE", "Document validation"
        RULE_CHANGE = "RULE_CHANGE", "Requirement rule change"
        USER_CHANGE = "USER_CHANGE", "User change"
        PROFILE_CHANGE = "PROFILE_CHANGE", "Profile change"
        REPORT = "REPORT", "Report generated"
        EXPIRY_CHECK = "EXPIRY_CHECK", "Expiry check"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user or 'system'} {self.action}"

    @property
    def summary(self):
        if not self.details:
            return ""
        return "; ".join(f"{k}: {v}" for k, v in self.details.items())
