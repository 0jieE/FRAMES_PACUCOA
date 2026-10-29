from django.db.models import Q
from django.shortcuts import render

from accounts.mixins import sysadmin_required
from frames_project.utils import paginate

from .forms import AuditFilterForm
from .models import AuditLog


@sysadmin_required
def audit_list(request):
    form = AuditFilterForm(request.GET or None)
    qs = AuditLog.objects.select_related("user")
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            q = data["q"]
            qs = qs.filter(
                Q(details__icontains=q) | Q(model_name__icontains=q) | Q(ip_address__icontains=q) | Q(user__username__icontains=q)
            )
        if data["user"]:
            qs = qs.filter(user=data["user"])
        if data["action"]:
            qs = qs.filter(action=data["action"])
        if data["date_from"]:
            qs = qs.filter(timestamp__date__gte=data["date_from"])
        if data["date_to"]:
            qs = qs.filter(timestamp__date__lte=data["date_to"])
    return render(request, "audit/list.html", {"form": form, "page_obj": paginate(request, qs, 25), "total": qs.count()})
