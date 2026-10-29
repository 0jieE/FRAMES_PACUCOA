"""Document workflows: versioned upload and validation decisions."""
from django.db import transaction
from django.db.models import Max, Q
from django.urls import reverse

from accounts.models import User
from audit.models import AuditLog
from audit.utils import log_action
from notifications.models import Notification
from notifications.services import notify, notify_many

from .models import Document, Validation


def validators_for(faculty):
    """HR admins plus Area Chairs whose scope covers the faculty's department."""
    return User.objects.filter(is_active=True).filter(
        Q(role=User.Role.HR_ADMIN)
        | Q(role=User.Role.AREA_CHAIR, department__isnull=True)
        | Q(role=User.Role.AREA_CHAIR, department=faculty.department_id)
    )


@transaction.atomic
def upload_document(*, faculty, requirement, uploaded_file, file_type, date_issued, expiry_date, user):
    """Store a new version; previous versions are kept with ``is_current=False``."""
    previous = Document.objects.select_for_update().filter(faculty=faculty, requirement=requirement)
    last_version = previous.aggregate(v=Max("version_no"))["v"] or 0
    previous.filter(is_current=True).update(is_current=False)

    document = Document(
        faculty=faculty,
        requirement=requirement,
        original_filename=uploaded_file.name[:255],
        file_type=file_type,
        file_size=uploaded_file.size,
        date_issued=date_issued,
        expiry_date=expiry_date,
        version_no=last_version + 1,
        is_current=True,
        status=Document.Status.PENDING,
        uploaded_by=user,
    )
    document.file.save(uploaded_file.name, uploaded_file, save=False)
    document.save()  # post_save signal re-evaluates compliance

    log_action(
        user,
        AuditLog.Action.UPLOAD,
        obj=document,
        details={
            "faculty": faculty.full_name,
            "requirement": requirement.name,
            "version": document.version_no,
            "filename": document.original_filename,
        },
    )
    link = reverse("documents:validate", args=[document.pk])
    verb = "re-submitted" if document.version_no > 1 else "uploaded"
    notify_many(
        validators_for(faculty),
        f"{faculty.full_name} ({faculty.department.code}) {verb} '{requirement.name}' (v{document.version_no}).",
        type=Notification.Type.UPLOAD,
        link=link,
    )
    return document


@transaction.atomic
def validate_document(*, document, user, decision, remarks=""):
    validation = Validation.objects.create(document=document, validated_by=user, decision=decision, remarks=remarks)
    document.status = decision
    document.save(update_fields=["status"])  # post_save signal re-evaluates compliance

    log_action(
        user,
        AuditLog.Action.VALIDATE,
        obj=document,
        details={
            "faculty": document.faculty.full_name,
            "requirement": document.requirement.name,
            "version": document.version_no,
            "decision": decision,
            "remarks": remarks,
        },
    )

    label = {
        Validation.Decision.APPROVED: "was APPROVED",
        Validation.Decision.REJECTED: "was REJECTED",
        Validation.Decision.RESUBMIT: "needs RE-SUBMISSION",
    }[decision]
    message = f"Your document '{document.requirement.name}' (v{document.version_no}) {label}."
    if remarks:
        message += f" Remarks: {remarks}"
    notify(
        document.faculty.user,
        message,
        type=Notification.Type.VALIDATION,
        link=reverse("documents:detail", args=[document.pk]),
        email=True,
        subject=f"[FRAMES] Document {label.lower()}: {document.requirement.name}",
    )
    return validation
