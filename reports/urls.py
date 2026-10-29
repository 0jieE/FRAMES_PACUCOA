from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("faculty-summary/", views.faculty_summary, name="faculty_summary"),
    path("matrix/", views.matrix, name="matrix"),
    path("missing/", views.missing, name="missing"),
    path("expiring/", views.expiring, name="expiring"),
    path("audit-summary/", views.audit_summary, name="audit_summary"),
]
