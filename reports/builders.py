"""Report data builders. Each returns a renderer-agnostic ``Report`` (see pdf.py / excel.py)."""
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from compliance.engine import compliance_rate, faculty_summary, rates_by_department, rates_by_subarea
from compliance.matrix import EXPIRY_WINDOWS, build_matrix, expiring_documents_for
from compliance.models import ComplianceStatus
from compliance.queries import scoped_statuses
from documents.models import Document

Status = ComplianceStatus.Status
STATUS_LABEL = dict(Status.choices)


@dataclass
class Cell:
    text: str
    status: str | None = None  # COMPLIED / INCOMPLETE / NOT_COMPLIED / NA / EXPIRING / PERCENT
    bold: bool = False

    def __str__(self):
        return self.text


@dataclass
class Table:
    heading: str
    headers: list
    rows: list
    col_widths: list | None = None  # relative widths
    sheet_name: str | None = None
    font_size: float = 8
    freeze: str | None = None  # Excel freeze-panes cell, e.g. "C2"
    totals_row: bool = False


@dataclass
class Report:
    title: str
    slug: str
    user: object
    filters: list = field(default_factory=list)  # [(label, value)]
    summary: list = field(default_factory=list)  # [(label, value)]
    tables: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    landscape: bool = False
    wide: bool = False
    generated_at: datetime = field(default_factory=timezone.localtime)

    @property
    def generated_by(self):
        user = self.user
        name = user.get_full_name() or user.username
        return f"{name} ({user.get_role_display()})"

    def filename(self, ext):
        return f"frames_{self.slug}_{self.generated_at:%Y%m%d_%H%M}.{ext}"


def _status_cell(cs):
    if cs is None:
        return Cell("N/A", "NA")
    if cs.status == Status.COMPLIED and cs.is_expiring:
        return Cell(f"Complied ({cs.days_to_expiry}d)", "EXPIRING")
    if cs.status == Status.NOT_COMPLIED and cs.is_expired:
        return Cell("Not Complied (expired)", Status.NOT_COMPLIED)
    return Cell(STATUS_LABEL[cs.status], cs.status)


def _pct(value):
    return Cell(f"{value:.2f}%", "PERCENT", bold=True)


def _department_label(department):
    return f"{department.code} — {department.name}" if department else "All departments"


def _scope_label(user, department):
    if user.scope_department:
        return _department_label(user.scope_department)
    return _department_label(department)


# ------------------------------------------------------------------ 1. faculty summary
def faculty_summary_report(user, faculty):
    data = faculty_summary(faculty)
    counts = data["counts"]
    report = Report(
        title="Faculty Compliance Summary",
        slug=f"faculty_{faculty.employee_no}",
        user=user,
        filters=[("Faculty", f"{faculty.sortable_name} ({faculty.employee_no})"), ("Department", _department_label(faculty.department))],
        summary=[
            ("Overall Area II compliance", f"{data['overall_rate']:.2f}%"),
            ("Applicable requirements", counts["applicable"]),
            ("Complied", counts["complied"]),
            ("Incomplete", counts["incomplete"]),
            ("Not complied", counts["not_complied"]),
            ("Expiring within 90 days", counts["expiring"]),
            ("Rank / status", f"{faculty.get_academic_rank_display()} · {faculty.get_employment_status_display()}"),
            ("Highest degree", faculty.get_highest_degree_display()),
        ],
    )
    report.tables.append(
        Table(
            "Compliance by sub-area",
            ["Sub-area", "Title", "Complied", "Applicable", "Rate"],
            [[s["code"], s["title"], s["complied"], s["total"], _pct(s["rate"])] for s in data["subarea_rates"]],
            col_widths=[1, 5, 1.2, 1.2, 1.2],
            sheet_name="By sub-area",
        )
    )
    rows = []
    for item in data["checklist"]:
        req, cs = item["requirement"], item["status"]
        doc = cs.document if cs else None
        rows.append(
            [
                req.subarea.code,
                req.name,
                _status_cell(cs),
                f"v{doc.version_no} · {doc.get_status_display()}" if doc else ("—" if cs else "Not applicable"),
                doc.expiry_date.strftime("%Y-%m-%d") if doc and doc.expiry_date else "—",
            ]
        )
    report.tables.append(
        Table("Requirement checklist", ["Sub-area", "Requirement", "Status", "Current document", "Expiry"], rows, col_widths=[1, 5, 2.4, 2.4, 1.4], sheet_name="Checklist")
    )
    return report


# ------------------------------------------------------------------ 2. matrix
CELL_TEXT = {Status.COMPLIED: "C", Status.INCOMPLETE: "I", Status.NOT_COMPLIED: "X"}


def matrix_report(user, department=None):
    data = build_matrix(user, department=department)
    columns = data["columns"]
    headers = ["Faculty", "Dept"] + [c["code"] for c in columns] + ["%"]
    rows = []
    for row in data["rows"]:
        cells = []
        for cs in row["cells"]:
            if cs is None:
                cells.append(Cell("N/A", "NA"))
            elif cs.status == Status.COMPLIED and cs.is_expiring:
                cells.append(Cell("C*", "EXPIRING"))
            else:
                cells.append(Cell(CELL_TEXT[cs.status], cs.status))
        rows.append([row["faculty"].sortable_name, row["faculty"].department.code] + cells + [_pct(row["rate"])])
    rows.append(
        [Cell("Requirement %", bold=True), ""]
        + [Cell(f"{t['rate']:.0f}%", "PERCENT", bold=True) for t in data["column_totals"]]
        + [_pct(data["overall"]["rate"])]
    )
    report = Report(
        title="PACUCOA Area II Compliance Matrix",
        slug="compliance_matrix",
        user=user,
        filters=[("Department", _scope_label(user, department))],
        summary=[
            ("Faculty in matrix", len(data["rows"])),
            ("Overall Area II compliance", f"{data['overall']['rate']:.2f}%"),
            ("Legend", "C = Complied, C* = Complied but expiring within 90 days, I = Incomplete, X = Not Complied, N/A = not applicable"),
        ],
        landscape=True,
        wide=True,
    )
    report.tables.append(
        Table(
            "Compliance matrix",
            headers,
            rows,
            col_widths=[4.2, 1.3] + [1] * len(columns) + [1.5],
            sheet_name="Matrix",
            font_size=6.5,
            freeze="C2",
            totals_row=True,
        )
    )
    report.tables.append(
        Table(
            "Column legend",
            ["Code", "Sub-area", "Requirement", "Applicability", "Expiry"],
            [
                [c["code"], c["requirement"].subarea.code, c["requirement"].name, c["requirement"].get_applicability_display(), "Yes" if c["requirement"].has_expiry else "No"]
                for c in columns
            ],
            col_widths=[0.8, 1, 6, 3, 0.8],
            sheet_name="Legend",
        )
    )
    return report


# ------------------------------------------------------------------ 3. missing documents
def _missing_reason(cs):
    doc = cs.document
    if cs.status == Status.INCOMPLETE:
        if doc and doc.status == Document.Status.RESUBMIT:
            return "Re-submission requested"
        return "Pending validation"
    if doc is None:
        return "No upload"
    if doc.status == Document.Status.REJECTED:
        return "Rejected"
    if cs.is_expired:
        return f"Expired {doc.expiry_date:%Y-%m-%d}"
    return "Not complied"


def missing_report(user, department=None, subarea=None):
    qs = (
        scoped_statuses(user, department)
        .exclude(status=Status.COMPLIED)
        .select_related("faculty__department", "requirement__subarea", "document")
        .order_by("faculty__department__code", "faculty__last_name", "faculty__first_name", "requirement__subarea__sort_order", "requirement__sort_order")
    )
    if subarea:
        qs = qs.filter(requirement__subarea=subarea)
    rows = [
        [cs.faculty.sortable_name, cs.faculty.department.code, cs.requirement.subarea.code, cs.requirement.name, _status_cell(cs), _missing_reason(cs)]
        for cs in qs
    ]
    report = Report(
        title="Missing-Document Report",
        slug="missing_documents",
        user=user,
        filters=[("Department", _scope_label(user, department)), ("Sub-area", str(subarea) if subarea else "All sub-areas")],
        summary=[
            ("Items not yet complied", len(rows)),
            ("Not complied", sum(1 for cs in qs if cs.status == Status.NOT_COMPLIED)),
            ("Incomplete (pending / re-submission)", sum(1 for cs in qs if cs.status == Status.INCOMPLETE)),
            ("Faculty affected", len({cs.faculty_id for cs in qs})),
        ],
        landscape=True,
    )
    report.tables.append(
        Table("Missing and incomplete requirements", ["Faculty", "Dept", "Sub-area", "Requirement", "Status", "Reason"], rows, col_widths=[3, 1, 1, 6, 2.6, 2.4], sheet_name="Missing")
    )
    return report


# ------------------------------------------------------------------ 4. expiring
def expiring_report(user, window="all", department=None):
    today = timezone.localdate()
    docs = list(expiring_documents_for(user, window, department, today))
    rows = []
    for doc in docs:
        days = (doc.expiry_date - today).days
        status = Cell(f"Expired {abs(days)} day(s) ago", Status.NOT_COMPLIED) if days < 0 else Cell(f"{days} day(s) left", "EXPIRING")
        rows.append([doc.faculty.sortable_name, doc.faculty.department.code, doc.requirement.subarea.code, doc.requirement.name, doc.expiry_date.strftime("%Y-%m-%d"), status])
    report = Report(
        title="Expiring and Expired Credentials Report",
        slug="expiring_credentials",
        user=user,
        filters=[("Window", dict(EXPIRY_WINDOWS).get(window, window)), ("Department", _scope_label(user, department))],
        summary=[
            ("Credentials listed", len(rows)),
            ("Expired", sum(1 for d in docs if d.expiry_date < today)),
            ("Expiring within 30 days", sum(1 for d in docs if 0 <= (d.expiry_date - today).days <= 30)),
            ("Expiring in 31–90 days", sum(1 for d in docs if 30 < (d.expiry_date - today).days <= 90)),
        ],
        landscape=True,
    )
    report.tables.append(
        Table("Credentials", ["Faculty", "Dept", "Sub-area", "Requirement", "Expiry date", "Status"], rows, col_widths=[3, 1, 1, 6, 1.6, 2.4], sheet_name="Credentials")
    )
    return report


# ------------------------------------------------------------------ 5. audit summary
def audit_summary_report(user, department=None):
    statuses = scoped_statuses(user, department)
    subareas = rates_by_subarea(statuses)
    departments = rates_by_department(statuses)
    report = Report(
        title="PACUCOA Area II Audit Summary",
        slug="area2_audit_summary",
        user=user,
        filters=[("Department", _scope_label(user, department))],
        summary=[
            ("Overall Area II compliance", f"{compliance_rate(statuses):.2f}%"),
            ("Faculty evaluated", statuses.values("faculty").distinct().count()),
            ("Applicable requirement items", statuses.count()),
            ("Complied", statuses.filter(status=Status.COMPLIED).count()),
            ("Incomplete", statuses.filter(status=Status.INCOMPLETE).count()),
            ("Not complied", statuses.filter(status=Status.NOT_COMPLIED).count()),
            ("Expiring within 90 days", statuses.filter(is_expiring=True).count()),
        ],
    )
    headers = ["Code", "Title", "Complied", "Incomplete", "Not complied", "Applicable", "Rate"]
    report.tables.append(
        Table(
            "Compliance by sub-area",
            headers,
            [[s["code"], s["title"], s["complied"], s["incomplete"], s["not_complied"], s["total"], _pct(s["rate"])] for s in subareas],
            col_widths=[1, 4.5, 1.3, 1.3, 1.4, 1.3, 1.3],
            sheet_name="By sub-area",
        )
    )
    report.tables.append(
        Table(
            "Compliance by department",
            headers,
            [[d["code"], d["name"], d["complied"], d["incomplete"], d["not_complied"], d["total"], _pct(d["rate"])] for d in departments],
            col_widths=[1, 4.5, 1.3, 1.3, 1.4, 1.3, 1.3],
            sheet_name="By department",
        )
    )
    return report
