"""Unread notification count for the navbar bell."""


def notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    unread = user.notifications.filter(is_read=False)
    return {
        "unread_notification_count": unread.count(),
        "recent_notifications": unread[:5],
    }
