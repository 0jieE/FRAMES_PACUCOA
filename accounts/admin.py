from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class FramesUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "department", "is_active")
    list_filter = ("role", "department", "is_active")
    fieldsets = UserAdmin.fieldsets + (("FRAMES", {"fields": ("role", "department")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("FRAMES", {"fields": ("role", "department")}),)
