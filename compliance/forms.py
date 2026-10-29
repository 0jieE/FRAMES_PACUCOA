from django import forms

from faculty.models import Department, Faculty
from frames_project.forms import BootstrapFormMixin
from requirements.models import PacucoaSubArea

from .matrix import EXPIRY_WINDOWS
from .queries import COMPLIANCE_FILTER_CHOICES


class ScopedDepartmentMixin:
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.scope_department and "department" in self.fields:
            self.fields["department"].queryset = Department.objects.filter(pk=user.scope_department.pk)
            self.fields["department"].empty_label = None


class MatrixFilterForm(ScopedDepartmentMixin, BootstrapFormMixin, forms.Form):
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False, empty_label="All departments")
    subarea = forms.ModelChoiceField(queryset=PacucoaSubArea.objects.all(), required=False, empty_label="All sub-areas")
    employment_status = forms.ChoiceField(
        choices=[("", "All employment")] + list(Faculty.EmploymentStatus.choices), required=False
    )
    compliance = forms.ChoiceField(choices=[("", "Any compliance")] + COMPLIANCE_FILTER_CHOICES, required=False)


class ExpiryFilterForm(ScopedDepartmentMixin, BootstrapFormMixin, forms.Form):
    window = forms.ChoiceField(choices=EXPIRY_WINDOWS, required=False, initial="90")
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False, empty_label="All departments")
