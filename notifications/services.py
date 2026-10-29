"""Create in-app notifications and (optionally) send the matching email."""
import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger(__name__)


def notify(user, message, type=Notification.Type.SYSTEM, link="", email=False, subject=None):
    notification = Notification.objects.create(user=user, type=type, message=message, link=link)
    if email and user.email:
        body = message
        if link:
            body += f"\n\nOpen FRAMES: {settings.SITE_URL.rstrip('/')}{link}"
        body += f"\n\n— {settings.SCHOOL_NAME} FRAMES"
        try:
            send_mail(
                subject or f"[FRAMES] {notification.get_type_display()}",
                body,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Exception:  # email problems must never break the workflow
            logger.exception("Could not send notification email to %s", user.email)
    return notification


def notify_many(users, message, **kwargs):
    return [notify(user, message, **kwargs) for user in users]
