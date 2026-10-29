from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("faculty/", include("faculty.urls")),
    path("requirements/", include("requirements.urls")),
    path("documents/", include("documents.urls")),
    path("compliance/", include("compliance.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("reports/", include("reports.urls")),
    path("notifications/", include("notifications.urls")),
    path("audit/", include("audit.urls")),
]
