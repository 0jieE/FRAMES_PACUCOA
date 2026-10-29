from django import forms
from django.utils import timezone

from faculty.models import Department
from frames_project.forms import BootstrapFormMixin, DateInput
from requirements.models import PacucoaSubArea, Requirement

from .models import Document, Validation
from .validators import validate_upload


class RequirementChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        suffix = " (with expiry date)" if obj.has_expiry else ""
        return f"{obj.subarea.code} · {obj.name}{suffix}"


class UploadForm(BootstrapFormMixin, forms.Form):
    requirement = RequirementChoiceField(queryset=Requirement.objects.none(), empty_label="Select a requirement…")
    file = forms.FileField(
        help_text="PDF, JPG or PNG, max 10 MB.",
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"}),
    )
    date_issued = forms.DateField(widget=DateInput(), label="Date issued")
    expiry_date = forms.DateField(
        widget=DateInput(), required=False, label="Expiry / validity date", help_text="Required for documents that expire."
    )

    def __init__(self, *args, faculty, **kwargs):
        super().__init__(*args, **kwargs)
        self.faculty = faculty
        applicable = [r.pk for r in Requirement.objects.active().ordered() if r.applies_to(faculty)]
        self.fields["requirement"].queryset = Requirement.objects.filter(pk__in=applicable).ordered()
        self.file_type = None

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        self.file_type = validate_upload(uploaded)
        return uploaded

    def clean(self):
        cleaned = super().clean()
        requirement = cleaned.get("requirement")
        issued, expiry = cleaned.get("date_issued"), cleaned.get("expiry_date")
        today = timezone.localdate()
        if issued and issued > today:
            self.add_error("date_issued", "Date issued cannot be in the future.")
        if requirement and requirement.has_expiry and not expiry:
            self.add_error("expiry_date", "This requirement has an expiry date; please enter it.")
        if issued and expiry and expiry <= issued:
            self.add_error("expiry_date", "Expiry date must be after the date issued.")
        if requirement and not requirement.applies_to(self.faculty):
            self.add_error("requirement", "This requirement does not apply to you.")
        return cleaned


class ValidationForm(BootstrapFormMixin, forms.Form):
    decision = forms.ChoiceField(choices=Validation.Decision.choices, widget=forms.RadioSelect)
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Required when rejecting or requesting re-submission."}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["decision"].widget.attrs["class"] = "form-check-input"

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get("decision")
        if decision and decision != Validation.Decision.APPROVED and not cleaned.get("remarks", "").strip():
            self.add_error("remarks", "Remarks are required when rejecting or requesting re-submission.")
        return cleaned


class DocumentFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(required=False, label="Search", widget=forms.TextInput(attrs={"placeholder": "Faculty or requirement"}))
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False, empty_label="All departments")
    subarea = forms.ModelChoiceField(queryset=PacucoaSubArea.objects.all(), required=False, empty_label="All sub-areas")
    status = forms.ChoiceField(choices=[("", "All statuses")] + list(Document.Status.choices), required=False)
    history = forms.BooleanField(required=False, label="Include old versions")

    def __init__(self, *args, user=None, show_status=True, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.scope_department:
            self.fields["department"].queryset = Department.objects.filter(pk=user.scope_department.pk)
        if user is not None and user.is_faculty:
            self.fields.pop("department")
        if not show_status:
            self.fields.pop("status")
            self.fields.pop("history")
