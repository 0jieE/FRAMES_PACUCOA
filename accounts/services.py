"""User account workflows."""
from django.db import transaction

from faculty.models import Faculty

from .models import User


@transaction.atomic
def create_user_from_form(form):
    """Create the user from a valid ``UserCreateForm``; FACULTY users also get a Faculty profile."""
    data = form.cleaned_data
    user = form.save(commit=False)
    if form.fields["role"].disabled:
        user.role = User.Role.FACULTY
    user.department = data.get("department")
    user.set_password(data["password1"])
    user.save()
    if user.role == User.Role.FACULTY:
        Faculty.objects.create(
            user=user,
            department=data["faculty_department"],
            employee_no=data["employee_no"],
            last_name=user.last_name,
            first_name=user.first_name,
            middle_name=data.get("middle_name", ""),
            sex=data["sex"],
            employment_status=data["employment_status"],
            faculty_type=data["faculty_type"],
            academic_rank=data["academic_rank"],
            highest_degree=data["highest_degree"],
            has_foreign_degree=data.get("has_foreign_degree", False),
            teaches_licensure_program=data.get("teaches_licensure_program", False),
            on_study_leave=data.get("on_study_leave", False),
            date_hired=data["date_hired"],
            contact_no=data.get("contact_no", ""),
        )
    return user
