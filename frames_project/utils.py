"""Shared view helpers."""
from django.core.paginator import Paginator


def paginate(request, queryset, per_page=20):
    """Return the requested page of ``queryset`` (invalid page numbers fall back safely)."""
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
