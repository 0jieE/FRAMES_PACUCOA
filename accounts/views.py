from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, views as auth_views
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from audit.utils import log_action
from frames_project.utils import paginate

from .forms import FramesPasswordChangeForm, FramesSetPasswordForm, LoginForm, UserCreateForm, UserEditForm
from .mixins import sysadmin_required
from .models import User
from .services import create_user_from_form


class FramesLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class FramesLogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("accounts:login")


class FramesPasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = FramesPasswordChangeForm
    success_url = reverse_lazy("accounts:home")

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, AuditLog.Action.PASSWORD_CHANGE, obj=self.request.user)
        messages.success(self.request, "Your password has been changed.")
        return response


@login_required
def home(request):
    """Send each role to its landing page."""
    user = request.user
    if user.is_faculty:
        return redirect("faculty:my_profile")
    if user.is_staff_role:
        return redirect("dashboard:index")
    messages.warning(request, "Your account has no role assigned. Contact the System Administrator.")
    return render(request, "accounts/no_role.html")


# ---------------------------------------------------------------- user management
@sysadmin_required
def user_list(request):
    users = User.objects.select_related("department").order_by("role", "last_name", "first_name")
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    active = request.GET.get("active", "")
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    if role:
        users = users.filter(role=role)
    if active in ("1", "0"):
        users = users.filter(is_active=active == "1")
    return render(
        request,
        "accounts/user_list.html",
        {"page_obj": paginate(request, users, 20), "roles": User.Role.choices, "q": q, "role": role, "active": active},
    )


@sysadmin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = create_user_from_form(form)
        log_action(
            request.user,
            AuditLog.Action.USER_CHANGE,
            obj=user,
            details={"event": "created", "username": user.username, "role": user.role},
        )
        messages.success(request, f"User '{user.username}' created.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "New user", "is_create": True})


@sysadmin_required
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    before = {"role": target.role, "department": str(target.department or ""), "is_active": target.is_active}
    form = UserEditForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        if target == request.user and not form.cleaned_data["is_active"]:
            messages.error(request, "You cannot deactivate your own account.")
        else:
            user = form.save()
            after = {"role": user.role, "department": str(user.department or ""), "is_active": user.is_active}
            log_action(
                request.user,
                AuditLog.Action.USER_CHANGE,
                obj=user,
                details={"event": "updated", "username": user.username, "before": before, "after": after},
            )
            messages.success(request, f"User '{user.username}' updated.")
            return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": f"Edit {target.username}", "target": target})


@sysadmin_required
@require_POST
def user_toggle_active(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("accounts:user_list")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    state = "activated" if target.is_active else "deactivated"
    log_action(request.user, AuditLog.Action.USER_CHANGE, obj=target, details={"event": state, "username": target.username})
    messages.success(request, f"User '{target.username}' {state}.")
    return redirect("accounts:user_list")


@sysadmin_required
def user_reset_password(request, pk):
    target = get_object_or_404(User, pk=pk)
    form = FramesSetPasswordForm(target, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        if target == request.user:
            update_session_auth_hash(request, target)
        log_action(
            request.user, AuditLog.Action.USER_CHANGE, obj=target, details={"event": "password reset", "username": target.username}
        )
        messages.success(request, f"Password for '{target.username}' has been reset.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_password.html", {"form": form, "target": target})
