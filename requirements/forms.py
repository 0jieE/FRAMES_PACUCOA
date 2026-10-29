from django import forms

from frames_project.forms import BootstrapFormMixin

from .models import PacucoaSubArea, Requirement


class SubAreaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PacucoaSubArea
        fields = ["code", "title", "description", "sort_order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class RequirementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Requirement
        fields = [
            "subarea",
            "name",
            "documentary_basis",
            "applicability",
            "is_mandatory",
            "has_expiry",
            "is_active",
            "sort_order",
        ]
        widgets = {"documentary_basis": forms.Textarea(attrs={"rows": 3})}
