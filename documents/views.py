from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.clickjacking import xframe_options_sameorigin

from accounts.mixins import faculty_required, role_required, validator_required
from accounts.models import STAFF_ROLES
from audit.models import AuditLog
from audit.utils import log_action
from compliance.models import ComplianceStatus
from frames_project.utils import paginate

from .forms import DocumentFilterForm, UploadForm, ValidationForm
from .models import Document, Validation
from .services import upload_document, validate_document
from .storage import private_storage


def _filtered_documents(request, queryset, form):
    if form.is_valid():
        data = form.cleaned_data
        if data.get("q"):
            q = data["q"]
            queryset = queryset.filter(
                Q(faculty__first_name__icontains=q)
                | Q(faculty__last_name__icontains=q)
                | Q(faculty__employee_no__icontains=q)
                | Q(requirement__name__icontains=q)
            )
        if data.get("department"):
            queryset = queryset.filter(faculty__department=data["department"])
        if data.get("subarea"):
            queryset = queryset.filter(requirement__subarea=data["subarea"])
        if data.get("status"):
            queryset = queryset.filter(status=data["status"])
        if not data.get("history"):
            queryset = queryset.filter(is_current=True)
    else:
        queryset = queryset.filter(is_current=True)
    return queryset


@login_required
def document_list(request):
    form = DocumentFilterForm(request.GET or None, user=request.user)
    qs = Document.objects.visible_to(request.user).select_related("faculty__department", "requirement__subarea")
    qs = _filtered_documents(request, qs, form)
    return render(request, "documents/document_list.html", {"form": form, "page_obj": paginate(request, qs, 20)})


@faculty_required
def upload(request):
    faculty = getattr(request.user, "faculty", None)
    if faculty is None:
        messages.error(request, "Your account has no faculty profile. Please contact HR.")
        return redirect("accounts:home")
    initial = {}
    requirement_id = request.GET.get("requirement")
    if requirement_id and requirement_id.isdigit():
        initial["requirement"] = requirement_id
    form = UploadForm(request.POST or None, request.FILES or None, faculty=faculty, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        document = upload_document(
            faculty=faculty,
            requirement=data["requirement"],
            uploaded_file=data["file"],
            file_type=form.file_type,
            date_issued=data["date_issued"],
            expiry_date=data["expiry_date"],
            user=request.user,
        )
        messages.success(
            request, f"'{document.requirement.name}' uploaded as version {document.version_no}. It is now pending validation."
        )
        return redirect(document)

    selected = None
    if form.is_bound:
        selected = form.cleaned_data.get("requirement")
    elif requirement_id and requirement_id.isdigit():
        selected = form.fields["requirement"].queryset.filter(pk=requirement_id).first()
    history = []
    if selected:
        history = Document.objects.filter(faculty=faculty, requirement=selected).order_by("-version_no")
    expiry_ids = list(form.fields["requirement"].queryset.filter(has_expiry=True).values_list("pk", flat=True))
    return render(
        request,
        "documents/upload.html",
        {"form": form, "selected": selected, "history": history, "expiry_requirement_ids": expiry_ids},
    )


@login_required
def document_detail(request, pk):
    document = get_object_or_404(
        Document.objects.visible_to(request.user).select_related("faculty__department", "faculty__user", "requirement__subarea"),
        pk=pk,
    )
    versions = document.versions().prefetch_related("validations__validated_by")
    compliance = ComplianceStatus.objects.filter(faculty=document.faculty, requirement=document.requirement).first()
    return render(
        request,
        "documents/document_detail.html",
        {
            "document": document,
            "versions": versions,
            "compliance": compliance,
            "can_validate": request.user.can_validate and document.status == Document.Status.PENDING and document.is_current,
            "is_owner": document.faculty.user_id == request.user.pk,
        },
    )


def _serve(request, pk, inline):
    document = get_object_or_404(Document.objects.visible_to(request.user).select_related("faculty", "requirement"), pk=pk)
    if not document.file:
        raise Http404("This document has no stored file.")
    try:
        data = private_storage.read_decrypted(document.file.name)
    except (FileNotFoundError, ValueError) as exc:
        raise Http404("The stored file is missing or cannot be decrypted.") from exc
    log_action(
        request.user,
        AuditLog.Action.PREVIEW if inline else AuditLog.Action.DOWNLOAD,
        obj=document,
        details={"faculty": document.faculty.full_name, "requirement": document.requirement.name, "version": document.version_no},
    )
    response = HttpResponse(data, content_type=document.file_type or "application/octet-stream")
    response["Content-Disposition"] = content_disposition_header(not inline, document.original_filename)
    response["Content-Length"] = str(len(data))
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@xframe_options_sameorigin
def document_preview(request, pk):
    return _serve(request, pk, inline=True)


@login_required
def document_download(request, pk):
    return _serve(request, pk, inline=False)


@role_required(*STAFF_ROLES)
def validation_queue(request):
    form = DocumentFilterForm(request.GET or None, user=request.user, show_status=False)
    qs = (
        Document.objects.visible_to(request.user)
        .filter(is_current=True, status=Document.Status.PENDING)
        .select_related("faculty__department", "requirement__subarea")
        .order_by("uploaded_at")
    )
    qs = _filtered_documents(request, qs, form).filter(is_current=True)
    return render(request, "documents/validation_queue.html", {"form": form, "page_obj": paginate(request, qs, 20)})


@validator_required
def validate(request, pk):
    document = get_object_or_404(
        Document.objects.visible_to(request.user).select_related("faculty__department", "requirement__subarea"), pk=pk
    )
    if document.status != Document.Status.PENDING or not document.is_current:
        messages.info(request, "This document is no longer pending validation.")
        return redirect(document)
    form = ValidationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        decision = form.cleaned_data["decision"]
        validate_document(document=document, user=request.user, decision=decision, remarks=form.cleaned_data["remarks"].strip())
        messages.success(
            request, f"{document.faculty.full_name} — '{document.requirement.name}': {Validation.Decision(decision).label}. Faculty notified."
        )
        return redirect("documents:validation_queue")
    history = document.versions().exclude(pk=document.pk).prefetch_related("validations__validated_by")
    return render(
        request,
        "documents/validate.html",
        {"document": document, "form": form, "history": history, "requirement": document.requirement},
    )
