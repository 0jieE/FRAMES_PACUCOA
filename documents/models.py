"""Uploads, versions, validation workflow, encrypted storage, protected download."""
import os
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from faculty.models import Faculty

from .storage import get_private_storage


def document_upload_path(instance, filename):
    """Opaque on-disk name; the original filename is kept only in the database."""
    return f"documents/{instance.faculty_id}/{uuid.uuid4().hex}.enc"


class StoredFile(models.Model):
    """Encrypted file bytes when PRIVATE_STORAGE = "database" (see documents/storage.py)."""

    name = models.CharField(max_length=255, unique=True)
    data = models.BinaryField()
    size = models.PositiveIntegerField(help_text="Encrypted size in bytes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DocumentQuerySet(models.QuerySet):
    def visible_to(self, user):
        return self.filter(faculty__in=Faculty.objects.visible_to(user))

    def current(self):
        return self.filter(is_current=True)


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending validation"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        RESUBMIT = "RESUBMIT", "Re-submission requested"

    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="documents")
    requirement = models.ForeignKey("requirements.Requirement", on_delete=models.PROTECT, related_name="documents")
    file = models.FileField(upload_to=document_upload_path, storage=get_private_storage, max_length=255)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100, help_text="MIME type")
    file_size = models.PositiveIntegerField(default=0)
    date_issued = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    version_no = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="uploads"
    )
    uploaded_at = models.DateTimeField(default=timezone.now)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["faculty", "requirement", "is_current"]),
            models.Index(fields=["status", "is_current"]),
        ]

    def __str__(self):
        return f"{self.requirement.name} v{self.version_no} — {self.faculty}"

    def get_absolute_url(self):
        return reverse("documents:detail", args=[self.pk])

    @property
    def extension(self):
        return os.path.splitext(self.original_filename)[1].lower()

    @property
    def is_pdf(self):
        return self.file_type == "application/pdf"

    @property
    def is_image(self):
        return self.file_type.startswith("image/")

    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.localdate()).days

    @property
    def is_expired(self):
        days = self.days_to_expiry
        return days is not None and days < 0

    def versions(self):
        return Document.objects.filter(faculty_id=self.faculty_id, requirement_id=self.requirement_id).order_by(
            "-version_no"
        )


class Validation(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "APPROVED", "Approve"
        REJECTED = "REJECTED", "Reject"
        RESUBMIT = "RESUBMIT", "Request re-submission"

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="validations")
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="validations"
    )
    decision = models.CharField(max_length=10, choices=Decision.choices)
    remarks = models.TextField(blank=True)
    validated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-validated_at"]

    def __str__(self):
        return f"{self.get_decision_display()} by {self.validated_by} on {self.validated_at:%Y-%m-%d}"
