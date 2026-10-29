"""PACUCOA Area II compliance matrix (shared by the matrix page and the reports)."""
from datetime import timedelta

from django.utils import timezone

from documents.models import Document

from .engine import _rate, active_requirements
from .models import ComplianceStatus
from .queries import requirement_columns, scoped_faculty

Status = ComplianceStatus.Status


def build_matrix(user, department=None, subarea=None, employment_status=None, compliance=None):
    requirements = active_requirements()
    if subarea:
        requirements = [r for r in requirements if r.subarea_id == subarea.pk]
    groups = requirement_columns(requirements)
    columns = [col for g in groups for col in g["columns"]]

    faculty_qs = scoped_faculty(user, department).order_by("department__code", "last_name", "first_name")
    if employment_status:
        faculty_qs = faculty_qs.filter(employment_status=employment_status)
    faculty_list = list(faculty_qs)

    statuses = {
        (cs.faculty_id, cs.requirement_id): cs
        for cs in ComplianceStatus.objects.filter(
            faculty__in=[f.pk for f in faculty_list], requirement__in=[r.pk for r in requirements]
        )
    }

    rows = []
    for faculty in faculty_list:
        cells, complied, total = [], 0, 0
        flags = {"INCOMPLETE": False, "NOT_COMPLIED": False, "EXPIRING": False}
        for col in columns:
            cs = statuses.get((faculty.pk, col["requirement"].pk))
            cells.append(cs)
            if cs is None:
                continue
            total += 1
            if cs.status == Status.COMPLIED:
                complied += 1
            elif cs.status in flags:
                flags[cs.status] = True
            if cs.is_expiring:
                flags["EXPIRING"] = True
        row = {"faculty": faculty, "cells": cells, "complied": complied, "total": total, "rate": _rate(complied, total)}
        if compliance == "FULL" and not (total and complied == total):
            continue
        if compliance in flags and not flags[compliance]:
            continue
        rows.append(row)

    column_totals = []
    for index, col in enumerate(columns):
        applicable = [r["cells"][index] for r in rows if r["cells"][index] is not None]
        done = sum(1 for cs in applicable if cs.status == Status.COMPLIED)
        column_totals.append({"complied": done, "total": len(applicable), "rate": _rate(done, len(applicable))})

    grand_complied = sum(r["complied"] for r in rows)
    grand_total = sum(r["total"] for r in rows)
    return {
        "groups": groups,
        "columns": columns,
        "rows": rows,
        "column_totals": column_totals,
        "overall": {"complied": grand_complied, "total": grand_total, "rate": _rate(grand_complied, grand_total)},
    }


EXPIRY_WINDOWS = [("30", "Within 30 days"), ("60", "Within 60 days"), ("90", "Within 90 days"), ("expired", "Expired"), ("all", "Expired + within 90 days")]


def expiring_documents_for(user, window="90", department=None, today=None):
    """Current approved credentials of expiring requirements, filtered by window."""
    today = today or timezone.localdate()
    qs = (
        Document.objects.visible_to(user)
        .filter(
            is_current=True,
            status=Document.Status.APPROVED,
            requirement__has_expiry=True,
            requirement__is_active=True,
            expiry_date__isnull=False,
        )
        .select_related("faculty__department", "requirement__subarea")
        .order_by("expiry_date")
    )
    if department:
        qs = qs.filter(faculty__department=department)
    if window == "expired":
        qs = qs.filter(expiry_date__lt=today)
    elif window == "all":
        qs = qs.filter(expiry_date__lte=today + timedelta(days=90))
    else:
        days = int(window) if str(window).isdigit() else 90
        qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=days))
    return qs
