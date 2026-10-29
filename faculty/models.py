"""Departments and faculty profiles."""
from django.conf import settings
from django.db import models
from django.urls import reverse


class Department(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    dean_name = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class FacultyQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Faculty records the given user may see (role + department scope)."""
        if not user.is_authenticated:
            return self.none()
        if user.is_faculty:
            return self.filter(user=user)
        if user.is_staff_role:
            dept = user.scope_department
            return self.filter(department=dept) if dept else self.all()
        return self.none()


class Faculty(models.Model):
    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"

    class EmploymentStatus(models.TextChoices):
        FULL_TIME = "FULL_TIME", "Full-time"
        PART_TIME = "PART_TIME", "Part-time"

    class FacultyType(models.TextChoices):
        UNDERGRADUATE = "UNDERGRADUATE", "Undergraduate"
        GRADUATE = "GRADUATE", "Graduate"

    class AcademicRank(models.TextChoices):
        INSTRUCTOR_I = "INSTRUCTOR_I", "Instructor I"
        INSTRUCTOR_II = "INSTRUCTOR_II", "Instructor II"
        INSTRUCTOR_III = "INSTRUCTOR_III", "Instructor III"
        ASST_PROF_I = "ASST_PROF_I", "Assistant Professor I"
        ASST_PROF_II = "ASST_PROF_II", "Assistant Professor II"
        ASST_PROF_III = "ASST_PROF_III", "Assistant Professor III"
        ASST_PROF_IV = "ASST_PROF_IV", "Assistant Professor IV"
        ASSOC_PROF_I = "ASSOC_PROF_I", "Associate Professor I"
        ASSOC_PROF_II = "ASSOC_PROF_II", "Associate Professor II"
        ASSOC_PROF_III = "ASSOC_PROF_III", "Associate Professor III"
        ASSOC_PROF_IV = "ASSOC_PROF_IV", "Associate Professor IV"
        ASSOC_PROF_V = "ASSOC_PROF_V", "Associate Professor V"
        PROFESSOR = "PROFESSOR", "Professor"

    class HighestDegree(models.TextChoices):
        BACHELOR = "BACHELOR", "Bachelor's"
        MASTER = "MASTER", "Master's"
        DOCTORATE = "DOCTORATE", "Doctorate"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="faculty")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="faculty")
    employee_no = models.CharField("Employee no.", max_length=30, unique=True)
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices)
    employment_status = models.CharField(max_length=20, choices=EmploymentStatus.choices)
    faculty_type = models.CharField(max_length=20, choices=FacultyType.choices, default=FacultyType.UNDERGRADUATE)
    academic_rank = models.CharField(max_length=20, choices=AcademicRank.choices, default=AcademicRank.INSTRUCTOR_I)
    highest_degree = models.CharField(max_length=20, choices=HighestDegree.choices)
    has_foreign_degree = models.BooleanField(default=False)
    teaches_licensure_program = models.BooleanField(default=False)
    on_study_leave = models.BooleanField(default=False)
    date_hired = models.DateField()
    contact_no = models.CharField(max_length=30, blank=True)

    objects = FacultyQuerySet.as_manager()

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name_plural = "faculty"

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        middle = f" {self.middle_name[0]}." if self.middle_name else ""
        return f"{self.first_name}{middle} {self.last_name}"

    @property
    def sortable_name(self):
        middle = f" {self.middle_name[0]}." if self.middle_name else ""
        return f"{self.last_name}, {self.first_name}{middle}"

    def get_absolute_url(self):
        return reverse("faculty:detail", args=[self.pk])
