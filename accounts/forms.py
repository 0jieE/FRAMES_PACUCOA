from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password

from faculty.models import Department, Faculty
from frames_project.forms import BootstrapFormMixin, DateInput

from .models import User


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    pass


class FramesPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class FramesSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    pass


FACULTY_REQUIRED_FIELDS = (
    "employee_no",
    "faculty_department",
    "sex",
    "employment_status",
    "faculty_type",
    "academic_rank",
    "highest_degree",
    "date_hired",
)


class UserCreateForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput, strip=False)

    # Faculty profile fields (required only when role = FACULTY)
    employee_no = forms.CharField(required=False, max_length=30, help_text="e.g. CDK-2018-0123")
    faculty_department = forms.ModelChoiceField(
        queryset=Department.objects.all(), required=False, label="Faculty department"
    )
    middle_name = forms.CharField(required=False, max_length=100)
    sex = forms.ChoiceField(choices=[("", "---------")] + list(Faculty.Sex.choices), required=False)
    employment_status = forms.ChoiceField(
        choices=[("", "---------")] + list(Faculty.EmploymentStatus.choices), required=False
    )
    faculty_type = forms.ChoiceField(
        choices=Faculty.FacultyType.choices, required=False, initial=Faculty.FacultyType.UNDERGRADUATE
    )
    academic_rank = forms.ChoiceField(
        choices=Faculty.AcademicRank.choices, required=False, initial=Faculty.AcademicRank.INSTRUCTOR_I
    )
    highest_degree = forms.ChoiceField(
        choices=[("", "---------")] + list(Faculty.HighestDegree.choices), required=False
    )
    has_foreign_degree = forms.BooleanField(required=False)
    teaches_licensure_program = forms.BooleanField(required=False)
    on_study_leave = forms.BooleanField(required=False)
    date_hired = forms.DateField(required=False, widget=DateInput())
    contact_no = forms.CharField(required=False, max_length=30)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "department", "is_active"]
        labels = {"department": "Department scope (Area Chair only)"}

    def __init__(self, *args, force_faculty=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        if force_faculty:
            self.fields["role"].initial = User.Role.FACULTY
            self.fields["role"].disabled = True
            self.fields.pop("department")

    def clean_employee_no(self):
        value = self.cleaned_data.get("employee_no", "").strip()
        if value and Faculty.objects.filter(employee_no__iexact=value).exists():
            raise forms.ValidationError("This employee number is already used.")
        return value

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        elif p1:
            try:
                validate_password(p1, self.instance)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        role = cleaned.get("role")
        if role == User.Role.FACULTY:
            for name in FACULTY_REQUIRED_FIELDS:
                if not cleaned.get(name):
                    self.add_error(name, "Required for faculty accounts.")
        if role != User.Role.AREA_CHAIR and "department" in self.fields:
            cleaned["department"] = None
        return cleaned


class UserEditForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "department", "is_active"]
        labels = {"department": "Department scope (Area Chair only)"}

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        has_profile = Faculty.objects.filter(user=self.instance).exists()
        if role == User.Role.FACULTY and not has_profile:
            self.add_error("role", "Faculty accounts need a profile: create them with 'New user' and role Faculty.")
        if role != User.Role.FACULTY and has_profile:
            self.add_error("role", "This account has a faculty profile; its role must stay Faculty Member.")
        if role != User.Role.AREA_CHAIR:
            cleaned["department"] = None
        return cleaned
