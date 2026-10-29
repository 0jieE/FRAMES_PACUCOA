"""Custom User model with role-based access control."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        FACULTY = "FACULTY", "Faculty Member"
        HR_ADMIN = "HR_ADMIN", "HR / Records Administrator"
        AREA_CHAIR = "AREA_CHAIR", "PACUCOA Area II Chair"
        SYS_ADMIN = "SYS_ADMIN", "System Administrator"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.FACULTY)
    department = models.ForeignKey(
        "faculty.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scoped_users",
        help_text="Area Chair scope. Leave blank to see all departments.",
    )

    class Meta:
        ordering = ["last_name", "first_name", "username"]

    def __str__(self):
        return self.get_full_name() or self.username

    # Role helpers -----------------------------------------------------
    @property
    def is_faculty(self):
        return self.role == self.Role.FACULTY

    @property
    def is_hr(self):
        return self.role == self.Role.HR_ADMIN

    @property
    def is_area_chair(self):
        return self.role == self.Role.AREA_CHAIR

    @property
    def is_sysadmin(self):
        return self.role == self.Role.SYS_ADMIN

    @property
    def is_staff_role(self):
        """HR, Area Chair, and SysAdmin can view the matrix, dashboard, and reports."""
        return self.role in STAFF_ROLES

    @property
    def can_validate(self):
        return self.role in VALIDATOR_ROLES

    @property
    def can_manage_faculty(self):
        return self.role in MANAGER_ROLES

    @property
    def scope_department(self):
        """Department restriction for Area Chairs (None means all departments)."""
        if self.is_area_chair:
            return self.department
        return None

    @property
    def faculty_profile(self):
        return getattr(self, "faculty", None)


STAFF_ROLES = (User.Role.HR_ADMIN, User.Role.AREA_CHAIR, User.Role.SYS_ADMIN)
VALIDATOR_ROLES = (User.Role.HR_ADMIN, User.Role.AREA_CHAIR)
MANAGER_ROLES = (User.Role.HR_ADMIN, User.Role.SYS_ADMIN)
