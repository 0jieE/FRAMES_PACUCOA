"""Role-based access mixins and decorators (FACULTY, HR_ADMIN, AREA_CHAIR, SYS_ADMIN)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .models import MANAGER_ROLES, STAFF_ROLES, VALIDATOR_ROLES, User


def role_required(*roles):
    """Allow the view only for logged-in users whose role is in ``roles``."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied("Your role does not have access to this page.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


faculty_required = role_required(User.Role.FACULTY)
staff_required = role_required(*STAFF_ROLES)
validator_required = role_required(*VALIDATOR_ROLES)
manager_required = role_required(*MANAGER_ROLES)
sysadmin_required = role_required(User.Role.SYS_ADMIN)


class RoleRequiredMixin(LoginRequiredMixin):
    """Class-based equivalent of ``role_required``; set ``allowed_roles``."""

    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role not in self.allowed_roles:
            raise PermissionDenied("Your role does not have access to this page.")
        return super().dispatch(request, *args, **kwargs)


class SysAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.SYS_ADMIN,)


class StaffRequiredMixin(RoleRequiredMixin):
    allowed_roles = STAFF_ROLES


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = MANAGER_ROLES
