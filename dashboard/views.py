"""Executive analytics dashboard."""
from django.db.models import Count, F, Q
from django.shortcuts import render
from django.utils import timezone

from accounts.mixins import staff_required
from compliance.engine import compliance_rate, rates_by_department, rates_by_subarea
from compliance.models import ComplianceStatus
from compliance.queries import department_choice_for, scoped_faculty
from documents.models import Document
from faculty.models import Department

Status = ComplianceStatus.Status


def dashboard_data(user, department=None):
    today = timezone.localdate()
    faculty_qs = scoped_faculty(user, department)
    statuses = ComplianceStatus.objects.filter(faculty__in=faculty_qs)

    fully_compliant = (
        faculty_qs.annotate(
            _total=Count("compliance_statuses"),
            _complied=Count("compliance_statuses", filter=Q(compliance_statuses__status=Status.COMPLIED)),
        )
        .filter(_total__gt=0, _complied=F("_total"))
        .count()
    )
    docs = Document.objects.filter(faculty__in=faculty_qs, is_current=True)
    expired_qs = statuses.filter(
        status=Status.NOT_COMPLIED, days_to_expiry__lt=0, document__status=Document.Status.APPROVED
    )
    kpis = {
        "overall_rate": compliance_rate(statuses),
        "faculty_count": faculty_qs.count(),
        "fully_compliant": fully_compliant,
        "pending_validations": docs.filter(status=Document.Status.PENDING).count(),
        "expiring_90": statuses.filter(is_expiring=True).count(),
        "expired": expired_qs.count(),
    }
    status_counts = statuses.aggregate(
        complied=Count("pk", filter=Q(status=Status.COMPLIED, is_expiring=False)),
        expiring=Count("pk", filter=Q(status=Status.COMPLIED, is_expiring=True)),
        incomplete=Count("pk", filter=Q(status=Status.INCOMPLETE)),
        not_complied=Count("pk", filter=Q(status=Status.NOT_COMPLIED)),
    )
    most_missing = (
        statuses.values("requirement__subarea__code", "requirement__name")
        .annotate(
            applicable=Count("pk"),
            not_complied=Count("pk", filter=Q(status=Status.NOT_COMPLIED)),
            incomplete=Count("pk", filter=Q(status=Status.INCOMPLETE)),
        )
        .filter(not_complied__gt=0)
        .order_by("-not_complied", "-incomplete", "requirement__subarea__code")[:10]
    )
    for row in most_missing:
        row["missing_rate"] = round(row["not_complied"] / row["applicable"] * 100, 1) if row["applicable"] else 0
    soonest = (
        statuses.filter(is_expiring=True)
        .select_related("faculty__department", "requirement__subarea", "document")
        .order_by("days_to_expiry")[:10]
    )
    subareas = rates_by_subarea(statuses)
    departments = rates_by_department(statuses)
    charts = {
        "subarea": {"labels": [f"{s['code']} {s['title']}" for s in subareas], "short": [s["code"] for s in subareas], "rates": [s["rate"] for s in subareas]},
        "department": {"labels": [d["code"] for d in departments], "names": [d["name"] for d in departments], "rates": [d["rate"] for d in departments]},
        "status": {
            "labels": ["Complied", "Complied (expiring)", "Incomplete", "Not Complied"],
            "values": [status_counts["complied"], status_counts["expiring"], status_counts["incomplete"], status_counts["not_complied"]],
        },
    }
    return {
        "kpis": kpis,
        "status_counts": status_counts,
        "most_missing": most_missing,
        "soonest": soonest,
        "subarea_rates": subareas,
        "department_rates": departments,
        "charts": charts,
        "today": today,
    }


@staff_required
def index(request):
    department = department_choice_for(request.user, request.GET.get("department"))
    context = dashboard_data(request.user, department)
    context.update(
        {
            "selected_department": department,
            "departments": Department.objects.all() if not request.user.scope_department else [request.user.scope_department],
        }
    )
    return render(request, "dashboard/index.html", context)
