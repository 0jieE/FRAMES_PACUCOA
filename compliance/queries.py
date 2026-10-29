"""Role-scoped query helpers shared by the matrix, dashboard, faculty list, and reports."""
from django.db.models import Count, F, Q

from faculty.models import Faculty

from .models import ComplianceStatus

Status = ComplianceStatus.Status

COMPLIANCE_FILTER_CHOICES = [
    ("FULL", "Fully compliant"),
    ("INCOMPLETE", "Has incomplete items"),
    ("NOT_COMPLIED", "Has non-complied items"),
    ("EXPIRING", "Has expiring credentials"),
]


def scoped_faculty(user, department=None):
    qs = Faculty.objects.visible_to(user).select_related("department", "user")
    if department:
        qs = qs.filter(department=department)
    return qs


def scoped_statuses(user, department=None):
    return ComplianceStatus.objects.filter(faculty__in=scoped_faculty(user, department))


def filter_faculty_by_compliance(queryset, value):
    """Filter a Faculty queryset by one of COMPLIANCE_FILTER_CHOICES."""
    if not value:
        return queryset
    if value == "FULL":
        return queryset.annotate(
            _total=Count("compliance_statuses"),
            _complied=Count("compliance_statuses", filter=Q(compliance_statuses__status=Status.COMPLIED)),
        ).filter(_total__gt=0, _complied=F("_total"))
    if value == "EXPIRING":
        return queryset.filter(compliance_statuses__is_expiring=True).distinct()
    if value in (Status.INCOMPLETE, Status.NOT_COMPLIED):
        return queryset.filter(compliance_statuses__status=value).distinct()
    return queryset


def requirement_columns(requirements):
    """Group requirements by sub-area and give each a short column code like 'A1'."""
    groups, current, index = [], None, 0
    for req in requirements:
        if current is None or current["subarea"].pk != req.subarea_id:
            current = {"subarea": req.subarea, "columns": []}
            groups.append(current)
            index = 0
        index += 1
        current["columns"].append({"requirement": req, "code": f"{req.subarea.letter}{index}"})
    return groups


def department_choice_for(user, requested_id):
    """Resolve the department filter, forcing an Area Chair's scope."""
    from faculty.models import Department

    if user.scope_department:
        return user.scope_department
    if requested_id and str(requested_id).isdigit():
        return Department.objects.filter(pk=requested_id).first()
    return None
