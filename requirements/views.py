"""Requirement rule configuration. Saving a rule re-runs ``evaluate_all()`` via signals."""
from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.mixins import StaffRequiredMixin, SysAdminRequiredMixin
from audit.models import AuditLog
from audit.utils import log_action

from .forms import RequirementForm, SubAreaForm
from .models import PacucoaSubArea, Requirement


class RuleListView(StaffRequiredMixin, ListView):
    template_name = "requirements/rule_list.html"
    context_object_name = "subareas"

    def get_queryset(self):
        return PacucoaSubArea.objects.prefetch_related("requirements").annotate(
            requirement_count=Count("requirements")
        )


class AuditedRuleMixin(SysAdminRequiredMixin):
    success_url = reverse_lazy("requirements:list")
    event = "saved"

    def form_valid(self, form):
        response = super().form_valid(form)
        obj = self.object
        log_action(
            self.request.user,
            AuditLog.Action.RULE_CHANGE,
            obj=obj,
            details={"event": self.event, "item": str(obj), "changed": form.changed_data},
        )
        messages.success(self.request, f"{obj} {self.event}. Compliance was re-evaluated for all faculty.")
        return response


class SubAreaCreateView(AuditedRuleMixin, CreateView):
    model = PacucoaSubArea
    form_class = SubAreaForm
    template_name = "requirements/subarea_form.html"
    event = "created"


class SubAreaUpdateView(AuditedRuleMixin, UpdateView):
    model = PacucoaSubArea
    form_class = SubAreaForm
    template_name = "requirements/subarea_form.html"
    event = "updated"


class RequirementCreateView(AuditedRuleMixin, CreateView):
    model = Requirement
    form_class = RequirementForm
    template_name = "requirements/requirement_form.html"
    event = "created"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("subarea"):
            initial["subarea"] = self.request.GET["subarea"]
        return initial


class RequirementUpdateView(AuditedRuleMixin, UpdateView):
    model = Requirement
    form_class = RequirementForm
    template_name = "requirements/requirement_form.html"
    event = "updated"


class ProtectedDeleteView(SysAdminRequiredMixin, DeleteView):
    template_name = "requirements/confirm_delete.html"
    success_url = reverse_lazy("requirements:list")
    protected_message = ""

    def form_valid(self, form):
        obj = self.get_object()
        label = str(obj)
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, self.protected_message)
            return redirect(self.success_url)
        log_action(
            self.request.user,
            AuditLog.Action.RULE_CHANGE,
            model_name=obj.__class__.__name__,
            object_id=obj.pk or self.kwargs["pk"],
            details={"event": "deleted", "item": label},
        )
        messages.success(self.request, f"{label} deleted. Compliance was re-evaluated.")
        return response


class SubAreaDeleteView(ProtectedDeleteView):
    model = PacucoaSubArea
    protected_message = "This sub-area still has requirements. Delete or move them first."


class RequirementDeleteView(ProtectedDeleteView):
    model = Requirement
    protected_message = (
        "Faculty have already uploaded documents for this requirement. Deactivate it instead of deleting it."
    )


class RequirementToggleView(SysAdminRequiredMixin, View):
    def post(self, request, pk):
        requirement = get_object_or_404(Requirement, pk=pk)
        requirement.is_active = not requirement.is_active
        requirement.save(update_fields=["is_active"])
        state = "activated" if requirement.is_active else "deactivated"
        log_action(request.user, AuditLog.Action.RULE_CHANGE, obj=requirement, details={"event": state, "item": str(requirement)})
        messages.success(request, f"Requirement {state}. Compliance was re-evaluated.")
        return redirect("requirements:list")
