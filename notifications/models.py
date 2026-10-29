"""In-app and email notifications."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Type(models.TextChoices):
        UPLOAD = "UPLOAD", "New upload"
        VALIDATION = "VALIDATION", "Validation result"
        EXPIRY = "EXPIRY", "Expiry alert"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.SYSTEM)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.message[:50]}"

    @property
    def icon(self):
        return {
            self.Type.UPLOAD: "bi-cloud-arrow-up",
            self.Type.VALIDATION: "bi-patch-check",
            self.Type.EXPIRY: "bi-clock-history",
        }.get(self.type, "bi-info-circle")
