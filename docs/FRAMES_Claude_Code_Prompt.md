# Claude Code Prompt — Build FRAMES

Copy everything below the line into Claude Code, run from an empty project folder.

---

Build a complete Django web application called **FRAMES: Faculty 201 Records, Academic Credentials, and Accreditation Evidence Analytics System for PACUCOA Area II** for Colegio de Kidapawan, Inc.

## How to work (important)

- **Build everything first, test once at the end.** Do NOT run the server, migrations, or tests after each file or step. Write all apps, models, views, templates, static files, management commands, and the seeder first.
- Only after the whole system is written: run `makemigrations`, `migrate`, `seed_frames`, `check`, the test suite **once**, and fix whatever fails. Then start the server once to confirm it boots.
- Do not ask me questions mid-build. Make sensible choices and list them in the README.
- Keep the code clean and modular. No placeholder "TODO" features — every listed feature must work.

## Tech stack (fixed)

- Python 3.12, **Django 5**, **PostgreSQL 16** via **psycopg 3** (`psycopg[binary]`)
- Bootstrap 5 (CDN), Chart.js (CDN), vanilla JavaScript — no React, no build step
- ReportLab (PDF reports), openpyxl (Excel reports)
- `cryptography` (Fernet) for encrypting uploaded files at rest
- `python-dotenv` for settings; `.env.example` with `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `DEBUG`, `EMAIL_*`
- Email backend: console backend in development
- Create `requirements.txt`, `.env.example`, `.gitignore`, and `README.md` (setup, PostgreSQL database creation commands, how to seed, demo accounts)

## Project layout

Project `frames_project`, apps:

| App | Responsibility |
|---|---|
| `accounts` | Custom User model (`AbstractUser`) with `role`, login/logout, password change, role decorators/mixins, user management |
| `faculty` | Departments, Faculty profiles |
| `requirements` | PACUCOA sub-areas (II.A–II.F) and configurable requirement rules |
| `documents` | Uploads, versions, validation workflow, encrypted storage, protected download |
| `compliance` | Compliance engine, compliance status, matrix, expiry tracking |
| `dashboard` | Executive dashboard (Chart.js) |
| `reports` | PDF and Excel exports |
| `notifications` | In-app notifications + email |
| `audit` | Audit log of user actions |

## Roles (role-based access control)

Use `User.role` with choices: `FACULTY`, `HR_ADMIN`, `AREA_CHAIR`, `SYS_ADMIN`.

| Role | Can do |
|---|---|
| Faculty Member | View/edit own profile; upload and re-submit 201 files, credentials, evidence for **own applicable requirements only**; view own compliance status, reviewer remarks, notifications |
| HR / Records Administrator | Manage faculty profiles; validate documents (Approve / Reject / Request Re-submission with remarks); expiry lists; matrix; dashboard; reports |
| PACUCOA Area II Chair | Validate evidence documents; view matrix, dashboard, reports. Optional `department` scope on the user: if set, sees only that department; if null, sees all |
| System Administrator | Manage users and roles; configure sub-areas and requirement rules; view audit logs; everything HR can view |

Enforce with mixins/decorators on every view **and** filter querysets by role (a faculty member must never be able to open another faculty member's document by changing the URL).

## Data model

- **Department**: code, name, dean_name
- **Faculty**: one-to-one User, department FK, employee_no (unique), last/first/middle name, sex, employment_status (`FULL_TIME`, `PART_TIME`), faculty_type (`UNDERGRADUATE`, `GRADUATE`), academic_rank (Instructor I–III, Assistant Professor I–IV, Associate Professor I–V, Professor), highest_degree (`BACHELOR`, `MASTER`, `DOCTORATE`), has_foreign_degree (bool), teaches_licensure_program (bool), on_study_leave (bool), date_hired, contact_no
- **PacucoaSubArea**: code (`II.A`…`II.F`), title, description, sort_order
- **Requirement**: subarea FK, name, documentary_basis, is_mandatory, has_expiry, `applicability` (choices: `ALL`, `GRADUATE_FACULTY`, `FOREIGN_DEGREE`, `LICENSURE_PROGRAM`, `STUDY_LEAVE`), is_active, sort_order
- **Document**: faculty FK, requirement FK, encrypted file (stored outside MEDIA public path), original_filename, file_type, file_size, date_issued, expiry_date (nullable), version_no, is_current (bool), status (`PENDING`, `APPROVED`, `REJECTED`, `RESUBMIT`), uploaded_at
- **Validation**: document FK, validated_by FK User, decision, remarks, validated_at
- **ComplianceStatus**: faculty FK, requirement FK, document FK (nullable), status (`COMPLIED`, `INCOMPLETE`, `NOT_COMPLIED`), is_expiring (bool), days_to_expiry (nullable), evaluated_at — unique (faculty, requirement)
- **Notification**: user FK, type, message, link, is_read, created_at
- **ExpiryAlertSent**: document FK, threshold (90/60/30) — unique together, so each alert is sent once
- **AuditLog**: user FK (nullable), action, model_name, object_id, details (JSON), ip_address, timestamp

## Requirement applicability

`Requirement.applies_to(faculty)`:
- `ALL` → always
- `GRADUATE_FACULTY` → faculty_type == GRADUATE
- `FOREIGN_DEGREE` → has_foreign_degree
- `LICENSURE_PROGRAM` → teaches_licensure_program
- `STUDY_LEAVE` → on_study_leave

Non-applicable requirements are **excluded** from both numerator and denominator and shown as "N/A" (grey) in the matrix.

## Compliance engine (`compliance/engine.py`) — core logic

For each applicable requirement of a faculty member, take the **current** document (`is_current=True`):

1. No document → `NOT_COMPLIED`
2. Status `PENDING` or `RESUBMIT` → `INCOMPLETE`
3. Status `REJECTED` → `NOT_COMPLIED`
4. `APPROVED` and requirement has no expiry → `COMPLIED`
5. `APPROVED`, expiry date passed → `NOT_COMPLIED` (expired)
6. `APPROVED`, expires within 90 days → `COMPLIED` with `is_expiring=True`
7. `APPROVED`, expiry more than 90 days away → `COMPLIED`

Functions: `evaluate_faculty(faculty)`, `evaluate_all()`, `compliance_rate(queryset)` = complied / applicable × 100 (rounded to 2 decimals), plus rates per sub-area and per department.

Re-evaluate automatically (signals or service calls) when a document is uploaded, validated, or a requirement rule is changed.

## Features

1. **Authentication**: login, logout, password change; redirect to role home after login.
2. **Faculty profile**: faculty edit contact info only; HR/SysAdmin edit everything. Profile page shows compliance % overall and per sub-area, and the requirement checklist with status badges.
3. **Upload**: faculty pick an applicable requirement, upload PDF/JPG/PNG (max 10 MB, validate extension **and** content type), enter date issued and expiry date (expiry required if `has_expiry`). Re-upload creates a new version (`version_no + 1`), older versions kept with `is_current=False`. Document history visible.
4. **Encrypted storage**: encrypt file bytes with Fernet before saving to `PRIVATE_MEDIA_ROOT` (not served by Django static/media). Download/preview through a view that checks permissions, decrypts, and streams the file. Log every download in AuditLog.
5. **Validation queue**: HR and Area Chair see pending documents (filter by department, sub-area). Open document preview side by side with the requirement; decide Approve / Reject / Request Re-submission with required remarks for non-approve. Notify the faculty member.
6. **Requirement rule configuration** (SysAdmin): CRUD for sub-areas and requirements without code changes; changing a rule triggers `evaluate_all()`.
7. **Expiry tracking**: management command `check_expirations` — re-evaluates, sends alerts at 90, 60, and 30 days before expiry (in-app + email), once per threshold, and marks expired items. Document in README how to schedule it daily (cron / Windows Task Scheduler). Also provide an "Expiring credentials" page (filter 30/60/90 days, expired).
8. **PACUCOA compliance matrix**: rows = faculty, columns = requirements grouped by sub-area header; color-coded cells (green Complied, amber Incomplete, red Not Complied, grey N/A, plus a clock icon for expiring). Filters: department, sub-area, employment status, compliance status. Totals per row (faculty %) and per column (requirement %). Sticky header and first column.
9. **Executive dashboard** (Chart.js): KPI cards (overall Area II compliance %, faculty count, fully compliant faculty, pending validations, expiring in 90 days, expired); bar chart compliance % by sub-area; bar chart by department; doughnut of status counts; table of top 10 most-missing requirements; list of soonest expiring credentials. Department filter.
10. **Reports** (PDF via ReportLab and Excel via openpyxl, with school name, report title, filters used, generated date and user):
    - Faculty compliance summary (one faculty, all requirements)
    - Area II compliance matrix (department filter)
    - Missing-document report
    - Expiring/expired credentials report
    - Area II audit summary (per sub-area and department rates)
11. **Notifications**: bell icon with unread count in navbar; list page; mark as read.
12. **Audit log**: record login/logout, uploads, downloads, validations, rule changes, user changes (with IP). SysAdmin page with filters.
13. **User management** (SysAdmin): create users, assign role and department scope, activate/deactivate, reset password. Creating a FACULTY user also creates the Faculty profile.
14. **Search**: faculty list searchable by name/employee no. and filterable by department, rank, employment status, highest degree, compliance status.

## UI

- Bootstrap 5, clean admin-style layout: left sidebar (menu items depend on role), top navbar with notifications and user menu.
- Header text "Colegio de Kidapawan, Inc. — FRAMES". Navy/blue primary color.
- Responsive (works on phone). Status badges consistent everywhere: Complied (success), Incomplete (warning), Not Complied (danger), N/A (secondary).
- Django messages for feedback; confirm dialogs for reject/delete actions.
- Pagination on long lists.

## Security

- CSRF on all forms, `@login_required` everywhere except login.
- Passwords via Django hashers. Session expires after 30 minutes of inactivity.
- Production settings block in `settings.py` controlled by `DEBUG`: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS.
- File upload limits and type checks; private media never under a public URL.

## Seeder — `python manage.py seed_frames [--reset]`

Create realistic, consistent demo data (Filipino names, Mindanao setting). `--reset` wipes FRAMES data first. Use a fixed random seed so results are reproducible.

**Departments (sample — easy to edit at top of the seeder):**
College of Computer Studies (CCS), College of Business Administration (CBA), College of Teacher Education (CTE), College of Criminal Justice Education (CCJE), College of Arts and Sciences (CAS)

**Sub-areas II.A–II.F and these 20 requirements:**

| Sub-area | Requirement | Expiry | Mandatory | Applicability |
|---|---|---|---|---|
| II.A | Bachelor's diploma and transcript of records | No | Yes | ALL |
| II.A | Master's diploma and transcript (vertical alignment) | No | Yes | ALL |
| II.A | Doctoral diploma and transcript | No | Conditional | GRADUATE_FACULTY |
| II.A | CAV / degree equivalency | No | Conditional | FOREIGN_DEGREE |
| II.A | PRC license / certificate of registration | Yes | Conditional | LICENSURE_PROGRAM |
| II.B | Appointment contract / terms of employment | Yes | Yes | ALL |
| II.B | Updated curriculum vitae / personal data sheet | No | Yes | ALL |
| II.B | Service record / certificate of employment | No | Yes | ALL |
| II.B | Certificate of academic rank and promotion | No | Yes | ALL |
| II.C | Annual faculty development participation plan | Yes | Yes | ALL |
| II.C | Seminar and training certificates (past 3 years) | No | Yes | ALL |
| II.C | Study leave contract / scholarship agreement | Yes | Conditional | STUDY_LEAVE |
| II.D | Official teaching load assignment form | Yes | Yes | ALL |
| II.D | Summarized performance ratings (student/peer/dean) | Yes | Yes | ALL |
| II.D | Sample course syllabi and instructional materials | Yes | Yes | ALL |
| II.E | Refereed publications / books authored | No | Yes | ALL |
| II.E | Completed institutional or funded research reports | No | Yes | ALL |
| II.E | Community extension certificates and reports | No | Yes | ALL |
| II.F | NBI / police clearance | Yes | Yes | ALL |
| II.F | Annual medical / health clearance | Yes | Yes | ALL |

**Users (password for all: `Frames@2026`):**
- `sysadmin` — System Administrator
- `hr.admin1`, `hr.admin2`, `hr.admin3` — HR / Records Administrators
- `area.chair` — PACUCOA Area II Chair (all departments) + one dean account per department with role AREA_CHAIR scoped to that department (e.g., `dean.ccs`)
- **45 faculty** (`firstname.lastname`), spread across the 5 departments, ~30 full-time / ~15 part-time, ~8 graduate faculty, ~3 with foreign degrees, ~12 teaching licensure programs (CTE, CCJE), ~2 on study leave; realistic ranks, degrees, hire dates (2005–2025), employee numbers like `CDK-2018-0123`

**Documents:** For each faculty, generate documents so the data produces a believable spread (overall Area II compliance around 65–75%), and make sure **every compliance case appears at least several times**:
- approved, no expiry → Complied
- approved, expiry > 90 days → Complied
- approved, expiring in ≤ 30, 31–60, 61–90 days → Complied + expiring
- approved, already expired (e.g., NBI clearance, PRC license) → Not Complied
- pending → Incomplete
- returned for re-submission with remarks (e.g., "Transcript page 2 is unreadable; please rescan.") → Incomplete
- rejected → Not Complied
- no upload → Not Complied
- at least 5 documents with 2–3 versions (history)
- Include ~5 "model" faculty who are 100% compliant and ~5 weak ones below 40%, and vary compliance by department so the dashboard charts are interesting.

Generate small real **PDF files** with ReportLab for each seeded document (title of the requirement, faculty name, "SAMPLE DOCUMENT – FOR TESTING ONLY"), encrypt them through the same storage service the app uses, so preview/download works.

Also seed: Validation records with realistic remarks and validators, ~60 notifications (some unread), ~200 audit log entries over the past 60 days. Finish by running `evaluate_all()` and printing a summary (counts per status, overall %, % per sub-area, % per department, demo logins).

## Tests (write them, but run only at the end, once)

`compliance/tests.py` covering all engine cases (TC-01 to TC-08: no doc, pending, re-submission, approved no expiry, expiry > 90 days, expiry within 90 days, expired, non-applicable excluded) and rate calculation. Plus a few permission tests: faculty cannot open another faculty's document or the validation queue; non-SysAdmin cannot edit rules.

## Final run sequence (only after everything is built)

1. `pip install -r requirements.txt`
2. Create the PostgreSQL database from `.env` values (give me the `psql` commands in the README; assume PostgreSQL is installed locally)
3. `python manage.py makemigrations && python manage.py migrate`
4. `python manage.py seed_frames --reset`
5. `python manage.py check` and `python manage.py test` — fix any failures
6. `python manage.py runserver` once to confirm it starts, then stop

When finished, give me a short summary: how to run it, demo accounts, and anything you had to assume.
