"""Compliance status per (faculty, requirement) and expiry-alert bookkeeping."""
from django.db import models


class ComplianceStatus(models.Model):
    class Status(models.TextChoices):
        COMPLIED = "COMPLIED", "Complied"
        INCOMPLETE = "INCOMPLETE", "Incomplete"
        NOT_COMPLIED = "NOT_COMPLIED", "Not Complied"

    faculty = models.ForeignKey("faculty.Faculty", on_delete=models.CASCADE, related_name="compliance_statuses")
    requirement = models.ForeignKey(
        "requirements.Requirement", on_delete=models.CASCADE, related_name="compliance_statuses"
    )
    document = models.ForeignKey(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=15, choices=Status.choices)
    is_expiring = models.BooleanField(default=False)
    days_to_expiry = models.IntegerField(null=True, blank=True)
    evaluated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["faculty", "requirement"], name="unique_compliance_per_requirement")
        ]
        verbose_name_plural = "compliance statuses"

    def __str__(self):
        return f"{self.faculty} · {self.requirement.name}: {self.get_status_display()}"

    @property
    def is_expired(self):
        return self.days_to_expiry is not None and self.days_to_expiry < 0


class ExpiryAlertSent(models.Model):
    """One row per (document, threshold) so each expiry alert is sent only once."""

    EXPIRED = 0
    THRESHOLD_CHOICES = [(90, "90 days"), (60, "60 days"), (30, "30 days"), (EXPIRED, "Expired")]

    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE, related_name="expiry_alerts")
    threshold = models.PositiveSmallIntegerField(choices=THRESHOLD_CHOICES)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "threshold"], name="unique_alert_per_threshold")]

    def __str__(self):
        return f"{self.document_id} @ {self.get_threshold_display()}"
