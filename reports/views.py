from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.mixins import staff_required
from audit.models import AuditLog
from audit.utils import log_action
from faculty.models import Faculty

from . import builders
from .excel import render_xlsx
from .forms import DepartmentReportForm, ExpiringReportForm, FacultyReportForm, MissingReportForm
from .pdf import render_pdf

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _respond(request, report, fmt):
    fmt = fmt if fmt in CONTENT_TYPES else "pdf"
    data = render_pdf(report) if fmt == "pdf" else render_xlsx(report)
    log_action(
        request.user,
        AuditLog.Action.REPORT,
        model_name="Report",
        details={"report": report.title, "format": fmt, "filters": {k: str(v) for k, v in report.filters}},
    )
    response = HttpResponse(data, content_type=CONTENT_TYPES[fmt])
    response["Content-Disposition"] = f'attachment; filename="{report.filename(fmt)}"'
    return response


def _forms(user, data=None):
    return {
        "faculty_form": FacultyReportForm(data, user=user, prefix="fs"),
        "matrix_form": DepartmentReportForm(data, user=user, prefix="mx"),
        "missing_form": MissingReportForm(data, user=user, prefix="ms"),
        "expiring_form": ExpiringReportForm(data, user=user, prefix="ex"),
        "audit_form": DepartmentReportForm(data, user=user, prefix="au"),
    }


@staff_required
def index(request):
    return render(request, "reports/index.html", _forms(request.user))


def _invalid(request):
    messages.error(request, "Please check the report filters.")
    return redirect("reports:index")


@login_required
def faculty_summary(request):
    """Staff pick any faculty in scope; faculty members may export their own summary."""
    user = request.user
    if user.is_faculty:
        faculty = get_object_or_404(Faculty, user=user)
        return _respond(request, builders.faculty_summary_report(user, faculty), request.GET.get("format", "pdf"))
    if not user.is_staff_role:
        return redirect("accounts:home")
    form = FacultyReportForm(request.GET, user=user, prefix="fs")
    if not form.is_valid():
        return _invalid(request)
    return _respond(request, builders.faculty_summary_report(user, form.cleaned_data["faculty"]), form.cleaned_data["format"])


@staff_required
def matrix(request):
    form = DepartmentReportForm(request.GET, user=request.user, prefix="mx")
    if not form.is_valid():
        return _invalid(request)
    return _respond(request, builders.matrix_report(request.user, form.cleaned_data["department"]), form.cleaned_data["format"])


@staff_required
def missing(request):
    form = MissingReportForm(request.GET, user=request.user, prefix="ms")
    if not form.is_valid():
        return _invalid(request)
    data = form.cleaned_data
    return _respond(request, builders.missing_report(request.user, data["department"], data["subarea"]), data["format"])


@staff_required
def expiring(request):
    form = ExpiringReportForm(request.GET, user=request.user, prefix="ex")
    if not form.is_valid():
        return _invalid(request)
    data = form.cleaned_data
    return _respond(request, builders.expiring_report(request.user, data["window"], data["department"]), data["format"])


@staff_required
def audit_summary(request):
    form = DepartmentReportForm(request.GET, user=request.user, prefix="au")
    if not form.is_valid():
        return _invalid(request)
    return _respond(request, builders.audit_summary_report(request.user, form.cleaned_data["department"]), form.cleaned_data["format"])
