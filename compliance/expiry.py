"""Expiry tracking: 90/60/30-day alerts (sent once per threshold) and expired notices."""
from dataclasses import dataclass, field

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from audit.utils import log_action
from documents.models import Document
from notifications.models import Notification
from notifications.services import notify

from .engine import evaluate_all
from .models import ExpiryAlertSent


@dataclass
class ExpiryRunResult:
    evaluated: int = 0
    alerts: dict = field(default_factory=dict)  # threshold -> count
    expired_notices: int = 0

    @property
    def total_alerts(self):
        return sum(self.alerts.values()) + self.expired_notices


def expiring_documents(today=None):
    """Current, approved documents of active expiring requirements that have an expiry date."""
    return Document.objects.filter(
        is_current=True,
        status=Document.Status.APPROVED,
        requirement__has_expiry=True,
        requirement__is_active=True,
        expiry_date__isnull=False,
    ).select_related("faculty__user", "faculty__department", "requirement")


def check_expirations(today=None, send_email=True):
    """Re-evaluate everything, then send each due alert exactly once.

    A document only gets the alert for the *tightest* threshold it currently falls
    under (e.g. 20 days left -> the 30-day alert); the wider thresholds are marked
    as sent too, so a late first run never sends three alerts at once.
    """
    today = today or timezone.localdate()
    result = ExpiryRunResult(evaluated=evaluate_all(today=today))
    thresholds = sorted(settings.EXPIRY_ALERT_DAYS)  # [30, 60, 90]
    sent = set(ExpiryAlertSent.objects.values_list("document_id", "threshold"))

    for doc in expiring_documents(today):
        days = (doc.expiry_date - today).days
        link = reverse("documents:detail", args=[doc.pk])
        user = doc.faculty.user
        if days < 0:
            if (doc.pk, ExpiryAlertSent.EXPIRED) in sent:
                continue
            ExpiryAlertSent.objects.get_or_create(document=doc, threshold=ExpiryAlertSent.EXPIRED)
            notify(
                user,
                f"Your '{doc.requirement.name}' EXPIRED on {doc.expiry_date:%b %d, %Y}. "
                "It is now counted as Not Complied — please upload a renewed copy.",
                type=Notification.Type.EXPIRY,
                link=reverse("documents:upload") + f"?requirement={doc.requirement_id}",
                email=send_email,
                subject=f"[FRAMES] Expired: {doc.requirement.name}",
            )
            result.expired_notices += 1
            continue
        due = next((t for t in thresholds if days <= t), None)
        if due is None or (doc.pk, due) in sent:
            continue
        for t in thresholds:
            if t >= due:
                ExpiryAlertSent.objects.get_or_create(document=doc, threshold=t)
        notify(
            user,
            f"Your '{doc.requirement.name}' expires in {days} day{'s' if days != 1 else ''} "
            f"({doc.expiry_date:%b %d, %Y}). Please prepare a renewed copy.",
            type=Notification.Type.EXPIRY,
            link=link,
            email=send_email,
            subject=f"[FRAMES] {due}-day expiry alert: {doc.requirement.name}",
        )
        result.alerts[due] = result.alerts.get(due, 0) + 1

    if result.total_alerts:
        summary = ", ".join(f"{n} at {t} days" for t, n in sorted(result.alerts.items()))
        parts = [p for p in (summary, f"{result.expired_notices} expired" if result.expired_notices else "") if p]
        for hr in User.objects.filter(role=User.Role.HR_ADMIN, is_active=True):
            notify(
                hr,
                f"Expiry check: {result.total_alerts} new alert(s) sent ({'; '.join(parts)}).",
                type=Notification.Type.EXPIRY,
                link=reverse("compliance:expiring"),
            )
    log_action(
        None,
        AuditLog.Action.EXPIRY_CHECK,
        model_name="Document",
        details={"evaluated": result.evaluated, "alerts": {str(k): v for k, v in result.alerts.items()}, "expired": result.expired_notices},
    )
    return result
