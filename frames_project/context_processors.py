from django.conf import settings


def school(request):
    return {
        "SCHOOL_NAME": settings.SCHOOL_NAME,
        "SYSTEM_NAME": settings.SYSTEM_NAME,
        "SYSTEM_FULL_NAME": settings.SYSTEM_FULL_NAME,
    }
