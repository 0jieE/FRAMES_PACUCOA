from django import forms

from compliance.forms import ScopedDepartmentMixin
from compliance.matrix import EXPIRY_WINDOWS
from faculty.models import Department, Faculty
from frames_project.forms import BootstrapFormMixin
from requirements.models import PacucoaSubArea

FORMAT_CHOICES = [("pdf", "PDF"), ("xlsx", "Excel")]


class ReportFormBase(ScopedDepartmentMixin, BootstrapFormMixin, forms.Form):
    format = forms.ChoiceField(choices=FORMAT_CHOICES, initial="pdf")


class FacultyReportForm(ReportFormBase):
    faculty = forms.ModelChoiceField(queryset=Faculty.objects.none(), empty_label="Select faculty…")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if user is not None:
            self.fields["faculty"].queryset = Faculty.objects.visible_to(user).select_related("department").order_by("last_name", "first_name")
        self.fields["faculty"].label_from_instance = lambda f: f"{f.sortable_name} — {f.department.code}"


class DepartmentReportForm(ReportFormBase):
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False, empty_label="All departments")


class MissingReportForm(DepartmentReportForm):
    subarea = forms.ModelChoiceField(queryset=PacucoaSubArea.objects.all(), required=False, empty_label="All sub-areas")


class ExpiringReportForm(DepartmentReportForm):
    window = forms.ChoiceField(choices=EXPIRY_WINDOWS, initial="all")
