from django.shortcuts import render

from accounts.mixins import staff_required
from frames_project.utils import paginate

from .forms import ExpiryFilterForm, MatrixFilterForm
from .matrix import build_matrix, expiring_documents_for


@staff_required
def matrix(request):
    form = MatrixFilterForm(request.GET or None, user=request.user)
    filters = {}
    if form.is_valid():
        filters = {k: v for k, v in form.cleaned_data.items() if v}
    data = build_matrix(request.user, **filters)
    return render(request, "compliance/matrix.html", {"form": form, "matrix": data})


@staff_required
def expiring(request):
    form = ExpiryFilterForm(request.GET or None, user=request.user)
    window, department = "90", None
    if form.is_valid():
        window = form.cleaned_data["window"] or "90"
        department = form.cleaned_data["department"]
    qs = expiring_documents_for(request.user, window, department)
    return render(
        request,
        "compliance/expiring.html",
        {"form": form, "page_obj": paginate(request, qs, 25), "window": window, "total": qs.count()},
    )
