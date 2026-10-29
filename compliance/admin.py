from django.contrib import admin

from .models import ComplianceStatus, ExpiryAlertSent


@admin.register(ComplianceStatus)
class ComplianceStatusAdmin(admin.ModelAdmin):
    list_display = ("faculty", "requirement", "status", "is_expiring", "days_to_expiry", "evaluated_at")
    list_filter = ("status", "is_expiring", "requirement__subarea")


@admin.register(ExpiryAlertSent)
class ExpiryAlertSentAdmin(admin.ModelAdmin):
    list_display = ("document", "threshold", "sent_at")
