from django import forms

from compliance.queries import COMPLIANCE_FILTER_CHOICES
from frames_project.forms import BootstrapFormMixin, DateInput

from .models import Department, Faculty


class FacultyForm(BootstrapFormMixin, forms.ModelForm):
    """Full profile editing for HR / SysAdmin."""

    class Meta:
        model = Faculty
        exclude = ["user"]
        widgets = {"date_hired": DateInput()}


class ContactForm(BootstrapFormMixin, forms.Form):
    """Faculty members may edit their contact information only."""

    contact_no = forms.CharField(max_length=30, required=False, label="Contact no.")
    email = forms.EmailField(required=False)


class DepartmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ["code", "name", "dean_name"]


def _blank(choices, label="All"):
    return [("", label)] + list(choices)


class FacultySearchForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(required=False, label="Search", widget=forms.TextInput(attrs={"placeholder": "Name or employee no."}))
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False, empty_label="All departments")
    rank = forms.ChoiceField(choices=_blank(Faculty.AcademicRank.choices, "All ranks"), required=False)
    employment_status = forms.ChoiceField(choices=_blank(Faculty.EmploymentStatus.choices, "All statuses"), required=False)
    highest_degree = forms.ChoiceField(choices=_blank(Faculty.HighestDegree.choices, "All degrees"), required=False)
    compliance = forms.ChoiceField(choices=_blank(COMPLIANCE_FILTER_CHOICES, "Any compliance"), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.scope_department:
            self.fields["department"].queryset = Department.objects.filter(pk=user.scope_department.pk)
