from django import forms

from accounts.models import User
from frames_project.forms import BootstrapFormMixin, DateInput

from .models import AuditLog


class AuditFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(required=False, label="Search", widget=forms.TextInput(attrs={"placeholder": "Details, model, IP"}))
    user = forms.ModelChoiceField(queryset=User.objects.order_by("username"), required=False, empty_label="All users")
    action = forms.ChoiceField(choices=[("", "All actions")] + list(AuditLog.Action.choices), required=False)
    date_from = forms.DateField(required=False, widget=DateInput(), label="From")
    date_to = forms.DateField(required=False, widget=DateInput(), label="To")
