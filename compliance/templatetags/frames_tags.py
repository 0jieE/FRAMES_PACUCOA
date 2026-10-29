"""Status badges and small template helpers used across FRAMES."""
from django import template
from django.utils.html import format_html

register = template.Library()

COMPLIANCE_BADGES = {
    "COMPLIED": ("success", "Complied", "bi-check-circle-fill"),
    "INCOMPLETE": ("warning", "Incomplete", "bi-hourglass-split"),
    "NOT_COMPLIED": ("danger", "Not Complied", "bi-x-circle-fill"),
    "NA": ("secondary", "N/A", "bi-dash-circle"),
}

DOCUMENT_BADGES = {
    "PENDING": ("warning", "Pending"),
    "APPROVED": ("success", "Approved"),
    "REJECTED": ("danger", "Rejected"),
    "RESUBMIT": ("warning", "Re-submit"),
}


def _badge(code, extra=""):
    color, label, icon = COMPLIANCE_BADGES.get(code, COMPLIANCE_BADGES["NA"])
    text_class = " text-dark" if color == "warning" else ""
    return format_html('<span class="badge bg-{}{} status-badge"><i class="bi {} me-1"></i>{}{}</span>', color, text_class, icon, label, extra)


@register.simple_tag
def status_badge(compliance_status):
    """Badge for a ComplianceStatus (None means not applicable)."""
    if compliance_status is None:
        return _badge("NA")
    badge = _badge(compliance_status.status)
    if compliance_status.is_expiring:
        return format_html(
            '{} <span class="badge bg-light text-dark border" title="Expires in {} day(s)"><i class="bi bi-clock-history text-warning"></i> {}d</span>',
            badge,
            compliance_status.days_to_expiry,
            compliance_status.days_to_expiry,
        )
    if compliance_status.is_expired:
        return format_html('{} <span class="badge bg-light text-danger border">expired</span>', badge)
    return badge


@register.simple_tag
def status_code_badge(code):
    return _badge(code)


@register.simple_tag
def doc_status_badge(document):
    if document is None:
        return format_html('<span class="badge bg-secondary">No upload</span>')
    color, label = DOCUMENT_BADGES.get(document.status, ("secondary", document.status))
    text_class = " text-dark" if color == "warning" else ""
    return format_html('<span class="badge bg-{}{}">{}</span>', color, text_class, label)


@register.filter
def rate_color(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "secondary"
    if value >= 80:
        return "success"
    if value >= 50:
        return "warning"
    return "danger"


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Current query string with some parameters replaced (keeps filters while paginating)."""
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()


@register.filter
def matrix_cell_class(compliance_status):
    if compliance_status is None:
        return "cell-na"
    return {"COMPLIED": "cell-ok", "INCOMPLETE": "cell-warn", "NOT_COMPLIED": "cell-bad"}.get(compliance_status.status, "cell-na")
