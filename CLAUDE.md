# FRAMES — instructions for Claude Code

The project scaffold already exists in this folder (Django project `frames_project`, apps: accounts, faculty, requirements, documents, compliance, dashboard, reports, notifications, audit). Build INTO this structure; do not create a new project.

The complete specification is in `docs/FRAMES_Claude_Code_Prompt.md`. Read it fully before writing code. The approved proposal is in `docs/`.

Working rules:
- Build everything first. Do NOT run the server, migrations, or tests after each step.
- After all code, templates, static files, management commands and the seeder are written, run once: makemigrations, migrate, `seed_frames --reset`, `check`, `test`; fix failures; start the server once to confirm.
- Database is PostgreSQL 16 via psycopg 3 (settings already configured from `.env`).
- `AUTH_USER_MODEL = "accounts.User"` is already set — create the custom User model before the first migration.
- Do not ask questions mid-build; record assumptions in README.md.
