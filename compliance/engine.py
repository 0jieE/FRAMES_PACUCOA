"""PACUCOA Area II compliance engine: evaluate_faculty, evaluate_all, compliance rates.

Rules, applied to the *current* document of every applicable requirement:

1. no document                          -> NOT_COMPLIED
2. PENDING or RESUBMIT                  -> INCOMPLETE
3. REJECTED                             -> NOT_COMPLIED
4. APPROVED, requirement has no expiry  -> COMPLIED
5. APPROVED, expiry date passed         -> NOT_COMPLIED (expired)
6. APPROVED, expires within 90 days     -> COMPLIED, is_expiring=True
7. APPROVED, expiry > 90 days away      -> COMPLIED

Requirements that do not apply to a faculty member get no ComplianceStatus row,
so they drop out of both numerator and denominator (shown as N/A).
"""
from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from documents.models import Document
from faculty.models import Faculty
from requirements.models import Requirement

from .models import ComplianceStatus

Status = ComplianceStatus.Status


def expiring_window():
    return getattr(settings, "EXPIRING_WINDOW_DAYS", 90)


@dataclass(frozen=True)
class Evaluation:
    status: str
    is_expiring: bool = False
    days_to_expiry: int | None = None


def determine_status(requirement, document, today=None):
    """Pure rule evaluation for one requirement and its current document."""
    today = today or timezone.localdate()
    if document is None:
        return Evaluation(Status.NOT_COMPLIED)
    if document.status in (Document.Status.PENDING, Document.Status.RESUBMIT):
        return Evaluation(Status.INCOMPLETE)
    if document.status == Document.Status.REJECTED:
        return Evaluation(Status.NOT_COMPLIED)
    # APPROVED
    if not requirement.has_expiry or document.expiry_date is None:
        return Evaluation(Status.COMPLIED)
    days = (document.expiry_date - today).days
    if days < 0:
        return Evaluation(Status.NOT_COMPLIED, False, days)
    if days <= expiring_window():
        return Evaluation(Status.COMPLIED, True, days)
    return Evaluation(Status.COMPLIED, False, days)


def active_requirements():
    return list(Requirement.objects.active().ordered())


def applicable_requirements(faculty, requirements=None):
    requirements = active_requirements() if requirements is None else requirements
    return [r for r in requirements if r.applies_to(faculty)]


@transaction.atomic
def evaluate_faculty(faculty, requirements=None, current_documents=None, today=None):
    """(Re)compute and persist ComplianceStatus rows for one faculty member."""
    today = today or timezone.localdate()
    requirements = active_requirements() if requirements is None else requirements
    if current_documents is None:
        current_documents = {
            d.requirement_id: d for d in Document.objects.filter(faculty=faculty, is_current=True).order_by("version_no")
        }
    existing = {cs.requirement_id: cs for cs in ComplianceStatus.objects.filter(faculty=faculty)}

    to_create, to_update, keep_ids = [], [], set()
    for req in requirements:
        if not req.applies_to(faculty):
            continue
        keep_ids.add(req.pk)
        doc = current_documents.get(req.pk)
        result = determine_status(req, doc, today)
        row = existing.get(req.pk)
        if row is None:
            to_create.append(
                ComplianceStatus(
                    faculty=faculty,
                    requirement=req,
                    document=doc,
                    status=result.status,
                    is_expiring=result.is_expiring,
                    days_to_expiry=result.days_to_expiry,
                )
            )
        else:
            row.document = doc
            row.status = result.status
            row.is_expiring = result.is_expiring
            row.days_to_expiry = result.days_to_expiry
            row.evaluated_at = timezone.now()
            to_update.append(row)

    if to_create:
        ComplianceStatus.objects.bulk_create(to_create)
    if to_update:
        ComplianceStatus.objects.bulk_update(
            to_update, ["document", "status", "is_expiring", "days_to_expiry", "evaluated_at"]
        )
    stale = [rid for rid in existing if rid not in keep_ids]
    if stale:
        ComplianceStatus.objects.filter(faculty=faculty, requirement_id__in=stale).delete()
    return ComplianceStatus.objects.filter(faculty=faculty)


def evaluate_all(today=None):
    """Re-evaluate every faculty member; returns the number evaluated."""
    today = today or timezone.localdate()
    requirements = active_requirements()
    docs_by_faculty = defaultdict(dict)
    for doc in Document.objects.filter(is_current=True).order_by("version_no"):
        docs_by_faculty[doc.faculty_id][doc.requirement_id] = doc
    count = 0
    for faculty in Faculty.objects.all():
        evaluate_faculty(faculty, requirements, docs_by_faculty.get(faculty.pk, {}), today)
        count += 1
    # Rows for requirements that were deactivated/deleted
    ComplianceStatus.objects.exclude(requirement__in=[r.pk for r in requirements]).delete()
    return count


# ---------------------------------------------------------------- rates
def _rate(complied, total):
    return round(complied / total * 100, 2) if total else 0.0


def compliance_rate(queryset):
    """complied / applicable x 100, rounded to 2 decimals, for a ComplianceStatus queryset."""
    totals = queryset.aggregate(total=Count("pk"), complied=Count("pk", filter=Q(status=Status.COMPLIED)))
    return _rate(totals["complied"], totals["total"])


def _grouped_rates(queryset, key, label_fields):
    rows = (
        queryset.values(key, *label_fields)
        .annotate(
            total=Count("pk"),
            complied=Count("pk", filter=Q(status=Status.COMPLIED)),
            incomplete=Count("pk", filter=Q(status=Status.INCOMPLETE)),
            not_complied=Count("pk", filter=Q(status=Status.NOT_COMPLIED)),
        )
        .order_by(*label_fields)
    )
    result = []
    for row in rows:
        row["rate"] = _rate(row["complied"], row["total"])
        result.append(row)
    return result


def rates_by_subarea(queryset):
    rows = _grouped_rates(
        queryset,
        "requirement__subarea",
        ["requirement__subarea__sort_order", "requirement__subarea__code", "requirement__subarea__title"],
    )
    return [
        {
            "id": r["requirement__subarea"],
            "code": r["requirement__subarea__code"],
            "title": r["requirement__subarea__title"],
            **{k: r[k] for k in ("total", "complied", "incomplete", "not_complied", "rate")},
        }
        for r in rows
    ]


def rates_by_department(queryset):
    rows = _grouped_rates(queryset, "faculty__department", ["faculty__department__code", "faculty__department__name"])
    return [
        {
            "id": r["faculty__department"],
            "code": r["faculty__department__code"],
            "name": r["faculty__department__name"],
            **{k: r[k] for k in ("total", "complied", "incomplete", "not_complied", "rate")},
        }
        for r in rows
    ]


def rates_by_faculty(queryset):
    """Mapping faculty_id -> {total, complied, rate}."""
    rows = queryset.values("faculty").annotate(
        total=Count("pk"), complied=Count("pk", filter=Q(status=Status.COMPLIED))
    )
    return {
        r["faculty"]: {"total": r["total"], "complied": r["complied"], "rate": _rate(r["complied"], r["total"])}
        for r in rows
    }


def rates_by_requirement(queryset):
    rows = queryset.values("requirement").annotate(
        total=Count("pk"),
        complied=Count("pk", filter=Q(status=Status.COMPLIED)),
        incomplete=Count("pk", filter=Q(status=Status.INCOMPLETE)),
        not_complied=Count("pk", filter=Q(status=Status.NOT_COMPLIED)),
    )
    return {r["requirement"]: {**r, "rate": _rate(r["complied"], r["total"])} for r in rows}


def faculty_summary(faculty):
    """Overall and per-sub-area rates plus a checklist for one faculty member."""
    qs = ComplianceStatus.objects.filter(faculty=faculty)
    statuses = {cs.requirement_id: cs for cs in qs.select_related("document")}
    checklist = []
    for req in active_requirements():
        checklist.append({"requirement": req, "status": statuses.get(req.pk), "applicable": req.pk in statuses})
    return {
        "overall_rate": compliance_rate(qs),
        "subarea_rates": rates_by_subarea(qs),
        "checklist": checklist,
        "counts": {
            "complied": sum(1 for s in statuses.values() if s.status == Status.COMPLIED),
            "incomplete": sum(1 for s in statuses.values() if s.status == Status.INCOMPLETE),
            "not_complied": sum(1 for s in statuses.values() if s.status == Status.NOT_COMPLIED),
            "expiring": sum(1 for s in statuses.values() if s.is_expiring),
            "applicable": len(statuses),
        },
    }
