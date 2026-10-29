"""Compliance engine tests (TC-01 … TC-08), rate calculation, and permission checks."""
import shutil
import tempfile
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from compliance.engine import compliance_rate, determine_status, evaluate_all, evaluate_faculty, rates_by_subarea
from compliance.expiry import check_expirations
from compliance.models import ComplianceStatus, ExpiryAlertSent
from documents.models import Document
from documents.storage import private_storage
from faculty.models import Department, Faculty
from notifications.models import Notification
from requirements.models import PacucoaSubArea, Requirement

Status = ComplianceStatus.Status
FAST_HASHER = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_user(username, role, department=None):
    return User.objects.create_user(username=username, password="pw-Test-123", role=role, department=department, email=f"{username}@example.com")


def make_faculty(username, department, **overrides):
    user = make_user(username, User.Role.FACULTY)
    fields = {
        "user": user,
        "department": department,
        "employee_no": f"CDK-2020-{Faculty.objects.count() + 1:04d}",
        "last_name": username.title(),
        "first_name": "Test",
        "sex": Faculty.Sex.FEMALE,
        "employment_status": Faculty.EmploymentStatus.FULL_TIME,
        "faculty_type": Faculty.FacultyType.UNDERGRADUATE,
        "highest_degree": Faculty.HighestDegree.MASTER,
        "date_hired": date(2015, 6, 1),
    }
    fields.update(overrides)
    return Faculty.objects.create(**fields)


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class FramesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="CCS", name="College of Computer Studies")
        cls.other_dept = Department.objects.create(code="CBA", name="College of Business Administration")
        cls.sub_a = PacucoaSubArea.objects.create(code="II.A", title="Academic Qualifications", sort_order=1)
        cls.sub_f = PacucoaSubArea.objects.create(code="II.F", title="Clearances", sort_order=6)
        cls.req_plain = Requirement.objects.create(subarea=cls.sub_a, name="Bachelor's diploma", sort_order=1)
        cls.req_doctoral = Requirement.objects.create(
            subarea=cls.sub_a, name="Doctoral diploma", applicability=Requirement.Applicability.GRADUATE_FACULTY, sort_order=2
        )
        cls.req_expiry = Requirement.objects.create(subarea=cls.sub_f, name="NBI clearance", has_expiry=True, sort_order=1)
        cls.faculty = make_faculty("santos", cls.dept)
        cls.today = timezone.localdate()

    def doc(self, requirement, status, expiry=None, faculty=None, version=1, is_current=True):
        return Document.objects.create(
            faculty=faculty or self.faculty,
            requirement=requirement,
            original_filename="sample.pdf",
            file_type="application/pdf",
            file_size=10,
            date_issued=self.today - timedelta(days=30),
            expiry_date=expiry,
            version_no=version,
            is_current=is_current,
            status=status,
        )

    def status_of(self, requirement, faculty=None):
        evaluate_faculty(faculty or self.faculty)
        return ComplianceStatus.objects.filter(faculty=faculty or self.faculty, requirement=requirement).first()


class ComplianceEngineTests(FramesTestCase):
    def test_tc01_no_document_is_not_complied(self):
        cs = self.status_of(self.req_plain)
        self.assertEqual(cs.status, Status.NOT_COMPLIED)
        self.assertIsNone(cs.document)

    def test_tc02_pending_is_incomplete(self):
        self.doc(self.req_plain, Document.Status.PENDING)
        self.assertEqual(self.status_of(self.req_plain).status, Status.INCOMPLETE)

    def test_tc03_resubmission_is_incomplete(self):
        self.doc(self.req_plain, Document.Status.RESUBMIT)
        self.assertEqual(self.status_of(self.req_plain).status, Status.INCOMPLETE)

    def test_rejected_is_not_complied(self):
        self.doc(self.req_plain, Document.Status.REJECTED)
        self.assertEqual(self.status_of(self.req_plain).status, Status.NOT_COMPLIED)

    def test_tc04_approved_without_expiry_is_complied(self):
        self.doc(self.req_plain, Document.Status.APPROVED)
        cs = self.status_of(self.req_plain)
        self.assertEqual(cs.status, Status.COMPLIED)
        self.assertFalse(cs.is_expiring)
        self.assertIsNone(cs.days_to_expiry)

    def test_tc05_approved_expiry_more_than_90_days_is_complied(self):
        self.doc(self.req_expiry, Document.Status.APPROVED, expiry=self.today + timedelta(days=200))
        cs = self.status_of(self.req_expiry)
        self.assertEqual(cs.status, Status.COMPLIED)
        self.assertFalse(cs.is_expiring)
        self.assertEqual(cs.days_to_expiry, 200)

    def test_tc06_approved_expiring_within_90_days_is_complied_and_flagged(self):
        self.doc(self.req_expiry, Document.Status.APPROVED, expiry=self.today + timedelta(days=45))
        cs = self.status_of(self.req_expiry)
        self.assertEqual(cs.status, Status.COMPLIED)
        self.assertTrue(cs.is_expiring)
        self.assertEqual(cs.days_to_expiry, 45)

    def test_expiry_window_boundaries(self):
        req = self.req_expiry
        at_90 = determine_status(req, Document(status=Document.Status.APPROVED, expiry_date=self.today + timedelta(days=90)), self.today)
        at_91 = determine_status(req, Document(status=Document.Status.APPROVED, expiry_date=self.today + timedelta(days=91)), self.today)
        today = determine_status(req, Document(status=Document.Status.APPROVED, expiry_date=self.today), self.today)
        self.assertTrue(at_90.is_expiring)
        self.assertFalse(at_91.is_expiring)
        self.assertEqual(today.status, Status.COMPLIED)
        self.assertTrue(today.is_expiring)

    def test_tc07_expired_is_not_complied(self):
        self.doc(self.req_expiry, Document.Status.APPROVED, expiry=self.today - timedelta(days=1))
        cs = self.status_of(self.req_expiry)
        self.assertEqual(cs.status, Status.NOT_COMPLIED)
        self.assertFalse(cs.is_expiring)
        self.assertEqual(cs.days_to_expiry, -1)

    def test_tc08_non_applicable_requirement_is_excluded(self):
        evaluate_faculty(self.faculty)
        self.assertFalse(ComplianceStatus.objects.filter(faculty=self.faculty, requirement=self.req_doctoral).exists())
        self.doc(self.req_plain, Document.Status.APPROVED)
        self.doc(self.req_expiry, Document.Status.APPROVED, expiry=self.today + timedelta(days=300))
        evaluate_faculty(self.faculty)
        # 2 applicable, both complied: the graduate-only requirement is outside numerator and denominator
        self.assertEqual(compliance_rate(ComplianceStatus.objects.filter(faculty=self.faculty)), 100.0)

    def test_applicability_follows_faculty_attributes(self):
        grad = make_faculty("reyes", self.dept, faculty_type=Faculty.FacultyType.GRADUATE)
        self.assertEqual(self.status_of(self.req_doctoral, grad).status, Status.NOT_COMPLIED)
        grad.faculty_type = Faculty.FacultyType.UNDERGRADUATE
        grad.save()  # signal re-evaluates
        self.assertFalse(ComplianceStatus.objects.filter(faculty=grad, requirement=self.req_doctoral).exists())

    def test_only_current_version_counts(self):
        self.doc(self.req_plain, Document.Status.APPROVED, version=1, is_current=False)
        self.doc(self.req_plain, Document.Status.PENDING, version=2, is_current=True)
        self.assertEqual(self.status_of(self.req_plain).status, Status.INCOMPLETE)

    def test_compliance_rate_rounds_to_two_decimals(self):
        self.doc(self.req_plain, Document.Status.APPROVED)
        self.doc(self.req_expiry, Document.Status.PENDING, expiry=self.today + timedelta(days=300))
        other = make_faculty("cruz", self.dept)
        self.doc(self.req_plain, Document.Status.APPROVED, faculty=other)
        evaluate_all()
        # 2 faculty x 2 applicable = 4 items; 2 complied -> 50%; with one more requirement 2/6 -> 33.33
        self.assertEqual(compliance_rate(ComplianceStatus.objects.all()), 50.0)
        Requirement.objects.create(subarea=self.sub_f, name="Medical clearance", has_expiry=True, sort_order=2)
        self.assertEqual(compliance_rate(ComplianceStatus.objects.all()), 33.33)
        self.assertEqual(compliance_rate(ComplianceStatus.objects.none()), 0.0)

    def test_rates_by_subarea(self):
        self.doc(self.req_plain, Document.Status.APPROVED)
        evaluate_faculty(self.faculty)
        rates = {r["code"]: r["rate"] for r in rates_by_subarea(ComplianceStatus.objects.all())}
        self.assertEqual(rates, {"II.A": 100.0, "II.F": 0.0})

    def test_rule_change_triggers_re_evaluation(self):
        evaluate_all()
        self.assertTrue(ComplianceStatus.objects.filter(requirement=self.req_expiry).exists())
        self.req_expiry.is_active = False
        self.req_expiry.save()  # signal -> evaluate_all()
        self.assertFalse(ComplianceStatus.objects.filter(requirement=self.req_expiry).exists())

    def test_upload_and_validation_re_evaluate_automatically(self):
        doc = self.doc(self.req_plain, Document.Status.PENDING)
        self.assertEqual(ComplianceStatus.objects.get(faculty=self.faculty, requirement=self.req_plain).status, Status.INCOMPLETE)
        doc.status = Document.Status.APPROVED
        doc.save()
        self.assertEqual(ComplianceStatus.objects.get(faculty=self.faculty, requirement=self.req_plain).status, Status.COMPLIED)


class ExpiryAlertTests(FramesTestCase):
    def test_alert_sent_once_per_threshold(self):
        doc = self.doc(self.req_expiry, Document.Status.APPROVED, expiry=self.today + timedelta(days=50))
        first = check_expirations(send_email=False)
        self.assertEqual(first.alerts, {60: 1})
        self.assertTrue(ExpiryAlertSent.objects.filter(document=doc, threshold=60).exists())
        self.assertTrue(ExpiryAlertSent.objects.filter(document=doc, threshold=90).exists())
        second = check_expirations(send_email=False)
        self.assertEqual(second.total_alerts, 0)
        # 20 days later it falls under the 30-day threshold -> exactly one new alert
        third = check_expirations(today=self.today + timedelta(days=25), send_email=False)
        self.assertEqual(third.alerts, {30: 1})
        self.assertEqual(Notification.objects.filter(user=self.faculty.user, type=Notification.Type.EXPIRY).count(), 2)

    def test_expired_notice_and_status(self):
        self.doc(self.req_expiry, Document.Status.APPROVED, expiry=self.today - timedelta(days=2))
        result = check_expirations(send_email=False)
        self.assertEqual(result.expired_notices, 1)
        self.assertEqual(ComplianceStatus.objects.get(faculty=self.faculty, requirement=self.req_expiry).status, Status.NOT_COMPLIED)
        self.assertEqual(check_expirations(send_email=False).expired_notices, 0)


class PermissionTests(FramesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other = make_faculty("garcia", cls.dept)
        cls.foreign = make_faculty("lim", cls.other_dept)
        cls.hr = make_user("hr", User.Role.HR_ADMIN)
        cls.sysadmin = make_user("admin", User.Role.SYS_ADMIN)
        cls.dean = make_user("dean", User.Role.AREA_CHAIR, department=cls.dept)

    def test_faculty_cannot_open_another_faculty_document(self):
        doc = self.doc(self.req_plain, Document.Status.PENDING, faculty=self.other)
        self.client.force_login(self.faculty.user)
        for name in ("documents:detail", "documents:download", "documents:preview"):
            self.assertEqual(self.client.get(reverse(name, args=[doc.pk])).status_code, 404, name)
        self.assertEqual(self.client.get(reverse("faculty:detail", args=[self.other.pk])).status_code, 404)

    def test_faculty_can_open_own_document(self):
        doc = self.doc(self.req_plain, Document.Status.PENDING)
        self.client.force_login(self.faculty.user)
        self.assertEqual(self.client.get(reverse("documents:detail", args=[doc.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("faculty:detail", args=[self.faculty.pk])).status_code, 200)

    def test_faculty_cannot_open_validation_queue(self):
        doc = self.doc(self.req_plain, Document.Status.PENDING, faculty=self.other)
        self.client.force_login(self.faculty.user)
        self.assertEqual(self.client.get(reverse("documents:validation_queue")).status_code, 403)
        self.assertEqual(self.client.get(reverse("documents:validate", args=[doc.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("compliance:matrix")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 403)

    def test_non_sysadmin_cannot_edit_rules(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse("requirements:list")).status_code, 200)  # read-only view
        self.assertEqual(self.client.get(reverse("requirements:requirement_edit", args=[self.req_plain.pk])).status_code, 403)
        response = self.client.post(reverse("requirements:requirement_create"), {"subarea": self.sub_a.pk, "name": "Hack", "applicability": "ALL", "sort_order": 9})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Requirement.objects.filter(name="Hack").exists())
        self.assertEqual(self.client.post(reverse("requirements:requirement_toggle", args=[self.req_plain.pk])).status_code, 403)

    def test_sysadmin_can_edit_rules(self):
        self.client.force_login(self.sysadmin)
        response = self.client.post(
            reverse("requirements:requirement_edit", args=[self.req_plain.pk]),
            {"subarea": self.sub_a.pk, "name": "Bachelor's diploma and TOR", "applicability": "ALL", "is_mandatory": "on", "is_active": "on", "sort_order": 1},
        )
        self.assertRedirects(response, reverse("requirements:list"))
        self.req_plain.refresh_from_db()
        self.assertEqual(self.req_plain.name, "Bachelor's diploma and TOR")

    def test_area_chair_scope_limits_departments(self):
        doc = self.doc(self.req_plain, Document.Status.PENDING, faculty=self.foreign)
        self.client.force_login(self.dean)
        self.assertEqual(self.client.get(reverse("documents:detail", args=[doc.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("faculty:detail", args=[self.foreign.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("faculty:detail", args=[self.faculty.pk])).status_code, 200)

    def test_staff_pages_render(self):
        self.doc(self.req_plain, Document.Status.APPROVED)
        self.doc(self.req_expiry, Document.Status.APPROVED, expiry=self.today + timedelta(days=20))
        self.client.force_login(self.hr)
        for name in ("dashboard:index", "compliance:matrix", "compliance:expiring", "faculty:list", "documents:validation_queue", "reports:index"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        pdf = self.client.get(reverse("reports:matrix"), {"mx-format": "pdf"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        xlsx = self.client.get(reverse("reports:audit_summary"), {"au-format": "xlsx"})
        self.assertIn("spreadsheetml", xlsx["Content-Type"])

    def test_login_required(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class UploadWorkflowTests(FramesTestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="frames-test-")
        self.override = override_settings(PRIVATE_MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def upload(self, content=b"%PDF-1.4 test document", name="diploma.pdf", content_type="application/pdf", **extra):
        data = {
            "requirement": self.req_plain.pk,
            "file": SimpleUploadedFile(name, content, content_type=content_type),
            "date_issued": (self.today - timedelta(days=10)).isoformat(),
        }
        data.update(extra)
        return self.client.post(reverse("documents:upload"), data)

    def test_upload_is_encrypted_versioned_and_downloadable(self):
        self.client.force_login(self.faculty.user)
        self.assertEqual(self.upload().status_code, 302)
        first = Document.objects.get(faculty=self.faculty, requirement=self.req_plain)
        self.assertEqual((first.version_no, first.status, first.is_current), (1, Document.Status.PENDING, True))
        raw = private_storage.read_raw(first.file.name)
        self.assertNotIn(b"%PDF", raw)  # encrypted at rest
        response = self.client.get(reverse("documents:download", args=[first.pk]))
        self.assertEqual(response.content, b"%PDF-1.4 test document")

        self.upload(content=b"%PDF-1.4 second version")
        versions = Document.objects.filter(faculty=self.faculty, requirement=self.req_plain).order_by("version_no")
        self.assertEqual([(d.version_no, d.is_current) for d in versions], [(1, False), (2, True)])
        self.assertEqual(ComplianceStatus.objects.get(faculty=self.faculty, requirement=self.req_plain).status, Status.INCOMPLETE)

    def test_filesystem_backend_also_encrypts(self):
        with override_settings(PRIVATE_STORAGE="filesystem"):
            self.client.force_login(self.faculty.user)
            self.upload()
            doc = Document.objects.get()
            with open(private_storage.path(doc.file.name), "rb") as fh:
                self.assertNotIn(b"%PDF", fh.read())
            self.assertEqual(self.client.get(reverse("documents:download", args=[doc.pk])).content, b"%PDF-1.4 test document")

    def test_upload_rejects_mismatched_content(self):
        self.client.force_login(self.faculty.user)
        response = self.upload(content=b"\x89PNG\r\n\x1a\nnot a pdf", name="fake.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.exists())
        response = self.upload(content=b"MZ executable", name="virus.exe", content_type="application/octet-stream")
        self.assertFalse(Document.objects.exists())

    def test_expiry_date_required_for_expiring_requirement(self):
        self.client.force_login(self.faculty.user)
        response = self.upload(requirement=self.req_expiry.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "please enter it")
        self.assertFalse(Document.objects.exists())

    def test_faculty_cannot_upload_non_applicable_requirement(self):
        self.client.force_login(self.faculty.user)
        self.upload(requirement=self.req_doctoral.pk)
        self.assertFalse(Document.objects.exists())

    def test_validation_notifies_faculty(self):
        hr = make_user("hr2", User.Role.HR_ADMIN)
        self.client.force_login(self.faculty.user)
        self.upload()
        doc = Document.objects.get()
        self.client.force_login(hr)
        response = self.client.post(reverse("documents:validate", args=[doc.pk]), {"decision": "RESUBMIT", "remarks": ""})
        self.assertEqual(response.status_code, 200)  # remarks required
        self.client.post(reverse("documents:validate", args=[doc.pk]), {"decision": "APPROVED", "remarks": ""})
        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.APPROVED)
        self.assertTrue(Notification.objects.filter(user=self.faculty.user, type=Notification.Type.VALIDATION).exists())
        self.assertEqual(ComplianceStatus.objects.get(faculty=self.faculty, requirement=self.req_plain).status, Status.COMPLIED)
