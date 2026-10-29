from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import UserCreateForm
from accounts.mixins import faculty_required, manager_required, staff_required
from accounts.services import create_user_from_form
from audit.models import AuditLog
from audit.utils import log_action
from compliance.engine import faculty_summary, rates_by_faculty
from compliance.models import ComplianceStatus
from compliance.queries import filter_faculty_by_compliance
from documents.models import Document
from frames_project.utils import paginate

from .forms import ContactForm, DepartmentForm, FacultyForm, FacultySearchForm
from .models import Department, Faculty


@staff_required
def faculty_list(request):
    form = FacultySearchForm(request.GET or None, user=request.user)
    qs = Faculty.objects.visible_to(request.user).select_related("department", "user")
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            q = data["q"]
            qs = qs.filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(middle_name__icontains=q) | Q(employee_no__icontains=q)
            )
        if data["department"]:
            qs = qs.filter(department=data["department"])
        if data["rank"]:
            qs = qs.filter(academic_rank=data["rank"])
        if data["employment_status"]:
            qs = qs.filter(employment_status=data["employment_status"])
        if data["highest_degree"]:
            qs = qs.filter(highest_degree=data["highest_degree"])
        qs = filter_faculty_by_compliance(qs, data["compliance"])
    qs = qs.order_by("last_name", "first_name")
    page_obj = paginate(request, qs, 15)
    rates = rates_by_faculty(ComplianceStatus.objects.filter(faculty__in=[f.pk for f in page_obj]))
    for f in page_obj:
        f.rate_info = rates.get(f.pk, {"total": 0, "complied": 0, "rate": 0.0})
    return render(request, "faculty/faculty_list.html", {"form": form, "page_obj": page_obj, "total": qs.count()})


@login_required
def faculty_detail(request, pk):
    faculty = get_object_or_404(Faculty.objects.visible_to(request.user).select_related("department", "user"), pk=pk)
    summary = faculty_summary(faculty)
    recent_documents = Document.objects.filter(faculty=faculty).select_related("requirement")[:8]
    return render(
        request,
        "faculty/faculty_detail.html",
        {
            "faculty": faculty,
            "summary": summary,
            "recent_documents": recent_documents,
            "is_own_profile": faculty.user_id == request.user.pk,
        },
    )


@faculty_required
def my_profile(request):
    faculty = getattr(request.user, "faculty", None)
    if faculty is None:
        messages.error(request, "Your account has no faculty profile yet. Please contact HR.")
        return render(request, "accounts/no_role.html")
    return redirect("faculty:detail", pk=faculty.pk)


@login_required
def faculty_edit(request, pk):
    faculty = get_object_or_404(Faculty.objects.visible_to(request.user), pk=pk)
    user = request.user
    if user.can_manage_faculty:
        form = FacultyForm(request.POST or None, instance=faculty)
        if request.method == "POST" and form.is_valid():
            changed = form.changed_data
            faculty = form.save()
            account = faculty.user
            account.first_name, account.last_name = faculty.first_name, faculty.last_name
            account.save(update_fields=["first_name", "last_name"])
            log_action(user, AuditLog.Action.PROFILE_CHANGE, obj=faculty, details={"faculty": faculty.full_name, "changed": changed})
            messages.success(request, "Faculty profile updated. Compliance was re-evaluated.")
            return redirect(faculty)
        full_edit = True
    elif faculty.user_id == user.pk:
        form = ContactForm(request.POST or None, initial={"contact_no": faculty.contact_no, "email": user.email})
        if request.method == "POST" and form.is_valid():
            faculty.contact_no = form.cleaned_data["contact_no"]
            faculty.save(update_fields=["contact_no"])
            user.email = form.cleaned_data["email"]
            user.save(update_fields=["email"])
            log_action(user, AuditLog.Action.PROFILE_CHANGE, obj=faculty, details={"changed": form.changed_data})
            messages.success(request, "Contact information updated.")
            return redirect(faculty)
        full_edit = False
    else:
        raise PermissionDenied("You cannot edit this profile.")
    return render(request, "faculty/faculty_form.html", {"form": form, "faculty": faculty, "full_edit": full_edit})


@manager_required
def faculty_create(request):
    form = UserCreateForm(request.POST or None, force_faculty=True)
    if request.method == "POST" and form.is_valid():
        account = create_user_from_form(form)
        log_action(
            request.user,
            AuditLog.Action.USER_CHANGE,
            obj=account,
            details={"event": "created faculty", "username": account.username, "employee_no": account.faculty.employee_no},
        )
        messages.success(request, f"Faculty {account.faculty.full_name} created (login: {account.username}).")
        return redirect(account.faculty)
    return render(request, "accounts/user_form.html", {"form": form, "title": "New faculty member", "is_create": True})


# ---------------------------------------------------------------- departments
@staff_required
def department_list(request):
    departments = Department.objects.annotate(faculty_count=Count("faculty"))
    return render(request, "faculty/department_list.html", {"departments": departments})


@manager_required
def department_form(request, pk=None):
    department = get_object_or_404(Department, pk=pk) if pk else None
    form = DepartmentForm(request.POST or None, instance=department)
    if request.method == "POST" and form.is_valid():
        department = form.save()
        log_action(request.user, AuditLog.Action.RULE_CHANGE, obj=department, details={"event": "department saved", "code": department.code})
        messages.success(request, f"Department {department.code} saved.")
        return redirect("faculty:department_list")
    return render(request, "faculty/department_form.html", {"form": form, "department": department})
