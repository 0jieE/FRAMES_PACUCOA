from django.contrib import admin

from .models import PacucoaSubArea, Requirement


class RequirementInline(admin.TabularInline):
    model = Requirement
    extra = 0


@admin.register(PacucoaSubArea)
class SubAreaAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "sort_order")
    inlines = [RequirementInline]


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = ("name", "subarea", "applicability", "is_mandatory", "has_expiry", "is_active")
    list_filter = ("subarea", "applicability", "has_expiry", "is_active")
