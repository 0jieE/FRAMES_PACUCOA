# FRAMES

**Faculty 201 Records, Academic Credentials, and Accreditation Evidence Analytics System for PACUCOA Area II**
Colegio de Kidapawan, Inc.

Stack: Python 3.12+, Django 5.2, PostgreSQL 16/17 (psycopg 3), Bootstrap 5 + Chart.js (CDN), ReportLab, openpyxl, cryptography (Fernet).

---

## 1. Setup

```powershell
python -m venv venv
venv\Scripts\activate                 # Windows  (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                # then fill in the values below
```

Generate the file-encryption key and put it in `.env` as `FIELD_ENCRYPTION_KEY`:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Keep this key safe.** Every uploaded document is encrypted with it. If it is lost or changed,
> existing files can no longer be opened (re-run the seeder for demo data).

### `.env` keys

| Key | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for development. `False` enables HTTPS redirect, secure cookies, and HSTS |
| `ALLOWED_HOSTS` | Comma-separated host names |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection |
| `FIELD_ENCRYPTION_KEY` | Fernet key for encrypting uploaded files at rest |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Email (console backend in development: emails are printed in the server terminal) |
| `SITE_URL` | Base URL used for links inside notification emails |

## 2. Create the PostgreSQL database

Open `psql` as the `postgres` superuser. If you have more than one PostgreSQL version installed, pass the port of the one you want.
(On this machine PostgreSQL **17 listens on port 5433** and 13 on 5432, so `.env` uses `DB_PORT=5433`.)

```powershell
psql -U postgres -p 5433
```

Using the `postgres` account directly (what `.env` does now):

```sql
CREATE DATABASE frames_db ENCODING 'UTF8';
```

Or with a dedicated application user (recommended for production):

```sql
CREATE USER frames_user WITH PASSWORD 'change-me';
CREATE DATABASE frames_db OWNER frames_user ENCODING 'UTF8';
ALTER USER frames_user CREATEDB;   -- only needed to run the test suite (it creates test_frames_db)
```

## 3. Migrate, seed, run

```powershell
python manage.py migrate
python manage.py seed_frames --reset
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in.

Other commands:

```powershell
python manage.py check
python manage.py test                 # engine TC-01..TC-08, rates, permissions, upload/encryption, expiry alerts
python manage.py check_expirations    # daily expiry job (see §5)
python manage.py createsuperuser      # optional; superusers survive seed_frames --reset
```

## 4. Demo accounts

Password for **all** demo accounts: `Frames@2026`

| Username | Role | Notes |
|---|---|---|
| `sysadmin` | System Administrator | Users and roles, requirement rules, audit log, plus everything HR can view. Also a Django `/admin/` superuser |
| `hr.admin1`, `hr.admin2`, `hr.admin3` | HR / Records Administrator | Faculty profiles, validation, expiry lists, matrix, dashboard, reports |
| `area.chair` | PACUCOA Area II Chair | All departments |
| `dean.ccs`, `dean.cba`, `dean.cte`, `dean.ccje`, `dean.cas` | Area II Chair, department-scoped | See only their own department |
| 45 faculty: `firstname.lastname` (e.g. listed at the end of the seeder output) | Faculty Member | Own profile, uploads, compliance |

The seeder prints the full summary (counts per status, overall %, % per sub-area and department) and sample faculty logins.
The faculty list (log in as `hr.admin1`) shows every faculty username's owner. A faculty username is the first and last name in lowercase with spaces and accents removed (e.g. `Niño Delos Reyes` → `nino.delosreyes`).

## 5. Expiry alerts: schedule `check_expirations` daily

`check_expirations` re-evaluates all compliance and sends in-app and email alerts **90, 60 and 30 days** before a credential expires, plus an "expired" notice. Each alert is sent only once (`ExpiryAlertSent` is unique per document and threshold). When a document is first checked after it has already passed several thresholds, only the tightest one is sent. HR administrators get a one-line digest. `--no-email` sends in-app notifications only.

**Windows Task Scheduler** (daily at 6:00 AM):

```powershell
schtasks /Create /SC DAILY /ST 06:00 /TN "FRAMES check_expirations" ^
  /TR "\"C:\path\to\pacucoa\venv\Scripts\python.exe\" \"C:\path\to\pacucoa\manage.py\" check_expirations"
```

**Linux cron** (`crontab -e`):

```cron
0 6 * * * cd /srv/frames && /srv/frames/venv/bin/python manage.py check_expirations >> /var/log/frames_expiry.log 2>&1
```

## 6. Deploying to Render

Repository: <https://github.com/0jieE/FRAMES_PACUCOA>. Deployment files: `render.yaml` (Blueprint), `build.sh` (install → `collectstatic` → `migrate`), `.python-version` (3.13). In production the app runs with **gunicorn** and serves static files with **WhiteNoise**.

### How production differs from local

- **Database.** `DATABASE_URL` takes priority over the `DB_*` variables. Use Render's *Internal* Database URL for the web service. The *External* URL (`…singapore-postgres.render.com`) is for connecting from your PC, and SSL is turned on automatically for it.
- **Uploaded documents.** These are stored **in PostgreSQL** (`PRIVATE_STORAGE=database`, table `documents_storedfile`), still Fernet-encrypted. Render's disk is wiped on every deploy, so files saved there would disappear. Set `PRIVATE_STORAGE=filesystem` only on a host with a persistent disk.
- **Encryption key.** `FIELD_ENCRYPTION_KEY` on Render **must be the same key** as in the local `.env` that encrypted the data. Otherwise no document can be opened.
- **Security settings.** `DEBUG=False` turns on HTTPS redirect, secure cookies and HSTS. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` pick up `RENDER_EXTERNAL_HOSTNAME` automatically.

### First deployment

1. Push this project to the GitHub repository (`main` branch).
2. In Render: **New → Blueprint**, pick the repository. Render reads `render.yaml` and creates the `frames-pacucoa` web service in the Singapore region.
3. When Render asks for the variables marked `sync: false`, enter:
   - `DATABASE_URL`: Render dashboard → `db_pacucoa` → *Connections* → **Internal Database URL**
   - `FIELD_ENCRYPTION_KEY`: copied from your local `.env`
4. Deploy. `build.sh` runs `migrate`, which does nothing on the already-loaded database. Then open `https://<service>.onrender.com/login/`.

### Copying data from local PostgreSQL to Render (already done once)

```powershell
# from the project folder, with PostgreSQL 17 client tools
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" -h localhost -p 5433 -U postgres -d frames_db -Fc --no-owner --no-acl -f frames.dump
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" --no-owner --no-acl --single-transaction -d "<EXTERNAL_DATABASE_URL>?sslmode=require" frames.dump
```

Only restore into an **empty** database. To reset the Render data from scratch instead, run the seeder against it:

```powershell
$env:DATABASE_URL = "<EXTERNAL_DATABASE_URL>"; python manage.py seed_frames --reset; Remove-Item Env:DATABASE_URL
```

If a database still has files on disk from `PRIVATE_STORAGE=filesystem`, run `python manage.py move_files_to_db` once. It copies the encrypted files into PostgreSQL without decrypting them.

### Notes

- **Expiry alerts.** Render cron jobs are a paid service. Uncomment the `cron` block in `render.yaml` to run `check_expirations` daily, or run it by hand with `DATABASE_URL` pointing at Render.
- **Free plan limits.** A free web service sleeps after about 15 minutes idle; the first request after that takes roughly 30–60 s. Check the expiry date of your Render Postgres plan in the dashboard.
- **Demo passwords.** The demo accounts all use the password in §4. Before sharing the public URL, change the `sysadmin` and HR passwords under *Users & roles*.

## 7. Features

- **Roles and access control**: decorators/mixins on every view, plus querysets filtered by role (`Faculty.objects.visible_to(user)`, `Document.objects.visible_to(user)`). Opening another faculty member's document by URL returns 404.
- **Compliance engine** (`compliance/engine.py`): the seven rules from the specification, run on the current document of each applicable requirement. Requirements that don't apply to someone are left out of the numerator and denominator and shown as N/A. It re-evaluates automatically through signals when a document is uploaded or validated, a faculty profile changes, or a rule changes.
- **Encrypted storage** (`documents/storage.py`): bytes are Fernet-encrypted before they are written to `private_media/`. That folder is never served at a URL. Downloads and previews go through a view that checks permissions, decrypts the file, and logs the access.
- **Uploads**: PDF/JPG/PNG up to 10 MB. Each upload is checked by extension, declared content type, and file signature (magic bytes). Re-uploading creates version *n+1* and keeps the full history.
- **Validation queue**: filter by department and sub-area. Preview the document beside the requirement, then Approve, Reject, or Request Re-submission. Remarks are required unless you approve. The faculty member gets an in-app notice and an email.
- **Compliance matrix**: sticky header and first column, colour-coded cells, a clock icon for expiring items, row and column totals, filters, and PDF/Excel export.
- **Dashboard**: KPI cards, bar charts by sub-area and department, a status doughnut, the top-10 most-missing requirements, and the soonest-expiring credentials.
- **Reports** (PDF and Excel): faculty summary, Area II matrix, missing documents, expiring/expired credentials, and Area II audit summary.
- **Notifications** (navbar bell, list, mark as read), **audit log** (with IP address and filters), **user management**, and **faculty search**.

## 8. Assumptions and design decisions

- **Django 5.2 LTS**, installed in a project `venv`. The machine's global Python has Django 6.1, and `requirements.txt` pins `<6.0`.
- **PostgreSQL 17** is used (the spec says 16). The schema uses nothing version-specific.
- **Non-applicable requirements** get no `ComplianceStatus` row. The absence of a row is what "N/A" means.
- **Expiry window**: 0–90 days (inclusive) counts as *expiring*. A document that expires today is still Complied. One that expired yesterday is Not Complied. If a requirement has an expiry but an approved document has no expiry date (e.g. the rule was changed after approval), the document is treated as Complied.
- **"Mandatory = Conditional"** in the spec means the requirement is mandatory *when it applies*. These rules are stored with `is_mandatory=True` and a conditional `applicability`, and the UI labels them "Conditional". Every active, applicable requirement counts toward the rate. `is_mandatory=False` is shown as "Optional" and is informational only.
- **Who validates**: HR administrators and Area Chairs can validate any document in their scope. Area Chairs are limited to their department when one is set. The System Administrator can *see* the queue but cannot decide on documents, so a separate role always handles validation.
- **Faculty profile edits**: faculty members can change only their contact number and email. HR and SysAdmin can change everything. Changing applicability flags (graduate, licensure, foreign degree, study leave) re-evaluates compliance.
- **Roles are locked to faculty profiles.** A user with a faculty profile must keep the Faculty role, and a Faculty user must be created together with a profile. This prevents orphaned profiles.
- **Deleting rules**: a requirement that already has documents, or a sub-area that still has requirements, cannot be deleted (PROTECT). Deactivate the requirement instead, which removes it from compliance.
- **Faculty in the reports**: staff export reports for anyone in their scope. Faculty members can download only their own compliance summary, from their profile page.
- **Compliance filters**: "compliance status" means *Fully compliant / Has incomplete items / Has non-complied items / Has expiring credentials*. The matrix applies it to the columns currently shown.
- **Seeded data is relative to today's date**, generated with a fixed random seed (2026). Running the seeder on a different day shifts the dates but keeps the same pattern. Seeded documents are small ReportLab PDFs marked "SAMPLE DOCUMENT – FOR TESTING ONLY", encrypted through the same storage service the app uses. About 12 expiry alerts are pre-marked as sent; the first `check_expirations` run sends the rest.
- **Sessions** expire after 30 minutes of inactivity (`SESSION_COOKIE_AGE` with `SESSION_SAVE_EVERY_REQUEST`).
- **Departments** can be managed in the app by HR and SysAdmin, and are also easy to edit at the top of `compliance/management/commands/seed_frames.py`.
