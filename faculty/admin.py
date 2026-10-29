from django.contrib import admin

from .models import Department, Faculty


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "dean_name")


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ("employee_no", "last_name", "first_name", "department", "employment_status", "academic_rank")
    list_filter = ("department", "employment_status", "faculty_type", "highest_degree")
    search_fields = ("employee_no", "last_name", "first_name")
