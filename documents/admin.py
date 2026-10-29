from django.contrib import admin

from .models import Document, Validation


class ValidationInline(admin.TabularInline):
    model = Validation
    extra = 0
    readonly_fields = ("validated_by", "decision", "remarks", "validated_at")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("faculty", "requirement", "version_no", "is_current", "status", "expiry_date", "uploaded_at")
    list_filter = ("status", "is_current", "requirement__subarea")
    search_fields = ("faculty__last_name", "faculty__first_name", "requirement__name")
    exclude = ("file",)  # encrypted private file: download through FRAMES, never via a public URL
    readonly_fields = ("original_filename", "file_type", "file_size")
    inlines = [ValidationInline]


@admin.register(Validation)
class ValidationAdmin(admin.ModelAdmin):
    list_display = ("document", "decision", "validated_by", "validated_at")
    list_filter = ("decision",)
