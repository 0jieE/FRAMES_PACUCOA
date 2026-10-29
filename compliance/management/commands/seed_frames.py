"""Seeder: departments, sub-areas, 20 requirements, users, 45 faculty, documents, validations, notifications, audit logs.

    python manage.py seed_frames --reset

Uses a fixed random seed, so the same data (relative to today's date) is produced every run.
"""
import random
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from compliance import signals as compliance_signals
from compliance.engine import compliance_rate, evaluate_all, rates_by_department, rates_by_subarea
from compliance.models import ComplianceStatus, ExpiryAlertSent
from documents.models import Document, StoredFile, Validation
from faculty.models import Department, Faculty
from notifications.models import Notification
from reports.pdf import render_sample_document
from requirements.models import PacucoaSubArea, Requirement

RANDOM_SEED = 2026
DEMO_PASSWORD = "Frames@2026"

# ---------------------------------------------------------------- editable sample data
# (code, name, dean full name, dean first name, dean last name)
DEPARTMENTS = [
    ("CCS", "College of Computer Studies", "Dr. Ramon B. Dela Cruz", "Ramon", "Dela Cruz"),
    ("CBA", "College of Business Administration", "Dr. Maricel T. Villanueva", "Maricel", "Villanueva"),
    ("CTE", "College of Teacher Education", "Dr. Josefina A. Manalo", "Josefina", "Manalo"),
    ("CCJE", "College of Criminal Justice Education", "Dr. Rolando P. Agustin", "Rolando", "Agustin"),
    ("CAS", "College of Arts and Sciences", "Dr. Teresita M. Gallardo", "Teresita", "Gallardo"),
]
# Share of applicable requirements complied by "typical" faculty of each department
DEPARTMENT_QUALITY = {"CCS": 0.86, "CBA": 0.76, "CTE": 0.73, "CCJE": 0.58, "CAS": 0.68}

SUBAREAS = [
    ("II.A", "Academic Qualifications and Licensure", "Degrees, vertical alignment, equivalency of foreign degrees, and professional licenses."),
    ("II.B", "Appointment, Rank and Tenure", "Employment contracts, personal records, service records, and academic rank."),
    ("II.C", "Faculty Development", "Development plans, trainings and seminars, and study-leave / scholarship agreements."),
    ("II.D", "Teaching Assignment and Performance", "Teaching load, performance evaluation, and instructional materials."),
    ("II.E", "Research, Publications and Extension", "Scholarly output, research reports, and community extension."),
    ("II.F", "Faculty Welfare and Clearances", "Clearances and health records required for continued employment."),
]

A, G, F, L, S = (
    Requirement.Applicability.ALL,
    Requirement.Applicability.GRADUATE_FACULTY,
    Requirement.Applicability.FOREIGN_DEGREE,
    Requirement.Applicability.LICENSURE_PROGRAM,
    Requirement.Applicability.STUDY_LEAVE,
)
# (sub-area, key, name, has_expiry, mandatory, applicability, validity days, documentary basis)
REQUIREMENTS = [
    ("II.A", "bachelor", "Bachelor's diploma and transcript of records", False, True, A, None, "Diploma and official TOR from the degree-granting institution."),
    ("II.A", "master", "Master's diploma and transcript (vertical alignment)", False, True, A, None, "Master's degree aligned with the subjects taught (CHED minimum qualification)."),
    ("II.A", "doctoral", "Doctoral diploma and transcript", False, True, G, None, "Required of faculty teaching in graduate programs."),
    ("II.A", "cav", "CAV / degree equivalency", False, True, F, None, "CHED Certification, Authentication and Verification or equivalency for foreign degrees."),
    ("II.A", "prc", "PRC license / certificate of registration", True, True, L, 1095, "Valid PRC ID / COR for faculty teaching licensure programs."),
    ("II.B", "contract", "Appointment contract / terms of employment", True, True, A, 365, "Signed appointment or contract for the current school year."),
    ("II.B", "pds", "Updated curriculum vitae / personal data sheet", False, True, A, None, "CV or PDS updated within the current school year."),
    ("II.B", "service", "Service record / certificate of employment", False, True, A, None, "Service record issued by HR."),
    ("II.B", "rank", "Certificate of academic rank and promotion", False, True, A, None, "Latest notice of rank / promotion approved by the Board."),
    ("II.C", "fdp", "Annual faculty development participation plan", True, True, A, 365, "Approved individual faculty development plan for the year."),
    ("II.C", "seminars", "Seminar and training certificates (past 3 years)", False, True, A, None, "Certificates of participation in relevant seminars and trainings."),
    ("II.C", "studyleave", "Study leave contract / scholarship agreement", True, True, S, 730, "Signed study-leave contract or scholarship agreement."),
    ("II.D", "load", "Official teaching load assignment form", True, True, A, 180, "Teaching load for the current semester signed by the dean."),
    ("II.D", "ratings", "Summarized performance ratings (student/peer/dean)", True, True, A, 365, "Consolidated faculty performance evaluation for the last term."),
    ("II.D", "syllabi", "Sample course syllabi and instructional materials", True, True, A, 365, "OBE syllabi and instructional materials reviewed this year."),
    ("II.E", "publications", "Refereed publications / books authored", False, True, A, None, "Copies of refereed articles, books, or modules authored."),
    ("II.E", "research", "Completed institutional or funded research reports", False, True, A, None, "Completed research reports with approval sheets."),
    ("II.E", "extension", "Community extension certificates and reports", False, True, A, None, "Certificates and narrative reports of extension activities."),
    ("II.F", "nbi", "NBI / police clearance", True, True, A, 365, "Valid NBI or police clearance."),
    ("II.F", "medical", "Annual medical / health clearance", True, True, A, 365, "Annual physical examination and health clearance."),
]

FEMALE_NAMES = [
    "Maria", "Rosalie", "Jocelyn", "Marites", "Analyn", "Cherry", "Rowena", "Glenda", "Liezl", "Kristine", "Janice",
    "Rhodora", "Marivic", "Hazel", "Divina", "Charisse", "Sheila", "Arlene", "Mylene", "Lourdes", "Evelyn", "Jennifer",
    "Ma. Theresa", "Grace", "Rachelle",
]
MALE_NAMES = [
    "Jose", "Ramil", "Rodel", "Arnel", "Jomar", "Reynaldo", "Edgar", "Ronald", "Dennis", "Noel", "Alvin", "Jerome",
    "Rogelio", "Danilo", "Ariel", "Nestor", "Marlon", "Christian", "Kevin", "Jayson", "Renato", "Benjie", "Romeo", "Niño",
]
LAST_NAMES = [
    "Abellana", "Agbayani", "Alonzo", "Baguio", "Bacus", "Caballero", "Cabahug", "Catalan", "Dagohoy", "Dalisay",
    "Delos Reyes", "Enriquez", "Escobar", "Fajardo", "Galvez", "Gonzaga", "Ibañez", "Labrador", "Lagura", "Lumantas",
    "Macaraeg", "Magbanua", "Mangubat", "Montejo", "Navarro", "Ocampo", "Ompad", "Pagaduan", "Palma", "Pepito",
    "Quiñones", "Ramos", "Rosales", "Sabanal", "Salazar", "Sumampong", "Tabanao", "Tagaro", "Tampus", "Ubaldo",
    "Valdez", "Villaflor", "Yap", "Zamora", "Alcantara", "Bautista", "Castillo", "Dumalagan", "Estrada", "Sarmiento",
]

STAFF_USERS = [
    # username, first, last, role, department code (Area Chair scope)
    ("sysadmin", "Kenneth", "Ybañez", User.Role.SYS_ADMIN, None),
    ("hr.admin1", "Lorna", "Sumagaysay", User.Role.HR_ADMIN, None),
    ("hr.admin2", "Arnel", "Pasaporte", User.Role.HR_ADMIN, None),
    ("hr.admin3", "Cherry Mae", "Lumanog", User.Role.HR_ADMIN, None),
    ("area.chair", "Evangeline", "Sarmiento", User.Role.AREA_CHAIR, None),
]

APPROVE_REMARKS = ["", "", "Verified against the original.", "Complete and valid.", "Authenticated copy received.", "OK — matches HR records."]
RESUBMIT_REMARKS = [
    "Transcript page 2 is unreadable; please rescan.",
    "Please upload the complete document including the back page.",
    "Certificate is not signed by the issuing officer; please submit a signed copy.",
    "Scanned copy is cropped; the registration number is cut off.",
    "Please submit the certified true copy, not a photocopy.",
    "Date of issue is not visible; please rescan at a higher resolution.",
]
REJECT_REMARKS = [
    "Document does not match the requirement (a certificate of attendance was submitted instead).",
    "The clearance submitted belongs to a different person.",
    "Document was already expired at the time of submission.",
    "Uploaded file is a blank page.",
    "Certificates are older than 3 years and do not meet the requirement.",
]

# Compliance cases produced by the seeder
NOEXP, FAR, EXP30, EXP60, EXP90, EXPIRED, PENDING, RESUBMIT, REJECTED, NONE = (
    "approved, no expiry", "approved, expiry > 90 days", "approved, expiring <= 30 days", "approved, expiring 31-60 days",
    "approved, expiring 61-90 days", "approved, already expired", "pending", "returned for re-submission", "rejected", "no upload",
)


@dataclass
class FacultySpec:
    dept: str
    slot: int
    employment: str
    faculty_type: str
    degree: str
    foreign: bool
    licensure: bool
    study_leave: bool
    profile: str  # model / weak / normal


def slugify_username(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(ch for ch in text.lower() if ch.isalnum())


class Command(BaseCommand):
    help = "Seed FRAMES with realistic, reproducible demo data. Use --reset to wipe existing FRAMES data first."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing FRAMES data before seeding.")

    # ------------------------------------------------------------------ entry point
    def handle(self, *args, **options):
        self.rng = random.Random(RANDOM_SEED)
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.case_counts = Counter()

        if options["reset"]:
            self.reset()
        elif Department.objects.exists() or Faculty.objects.exists():
            raise CommandError("FRAMES data already exists. Run with --reset to wipe and re-seed.")

        with compliance_signals.suspended(), transaction.atomic():
            self.password_hash = make_password(DEMO_PASSWORD)
            self.create_departments()
            self.create_rules()
            self.create_staff()
            self.create_faculty()
            self.create_documents()
            self.create_notifications()
            self.create_audit_logs()
        evaluate_all()
        self.print_summary()

    # ------------------------------------------------------------------ reset
    def reset(self):
        self.stdout.write("Resetting FRAMES data...")
        with compliance_signals.suspended(), transaction.atomic():
            AuditLog.objects.all().delete()
            Notification.objects.all().delete()
            ExpiryAlertSent.objects.all().delete()
            ComplianceStatus.objects.all().delete()
            Validation.objects.all().delete()
            Document.objects.all().delete()
            StoredFile.objects.all().delete()
            Faculty.objects.all().delete()
            Requirement.objects.all().delete()
            PacucoaSubArea.objects.all().delete()
            # keep manually created superusers (e.g. from createsuperuser)
            User.objects.exclude(Q(is_superuser=True) & ~Q(username="sysadmin")).delete()
            Department.objects.all().delete()
        doc_dir = Path(settings.PRIVATE_MEDIA_ROOT) / "documents"
        if doc_dir.exists():
            shutil.rmtree(doc_dir)

    # ------------------------------------------------------------------ reference data
    def create_departments(self):
        self.departments = {}
        for code, name, dean, *_ in DEPARTMENTS:
            self.departments[code] = Department.objects.create(code=code, name=name, dean_name=dean)

    def create_rules(self):
        self.subareas = {}
        for i, (code, title, description) in enumerate(SUBAREAS, start=1):
            self.subareas[code] = PacucoaSubArea.objects.create(code=code, title=title, description=description, sort_order=i)
        self.requirements, self.validity = {}, {}
        order = Counter()
        for sub, key, name, has_expiry, mandatory, applicability, validity, basis in REQUIREMENTS:
            order[sub] += 1
            req = Requirement.objects.create(
                subarea=self.subareas[sub],
                name=name,
                documentary_basis=basis,
                is_mandatory=mandatory,
                has_expiry=has_expiry,
                applicability=applicability,
                sort_order=order[sub],
            )
            self.requirements[key] = req
            self.validity[req.pk] = validity
        self.req_keys = {req.pk: key for key, req in self.requirements.items()}

    def _user(self, username, first, last, role, department=None, superuser=False):
        existing = User.objects.filter(username=username).first()
        if existing:  # a kept superuser with the same name
            return existing
        return User.objects.create(
            username=username,
            first_name=first,
            last_name=last,
            email=f"{username}@cdk.edu.ph",
            role=role,
            department=department,
            password=self.password_hash,
            is_staff=superuser,
            is_superuser=superuser,
            date_joined=self.now - timedelta(days=400),
        )

    def create_staff(self):
        self.staff = {}
        for username, first, last, role, dept in STAFF_USERS:
            self.staff[username] = self._user(
                username, first, last, role, self.departments.get(dept), superuser=username == "sysadmin"
            )
        self.deans = {}
        for code, _name, _dean, first, last in DEPARTMENTS:
            self.deans[code] = self._user(f"dean.{code.lower()}", first, last, User.Role.AREA_CHAIR, self.departments[code])
        self.hr_admins = [self.staff["hr.admin1"], self.staff["hr.admin2"], self.staff["hr.admin3"]]

    # ------------------------------------------------------------------ faculty
    def faculty_specs(self):
        graduate_slots = {"CCS": [0], "CBA": [0, 1], "CTE": [0, 1], "CCJE": [0], "CAS": [0, 1]}
        doctor_slots = {"CCS": [0], "CBA": [0, 1], "CTE": [0], "CCJE": [0], "CAS": [0]}
        licensure_slots = {"CTE": range(0, 7), "CCJE": range(0, 5)}
        foreign = {("CCS", 0), ("CBA", 0), ("CAS", 2)}
        study_leave = {("CCS", 2), ("CAS", 3)}
        bachelor = {("CCS", 5), ("CCJE", 5)}
        model = {("CCS", 0), ("CBA", 1), ("CTE", 2), ("CAS", 0), ("CCJE", 1)}
        weak = {("CCJE", 7), ("CCJE", 8), ("CAS", 8), ("CBA", 8), ("CTE", 8)}
        specs = []
        for code, *_ in DEPARTMENTS:
            for slot in range(9):
                key = (code, slot)
                graduate = slot in graduate_slots.get(code, [])
                if slot in doctor_slots.get(code, []):
                    degree = Faculty.HighestDegree.DOCTORATE
                elif slot >= 7 or key in bachelor:
                    degree = Faculty.HighestDegree.BACHELOR
                else:
                    degree = Faculty.HighestDegree.MASTER
                specs.append(
                    FacultySpec(
                        dept=code,
                        slot=slot,
                        employment=Faculty.EmploymentStatus.FULL_TIME if slot < 6 else Faculty.EmploymentStatus.PART_TIME,
                        faculty_type=Faculty.FacultyType.GRADUATE if graduate else Faculty.FacultyType.UNDERGRADUATE,
                        degree=degree,
                        foreign=key in foreign,
                        licensure=slot in licensure_slots.get(code, []),
                        study_leave=key in study_leave,
                        profile="model" if key in model else ("weak" if key in weak else "normal"),
                    )
                )
        return specs

    def _rank_and_hire(self, degree):
        rng = self.rng
        R = Faculty.AcademicRank
        if degree == Faculty.HighestDegree.DOCTORATE:
            year = rng.randint(2005, 2012)
            rank = rng.choice([R.ASSOC_PROF_II, R.ASSOC_PROF_III, R.ASSOC_PROF_IV, R.ASSOC_PROF_V, R.PROFESSOR])
        elif degree == Faculty.HighestDegree.MASTER:
            year = rng.randint(2008, 2021)
            rank = rng.choice([R.INSTRUCTOR_III, R.ASST_PROF_I, R.ASST_PROF_II, R.ASST_PROF_III, R.ASST_PROF_IV, R.ASSOC_PROF_I])
        else:
            year = rng.randint(2016, 2025)
            rank = rng.choice([R.INSTRUCTOR_I, R.INSTRUCTOR_I, R.INSTRUCTOR_II])
        hired = date(year, rng.choice([6, 6, 7, 8, 11, 1]), rng.randint(1, 28))
        return rank, min(hired, self.today - timedelta(days=120))

    def create_faculty(self):
        rng = self.rng
        specs = self.faculty_specs()
        used_names, used_usernames, used_numbers = set(), set(), set()
        self.faculty = []
        for spec in specs:
            while True:
                sex = rng.choice(["F", "M"])
                first = rng.choice(FEMALE_NAMES if sex == "F" else MALE_NAMES)
                last = rng.choice(LAST_NAMES)
                username = f"{slugify_username(first)}.{slugify_username(last)}"
                if (first, last) not in used_names and username not in used_usernames:
                    break
            used_names.add((first, last))
            used_usernames.add(username)
            middle = rng.choice([n for n in LAST_NAMES if n != last])
            rank, hired = self._rank_and_hire(spec.degree)
            while True:
                emp_no = f"CDK-{hired.year}-{rng.randint(1, 999):04d}"
                if emp_no not in used_numbers:
                    break
            used_numbers.add(emp_no)
            user = self._user(username, first, last, User.Role.FACULTY)
            user.date_joined = timezone.make_aware(datetime.combine(hired, time(8, 0)))
            user.save(update_fields=["date_joined"])
            faculty = Faculty.objects.create(
                user=user,
                department=self.departments[spec.dept],
                employee_no=emp_no,
                last_name=last,
                first_name=first,
                middle_name=middle,
                sex=sex,
                employment_status=spec.employment,
                faculty_type=spec.faculty_type,
                academic_rank=rank,
                highest_degree=spec.degree,
                has_foreign_degree=spec.foreign,
                teaches_licensure_program=spec.licensure,
                on_study_leave=spec.study_leave,
                date_hired=hired,
                contact_no=f"09{rng.randint(10, 99)}-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}",
            )
            faculty.spec = spec
            self.faculty.append(faculty)

    # ------------------------------------------------------------------ documents
    def _eligible(self, faculty, req):
        """Whether the faculty member *can* comply (bachelor-only faculty cannot have a master's diploma...)."""
        key = self.req_keys[req.pk]
        if key == "master" and faculty.highest_degree == Faculty.HighestDegree.BACHELOR:
            return False
        if key == "doctoral" and faculty.highest_degree != Faculty.HighestDegree.DOCTORATE:
            return False
        return True

    def plan_outcomes(self, faculty, applicable):
        rng = self.rng
        eligible = [r for r in applicable if self._eligible(faculty, r)]
        n = len(applicable)
        profile = faculty.spec.profile
        if profile == "model":
            complied = set(r.pk for r in eligible)
        else:
            if profile == "weak":
                k = int(n * rng.uniform(0.12, 0.34))
            else:
                p = DEPARTMENT_QUALITY[faculty.spec.dept] + rng.uniform(-0.13, 0.13)
                k = round(min(max(p, 0.42), 0.97) * n)
                k = min(k, n - 1)  # only the model faculty are 100%
            k = min(k, len(eligible))
            complied = set(r.pk for r in rng.sample(eligible, k))
        outcomes = {}
        for req in applicable:
            if req.pk in complied:
                if req.has_expiry:
                    outcomes[req.pk] = rng.choices([FAR, EXP30, EXP60, EXP90], weights=[60, 13, 13, 14])[0]
                else:
                    outcomes[req.pk] = NOEXP
            elif not self._eligible(faculty, req):
                outcomes[req.pk] = rng.choices([NONE, PENDING], weights=[85, 15])[0]
            elif req.has_expiry:
                outcomes[req.pk] = rng.choices([NONE, PENDING, RESUBMIT, REJECTED, EXPIRED], weights=[22, 20, 15, 10, 33])[0]
            else:
                outcomes[req.pk] = rng.choices([NONE, PENDING, RESUBMIT, REJECTED], weights=[40, 27, 19, 14])[0]
        return outcomes

    def _dates_for(self, faculty, req, outcome):
        """Return (date_issued, expiry_date) for the current version."""
        rng, today = self.rng, self.today
        validity = self.validity[req.pk]
        if not req.has_expiry:
            key = self.req_keys[req.pk]
            if key in ("bachelor", "master", "doctoral", "cav"):
                issued = faculty.date_hired - timedelta(days=rng.randint(200, 2600))
            else:
                issued = today - timedelta(days=rng.randint(30, 900))
            return issued, None
        if outcome == FAR:
            expiry = today + timedelta(days=rng.randint(95, validity - 15))
        elif outcome == EXP30:
            expiry = today + timedelta(days=rng.randint(2, 30))
        elif outcome == EXP60:
            expiry = today + timedelta(days=rng.randint(31, 60))
        elif outcome == EXP90:
            expiry = today + timedelta(days=rng.randint(61, 90))
        elif outcome == EXPIRED:
            expiry = today - timedelta(days=rng.randint(3, 160))
        else:  # pending / re-submit / rejected: a fresh credential
            expiry = today + timedelta(days=rng.randint(min(120, validity - 20), validity - 10))
        return expiry - timedelta(days=validity), expiry

    def _uploaded_at(self, issued, recent=False):
        rng = self.rng
        if recent:
            days_ago = rng.randint(1, 18)
        else:
            days_ago = rng.randint(12, 170)
        moment = self.now - timedelta(days=days_ago, hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
        issued_dt = timezone.make_aware(datetime.combine(issued, time(9, 0)))
        if moment < issued_dt:
            span = max(1, (self.now - issued_dt).days)
            moment = issued_dt + timedelta(days=rng.randint(0, min(span, 14)), hours=rng.randint(1, 8))
        return min(moment, self.now - timedelta(hours=2))

    def _validator(self, faculty):
        rng = self.rng
        if rng.random() < 0.6:
            return rng.choice(self.hr_admins)
        return rng.choice([self.deans[faculty.spec.dept], self.staff["area.chair"]])

    def _make_document(self, faculty, req, version, status, issued, expiry, uploaded_at, is_current):
        key = self.req_keys[req.pk]
        filename = f"{key}_{slugify_username(faculty.last_name)}_v{version}.pdf"
        details = [f"Employee no.: {faculty.employee_no}", f"Department: {faculty.department.name}"]
        if issued:
            details.append(f"Date issued: {issued:%B %d, %Y}")
        if expiry:
            details.append(f"Valid until: {expiry:%B %d, %Y}")
        details.append(f"Version {version}")
        pdf = render_sample_document(req.name, faculty.full_name, details)
        doc = Document(
            faculty=faculty,
            requirement=req,
            original_filename=filename,
            file_type="application/pdf",
            file_size=len(pdf),
            date_issued=issued,
            expiry_date=expiry,
            version_no=version,
            is_current=is_current,
            status=status,
            uploaded_by=faculty.user,
            uploaded_at=uploaded_at,
        )
        doc.file.save(filename, ContentFile(pdf), save=False)  # encrypted by the private storage
        doc.save()
        if status != Document.Status.PENDING:
            remarks_pool = {
                Document.Status.APPROVED: APPROVE_REMARKS,
                Document.Status.RESUBMIT: RESUBMIT_REMARKS,
                Document.Status.REJECTED: REJECT_REMARKS,
            }[status]
            validated_at = min(uploaded_at + timedelta(days=self.rng.randint(1, 6), hours=self.rng.randint(1, 6)), self.now - timedelta(hours=1))
            Validation.objects.create(
                document=doc,
                validated_by=self._validator(faculty),
                decision=status,
                remarks=self.rng.choice(remarks_pool),
                validated_at=validated_at,
            )
        return doc

    def create_documents(self):
        rng = self.rng
        all_reqs = list(Requirement.objects.active().ordered())
        self.history_cells = 0
        status_for = {
            NOEXP: Document.Status.APPROVED, FAR: Document.Status.APPROVED, EXP30: Document.Status.APPROVED,
            EXP60: Document.Status.APPROVED, EXP90: Document.Status.APPROVED, EXPIRED: Document.Status.APPROVED,
            PENDING: Document.Status.PENDING, RESUBMIT: Document.Status.RESUBMIT, REJECTED: Document.Status.REJECTED,
        }
        for faculty in self.faculty:
            applicable = [r for r in all_reqs if r.applies_to(faculty)]
            outcomes = self.plan_outcomes(faculty, applicable)
            for req in applicable:
                outcome = outcomes[req.pk]
                self.case_counts[outcome] += 1
                if outcome == NONE:
                    continue
                issued, expiry = self._dates_for(faculty, req, outcome)
                uploaded = self._uploaded_at(issued, recent=outcome == PENDING)

                # Version history: earlier submissions that were returned / rejected, or a previous cycle.
                prior = []
                if rng.random() < 0.13:
                    count = 2 if rng.random() < 0.35 else 1
                    for i in range(count):
                        if req.has_expiry and outcome in (FAR, EXP30, EXP60, EXP90, EXPIRED) and i == 0 and rng.random() < 0.5:
                            # previous validity cycle, approved then expired
                            validity = self.validity[req.pk]
                            prior.append((Document.Status.APPROVED, issued - timedelta(days=validity), issued))
                        else:
                            prior.append((rng.choice([Document.Status.RESUBMIT, Document.Status.RESUBMIT, Document.Status.REJECTED]), issued, expiry))
                    prior.reverse()
                version = 1
                if prior:
                    self.history_cells += 1
                    for idx, (status, p_issued, p_expiry) in enumerate(prior):
                        gap = (len(prior) - idx) * rng.randint(12, 35)
                        p_uploaded = uploaded - timedelta(days=gap)
                        p_issued_dt = timezone.make_aware(datetime.combine(p_issued, time(9, 0)))
                        if status == Document.Status.APPROVED:
                            p_uploaded = p_issued_dt + timedelta(days=rng.randint(1, 10))
                        else:
                            p_uploaded = min(max(p_uploaded, p_issued_dt + timedelta(hours=idx + 1)), uploaded - timedelta(hours=len(prior) - idx))
                        self._make_document(faculty, req, version, status, p_issued, p_expiry, p_uploaded, False)
                        version += 1
                self._make_document(faculty, req, version, status_for[outcome], issued, expiry, uploaded, True)

    # ------------------------------------------------------------------ notifications
    def create_notifications(self):
        rng = self.rng
        items = []
        validations = list(
            Validation.objects.select_related("document__faculty__user", "document__requirement").order_by("-validated_at")[:150]
        )
        rng.shuffle(validations)
        label = {"APPROVED": "was APPROVED", "REJECTED": "was REJECTED", "RESUBMIT": "needs RE-SUBMISSION"}
        for v in validations[:32]:
            doc = v.document
            msg = f"Your document '{doc.requirement.name}' (v{doc.version_no}) {label[v.decision]}."
            if v.remarks:
                msg += f" Remarks: {v.remarks}"
            items.append(Notification(user=doc.faculty.user, type=Notification.Type.VALIDATION, message=msg,
                                      link=reverse("documents:detail", args=[doc.pk]), created_at=v.validated_at))

        pending = list(Document.objects.filter(status=Document.Status.PENDING, is_current=True).select_related("faculty__department", "requirement"))
        rng.shuffle(pending)
        for doc in pending[:16]:
            recipient = rng.choice(self.hr_admins + [self.deans[doc.faculty.department.code], self.staff["area.chair"]])
            verb = "re-submitted" if doc.version_no > 1 else "uploaded"
            items.append(Notification(user=recipient, type=Notification.Type.UPLOAD,
                                      message=f"{doc.faculty.full_name} ({doc.faculty.department.code}) {verb} '{doc.requirement.name}' (v{doc.version_no}).",
                                      link=reverse("documents:validate", args=[doc.pk]), created_at=doc.uploaded_at + timedelta(minutes=1)))

        thresholds = sorted(settings.EXPIRY_ALERT_DAYS)
        expiring = list(
            Document.objects.filter(is_current=True, status=Document.Status.APPROVED, requirement__has_expiry=True,
                                    expiry_date__gte=self.today, expiry_date__lte=self.today + timedelta(days=90))
            .select_related("faculty__user", "requirement").order_by("expiry_date")
        )
        rng.shuffle(expiring)
        for doc in expiring[: 60 - len(items)]:
            days_then = (doc.expiry_date - self.today).days + rng.randint(0, 3)
            due = next((t for t in thresholds if days_then <= t), thresholds[-1])
            for t in thresholds:
                if t >= due:
                    ExpiryAlertSent.objects.get_or_create(document=doc, threshold=t)
            items.append(Notification(user=doc.faculty.user, type=Notification.Type.EXPIRY,
                                      message=f"Your '{doc.requirement.name}' expires in {days_then} days ({doc.expiry_date:%b %d, %Y}). Please prepare a renewed copy.",
                                      link=reverse("documents:detail", args=[doc.pk]),
                                      created_at=self.now - timedelta(days=rng.randint(0, 3), hours=rng.randint(1, 8))))
        items = items[:60]
        items.sort(key=lambda n: n.created_at)
        for i, n in enumerate(items):
            # older notifications have been read; the most recent ~40% are unread
            n.is_read = i < len(items) * 0.6 and rng.random() < 0.9
        Notification.objects.bulk_create(items)
        self.notification_count = len(items)

    # ------------------------------------------------------------------ audit log
    def create_audit_logs(self):
        rng = self.rng
        start = self.now - timedelta(days=60)
        staff_users = list(self.staff.values()) + list(self.deans.values())
        faculty_users = [f.user for f in self.faculty]
        docs = list(Document.objects.filter(uploaded_at__gte=start).select_related("faculty", "requirement"))
        all_docs = list(Document.objects.select_related("faculty", "requirement")[:400])
        validations = list(Validation.objects.filter(validated_at__gte=start).select_related("document__faculty", "document__requirement", "validated_by"))

        def ip():
            return rng.choice([f"192.168.10.{rng.randint(10, 250)}", f"10.20.{rng.randint(1, 9)}.{rng.randint(10, 250)}", f"112.198.{rng.randint(1, 250)}.{rng.randint(1, 250)}"])

        def moment():
            day = start + timedelta(days=rng.randint(0, 59))
            return day.replace(hour=rng.randint(7, 18), minute=rng.randint(0, 59), second=rng.randint(0, 59))

        logs = []

        def add(user, action, when, model="", obj_id="", details=None):
            logs.append(AuditLog(user=user, action=action, model_name=model, object_id=str(obj_id), details=details or {}, ip_address=ip(), timestamp=when))

        for _ in range(60):
            user = rng.choice(staff_users + faculty_users)
            when = moment()
            add(user, AuditLog.Action.LOGIN, when, "User", user.pk, {"role": user.role})
            if len(logs) < 200 and rng.random() < 0.67:
                add(user, AuditLog.Action.LOGOUT, when + timedelta(minutes=rng.randint(5, 50)), "User", user.pk)
        for doc in rng.sample(docs, min(30, len(docs))):
            add(doc.faculty.user, AuditLog.Action.UPLOAD, doc.uploaded_at, "Document", doc.pk,
                {"faculty": doc.faculty.full_name, "requirement": doc.requirement.name, "version": doc.version_no, "filename": doc.original_filename})
        for v in rng.sample(validations, min(25, len(validations))):
            add(v.validated_by, AuditLog.Action.VALIDATE, v.validated_at, "Document", v.document_id,
                {"faculty": v.document.faculty.full_name, "requirement": v.document.requirement.name, "decision": v.decision, "remarks": v.remarks})
        for i in range(25):
            doc = rng.choice(all_docs)
            user = rng.choice(self.hr_admins + [self.staff["area.chair"], doc.faculty.user])
            action = AuditLog.Action.DOWNLOAD if i < 15 else AuditLog.Action.PREVIEW
            add(user, action, moment(), "Document", doc.pk, {"faculty": doc.faculty.full_name, "requirement": doc.requirement.name, "version": doc.version_no})
        sysadmin = self.staff["sysadmin"]
        for req in rng.sample(list(self.requirements.values()), 5):
            add(sysadmin, AuditLog.Action.RULE_CHANGE, moment(), "Requirement", req.pk, {"event": "updated", "item": str(req), "changed": ["documentary_basis"]})
        for user in rng.sample(faculty_users, 6):
            add(sysadmin, AuditLog.Action.USER_CHANGE, moment(), "User", user.pk, {"event": rng.choice(["created", "password reset", "updated"]), "username": user.username})
        for title in ["PACUCOA Area II Compliance Matrix", "Missing-Document Report", "PACUCOA Area II Audit Summary", "Expiring and Expired Credentials Report", "Faculty Compliance Summary", "PACUCOA Area II Compliance Matrix"]:
            add(rng.choice(self.hr_admins + [self.staff["area.chair"]]), AuditLog.Action.REPORT, moment(), "Report", "", {"report": title, "format": rng.choice(["pdf", "xlsx"])})
        while len(logs) < 200:
            add(None, AuditLog.Action.LOGIN_FAILED, moment(), "User", "", {"username": rng.choice(faculty_users).username})
        logs = sorted(logs, key=lambda log: log.timestamp)[:200]
        AuditLog.objects.bulk_create(logs)
        self.audit_count = len(logs)

    # ------------------------------------------------------------------ summary
    def print_summary(self):
        w = self.stdout.write
        statuses = ComplianceStatus.objects.all()
        w(self.style.SUCCESS("\nFRAMES demo data seeded."))
        w(f"  Departments: {Department.objects.count()} | Sub-areas: {PacucoaSubArea.objects.count()} | Requirements: {Requirement.objects.count()}")
        w(f"  Users: {User.objects.count()} | Faculty: {Faculty.objects.count()} "
          f"(full-time {Faculty.objects.filter(employment_status='FULL_TIME').count()}, part-time {Faculty.objects.filter(employment_status='PART_TIME').count()}, "
          f"graduate {Faculty.objects.filter(faculty_type='GRADUATE').count()}, foreign degree {Faculty.objects.filter(has_foreign_degree=True).count()}, "
          f"licensure {Faculty.objects.filter(teaches_licensure_program=True).count()}, study leave {Faculty.objects.filter(on_study_leave=True).count()})")
        w(f"  Documents: {Document.objects.count()} ({Document.objects.filter(is_current=True).count()} current; "
          f"{self.history_cells} requirement(s) with 2-3 versions) | Validations: {Validation.objects.count()}")
        w(f"  Notifications: {self.notification_count} ({Notification.objects.filter(is_read=False).count()} unread) | Audit log entries: {self.audit_count}")

        w("\nCompliance cases generated:")
        for case in (NOEXP, FAR, EXP30, EXP60, EXP90, EXPIRED, PENDING, RESUBMIT, REJECTED, NONE):
            w(f"  {case:<32} {self.case_counts[case]:>4}")

        w("\nCompliance status counts:")
        for code, label in ComplianceStatus.Status.choices:
            w(f"  {label:<14} {statuses.filter(status=code).count():>4}")
        w(f"  {'(expiring)':<14} {statuses.filter(is_expiring=True).count():>4}")
        w(self.style.SUCCESS(f"\nOverall Area II compliance: {compliance_rate(statuses):.2f}%"))
        w("By sub-area:")
        for s in rates_by_subarea(statuses):
            w(f"  {s['code']:<6} {s['title']:<42} {s['rate']:>6.2f}%")
        w("By department:")
        for d in rates_by_department(statuses):
            w(f"  {d['code']:<6} {d['name']:<42} {d['rate']:>6.2f}%")

        full = sum(1 for f in self.faculty if statuses.filter(faculty=f).exclude(status="COMPLIED").count() == 0)
        weak = sum(1 for f in self.faculty if compliance_rate(statuses.filter(faculty=f)) < 40)
        w(f"Fully compliant faculty: {full} | Faculty below 40%: {weak}")

        w("\nDemo logins (password for all: " + DEMO_PASSWORD + "):")
        w("  sysadmin                       System Administrator")
        w("  hr.admin1 / hr.admin2 / hr.admin3   HR / Records Administrators")
        w("  area.chair                     PACUCOA Area II Chair (all departments)")
        w("  " + " / ".join(f"dean.{c.lower()}" for c, *_ in DEPARTMENTS) + "   Area Chair scoped to one department")
        model = [f for f in self.faculty if f.spec.profile == "model"][:2]
        weak_f = [f for f in self.faculty if f.spec.profile == "weak"][:1]
        sample = model + weak_f + [f for f in self.faculty if f.spec.profile == "normal"][:2]
        w("  Faculty, e.g.: " + ", ".join(f"{f.user.username}" for f in sample))
