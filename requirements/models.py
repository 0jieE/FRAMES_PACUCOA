"""PACUCOA Area II sub-areas (II.A-II.F) and configurable requirement rules."""
from django.db import models


class PacucoaSubArea(models.Model):
    code = models.CharField(max_length=10, unique=True, help_text="e.g. II.A")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "PACUCOA sub-area"

    def __str__(self):
        return f"{self.code} {self.title}"

    @property
    def letter(self):
        return self.code.split(".")[-1]


class RequirementQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, subarea__isnull=False)

    def ordered(self):
        return self.select_related("subarea").order_by("subarea__sort_order", "subarea__code", "sort_order", "pk")


class Requirement(models.Model):
    class Applicability(models.TextChoices):
        ALL = "ALL", "All faculty"
        GRADUATE_FACULTY = "GRADUATE_FACULTY", "Graduate faculty only"
        FOREIGN_DEGREE = "FOREIGN_DEGREE", "Faculty with foreign degree"
        LICENSURE_PROGRAM = "LICENSURE_PROGRAM", "Faculty teaching licensure programs"
        STUDY_LEAVE = "STUDY_LEAVE", "Faculty on study leave"

    subarea = models.ForeignKey(PacucoaSubArea, on_delete=models.PROTECT, related_name="requirements")
    name = models.CharField(max_length=255)
    documentary_basis = models.TextField(blank=True, help_text="Evidence PACUCOA accreditors look for.")
    is_mandatory = models.BooleanField(default=True)
    has_expiry = models.BooleanField(default=False, help_text="Document carries an expiry / validity date.")
    applicability = models.CharField(max_length=30, choices=Applicability.choices, default=Applicability.ALL)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    objects = RequirementQuerySet.as_manager()

    class Meta:
        ordering = ["subarea__sort_order", "sort_order", "pk"]

    def __str__(self):
        return f"{self.subarea.code} · {self.name}"

    def applies_to(self, faculty):
        rule = self.applicability
        if rule == self.Applicability.ALL:
            return True
        if rule == self.Applicability.GRADUATE_FACULTY:
            return faculty.faculty_type == faculty.FacultyType.GRADUATE
        if rule == self.Applicability.FOREIGN_DEGREE:
            return faculty.has_foreign_degree
        if rule == self.Applicability.LICENSURE_PROGRAM:
            return faculty.teaches_licensure_program
        if rule == self.Applicability.STUDY_LEAVE:
            return faculty.on_study_leave
        return False

    @property
    def mandatory_label(self):
        if not self.is_mandatory:
            return "Optional"
        return "Yes" if self.applicability == self.Applicability.ALL else "Conditional"
